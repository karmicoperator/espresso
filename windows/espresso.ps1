# espresso for Windows: double-click espresso.bat, or run this in PowerShell.
#
# On first run it fetches uv (which brings Python) and Node.js into
# %LOCALAPPDATA%\espresso\tools, never into system paths, installs the app's packages,
# builds the web app, starts both servers and opens the browser. Later runs skip what is
# already done. Ctrl-C in the window stops the servers.
#
# UNTESTED on a real Windows machine at the time of writing: the author had none. It
# mirrors start.command step for step; if a step fails, the log says which.

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$Home_ = Join-Path $env:LOCALAPPDATA "espresso"
$Tools = Join-Path $Home_ "tools"
$Logs = Join-Path $Home_ "logs"
New-Item -ItemType Directory -Force -Path $Tools, $Logs | Out-Null
$NodeVersion = "v22.12.0"

function Say($t) { Write-Host "  $t" }
function Fail($t) { Write-Host ""; Write-Host "  $t"; Write-Host ""; Read-Host "Press Enter to close"; exit 1 }

$env:Path = "$Tools\bin;$Tools\node;$env:USERPROFILE\.local\bin;$env:Path"

Write-Host "espresso"; Write-Host ""

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Say "Fetching uv (brings Python with it)..."
  $env:UV_INSTALL_DIR = "$Tools\bin"; $env:UV_NO_MODIFY_PATH = "1"
  try { Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression } catch { Fail "Could not fetch uv. Is the machine online? $_" }
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
  Say "Fetching Node.js $NodeVersion..."
  $arch = if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") { "arm64" } else { "x64" }
  $zip = "node-$NodeVersion-win-$arch.zip"
  try {
    Invoke-WebRequest "https://nodejs.org/dist/$NodeVersion/$zip" -OutFile "$Tools\$zip"
    Expand-Archive "$Tools\$zip" -DestinationPath "$Tools\node-tmp" -Force
    if (Test-Path "$Tools\node") { Remove-Item "$Tools\node" -Recurse -Force }
    Move-Item "$Tools\node-tmp\node-$NodeVersion-win-$arch" "$Tools\node"
    Remove-Item "$Tools\node-tmp", "$Tools\$zip" -Recurse -Force
  } catch { Fail "Could not fetch Node.js. $_" }
}

# Backend packages, exactly the lockfile. Skipped while the lockfile is unchanged.
$beStamp = Join-Path $Repo "backend\.venv\.espresso-installed"
$beLock = Get-FileHash (Join-Path $Repo "backend\uv.lock")
if (-not (Test-Path $beStamp) -or (Get-Content $beStamp) -ne $beLock.Hash) {
  Say "Installing the API's packages. First run only, about a minute."
  Push-Location (Join-Path $Repo "backend")
  uv sync --frozen --extra dev *>> "$Logs\setup.log"
  if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "The API's packages did not install. See $Logs\setup.log" }
  Pop-Location
  Set-Content $beStamp $beLock.Hash
}

# Web app packages and build. Rebuilt when a source file changed since the last build.
$fe = Join-Path $Repo "frontend"
$feStamp = Join-Path $fe "node_modules\.espresso-installed"
$feLock = Get-FileHash (Join-Path $fe "package-lock.json")
if (-not (Test-Path $feStamp) -or (Get-Content $feStamp) -ne $feLock.Hash) {
  Say "Installing the web app's packages. First run only, about a minute."
  Push-Location $fe
  npm install --no-fund --no-audit *>> "$Logs\setup.log"
  if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "The web app's packages did not install. See $Logs\setup.log" }
  Pop-Location
  Set-Content $feStamp $feLock.Hash
}
$buildStamp = Join-Path $fe ".next\.espresso-built"
$newest = Get-ChildItem $fe -Recurse -Include *.ts,*.tsx,*.css,*.json -Exclude node_modules,.next |
  Where-Object { $_.FullName -notmatch "node_modules|\\.next" } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not (Test-Path $buildStamp) -or $newest.LastWriteTime -gt (Get-Item $buildStamp).LastWriteTime) {
  Say "Building the web app..."
  Push-Location $fe
  npm run build *>> "$Logs\setup.log"
  if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "The web app did not build. See $Logs\setup.log" }
  Pop-Location
  Set-Content $buildStamp (Get-Date)
}

# Ports: the defaults, stepping past ones that are taken.
function Free($port) { -not (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) }
$ApiPort = 8000; while (-not (Free $ApiPort) -and $ApiPort -lt 8012) { $ApiPort++ }
$WebPort = 3000; while (-not (Free $WebPort) -and $WebPort -lt 3012) { $WebPort++ }

$api = Start-Process -PassThru -WindowStyle Hidden -WorkingDirectory (Join-Path $Repo "backend") `
  -FilePath "uv" -ArgumentList "run", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "$ApiPort" `
  -RedirectStandardOutput "$Logs\api.log" -RedirectStandardError "$Logs\api.err.log"
Say "api   started on :$ApiPort"
$env:API_URL = "http://127.0.0.1:$ApiPort"
$env:PORT = "$WebPort"
$web = Start-Process -PassThru -WindowStyle Hidden -WorkingDirectory $fe `
  -FilePath "npm" -ArgumentList "run", "start", "--", "-p", "$WebPort" `
  -RedirectStandardOutput "$Logs\web.log" -RedirectStandardError "$Logs\web.err.log"
Say "web   started on :$WebPort"

Start-Sleep -Seconds 4
Start-Process "http://localhost:$WebPort"
Write-Host ""; Say "open http://localhost:$WebPort"; Say "Ctrl-C to stop."
try { while ($true) { Start-Sleep -Seconds 3600 } }
finally {
  foreach ($p in @($api, $web)) { if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } }
  Get-Process node, python -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$Tools*" -or $_.Path -like "$Repo*" } | Stop-Process -Force -ErrorAction SilentlyContinue
}
