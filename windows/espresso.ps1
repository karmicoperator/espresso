# espresso for Windows: double-click "Start espresso.bat", or run this in PowerShell.
#
# On first run it fetches uv (which brings Python) and Node.js into
# %LOCALAPPDATA%\espresso\tools, never into system paths, installs the app's packages,
# builds the web app, starts both servers, waits until they answer, and opens the browser.
# Later runs skip what is already done, and a run that finds espresso already going only
# opens the browser. Ctrl-C in the window stops the servers that window started.
#
# UNTESTED on a real Windows machine at the time of writing: the author had none. It
# mirrors start.command step for step. When a step fails, the window says which one and
# where its log is, and stays open until Enter is pressed.

$ErrorActionPreference = "Stop"
# Windows PowerShell 5.1 redraws a progress bar for every block Invoke-WebRequest reads,
# which turns a 30 MB download into many minutes. Without the bar it takes seconds.
$ProgressPreference = "SilentlyContinue"
$Repo = Split-Path -Parent $PSScriptRoot
$Home_ = Join-Path $env:LOCALAPPDATA "espresso"
$Tools = Join-Path $Home_ "tools"
$Logs = Join-Path $Home_ "logs"
New-Item -ItemType Directory -Force -Path $Tools, $Logs | Out-Null
$NodeVersion = "v22.12.0"
$api = $null; $web = $null

function Say($t) { Write-Host "  $t" }

function StopStarted {
  # The whole tree, not just the process: a venv's python.exe on Windows is a launcher that
  # runs the real interpreter as its child, and stopping the launcher alone leaves the API up.
  foreach ($p in @($script:api, $script:web)) {
    if ($p -and -not $p.HasExited) { taskkill.exe /PID $p.Id /T /F 2>&1 | Out-Null }
  }
  # Anything else still running from our folders.
  Get-Process node, python -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -like "$Tools*" -or $_.Path -like "$Repo*" } |
    Stop-Process -Force -ErrorAction SilentlyContinue
}

function Fail($t) {
  StopStarted
  Write-Host ""; Write-Host "  $t" -ForegroundColor Red; Write-Host ""
  Write-Host "  Logs are in $Logs"; Write-Host ""
  Read-Host "Press Enter to close"
  exit 1
}

# Anything unexpected lands here, so the window says what happened instead of vanishing.
trap { Fail "Something went wrong: $_" }

$env:Path = "$Tools\bin;$Tools\node;$env:USERPROFILE\.local\bin;$env:Path"

function IsOurApi($port) {
  try { return (Invoke-RestMethod "http://127.0.0.1:$port/api/health" -TimeoutSec 3).app -eq "espresso" }
  catch { return $false }
}
function IsOurWeb($port) {
  try { return (Invoke-WebRequest "http://127.0.0.1:$port/" -UseBasicParsing -TimeoutSec 5).Content -match "espresso" }
  catch { return $false }
}
function Free($port) { -not (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) }

Write-Host "espresso"; Write-Host ""

# Already running, from an earlier window or one closed without Ctrl-C: open it and stop here.
$runningWeb = 3000..3012 | Where-Object { -not (Free $_) -and (IsOurWeb $_) } | Select-Object -First 1
$runningApi = 8000..8012 | Where-Object { -not (Free $_) -and (IsOurApi $_) } | Select-Object -First 1
if ($runningWeb -and $runningApi) {
  Say "espresso is already running."
  Start-Process "http://localhost:$runningWeb"
  Say "Opened http://localhost:$runningWeb in your browser. This window closes by itself."
  Start-Sleep -Seconds 6
  exit 0
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Say "Fetching uv (brings Python with it)..."
  $env:UV_INSTALL_DIR = "$Tools\bin"; $env:UV_NO_MODIFY_PATH = "1"
  try { Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression } catch { Fail "Could not fetch uv. Is the machine online? $_" }
  if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { Fail "uv was downloaded but cannot be found in $Tools\bin." }
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
  Say "Fetching Node.js $NodeVersion..."
  $arch = if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") { "arm64" } else { "x64" }
  $zip = "node-$NodeVersion-win-$arch.zip"
  try {
    Invoke-WebRequest "https://nodejs.org/dist/$NodeVersion/$zip" -OutFile "$Tools\$zip" -UseBasicParsing
    if (Test-Path "$Tools\node-tmp") { Remove-Item "$Tools\node-tmp" -Recurse -Force }
    New-Item -ItemType Directory -Force -Path "$Tools\node-tmp" | Out-Null
    # tar.exe (Windows 10 1803 and later) unpacks the zip in seconds; Expand-Archive takes minutes.
    $tar = Get-Command tar.exe -ErrorAction SilentlyContinue
    if ($tar) {
      & $tar.Source -xf "$Tools\$zip" -C "$Tools\node-tmp"
      if ($LASTEXITCODE -ne 0) { throw "tar exited with $LASTEXITCODE" }
    } else {
      Expand-Archive "$Tools\$zip" -DestinationPath "$Tools\node-tmp" -Force
    }
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
# Only the web app's own sources count; walking node_modules would take minutes.
$srcDirs = @("app", "components", "lib", "public") | ForEach-Object { Join-Path $fe $_ } | Where-Object { Test-Path $_ }
$srcFiles = @("next.config.ts", "package.json", "tsconfig.json", "postcss.config.mjs") |
  ForEach-Object { Join-Path $fe $_ } | Where-Object { Test-Path $_ } | ForEach-Object { Get-Item $_ }
$newest = @(Get-ChildItem $srcDirs -Recurse -File) + @($srcFiles) |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not (Test-Path $buildStamp) -or $newest.LastWriteTime -gt (Get-Item $buildStamp).LastWriteTime) {
  Say "Building the web app. First run only, about a minute."
  Push-Location $fe
  npm run build *>> "$Logs\setup.log"
  if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "The web app did not build. See $Logs\setup.log" }
  Pop-Location
  Set-Content $buildStamp (Get-Date)
}

# Ports: the defaults, stepping past ones that are taken.
$ApiPort = 8000; while (-not (Free $ApiPort) -and $ApiPort -lt 8012) { $ApiPort++ }
$WebPort = 3000; while (-not (Free $WebPort) -and $WebPort -lt 3012) { $WebPort++ }

# Both servers run from their own executables, not through npm or uv: Start-Process cannot
# start npm's .cmd and .ps1 shims with redirected output, and uv run would re-check the
# environment on every start.
$env:API_PORT = "$ApiPort"
$api = Start-Process -PassThru -WindowStyle Hidden -WorkingDirectory (Join-Path $Repo "backend") `
  -FilePath (Join-Path $Repo "backend\.venv\Scripts\python.exe") -ArgumentList "main.py" `
  -RedirectStandardOutput "$Logs\api.log" -RedirectStandardError "$Logs\api.err.log"
$env:API_URL = "http://127.0.0.1:$ApiPort"
$web = Start-Process -PassThru -WindowStyle Hidden -WorkingDirectory $fe `
  -FilePath (Get-Command node).Source `
  -ArgumentList "node_modules\next\dist\bin\next", "start", "-H", "127.0.0.1", "-p", "$WebPort" `
  -RedirectStandardOutput "$Logs\web.log" -RedirectStandardError "$Logs\web.err.log"

# Open the browser only once both answer; opening it earlier shows a "can't reach" page.
function WaitFor($what, $probe, $proc, $log) {
  for ($i = 0; $i -lt 120; $i++) {
    if (& $probe) { return }
    if ($proc.HasExited) { Fail "The $what stopped while starting. See $log" }
    Start-Sleep -Seconds 1
  }
  Fail "The $what did not start within two minutes. See $log"
}
Say "Starting espresso..."
WaitFor "API" { IsOurApi $ApiPort } $api "$Logs\api.err.log"
WaitFor "web app" { IsOurWeb $WebPort } $web "$Logs\web.err.log"

Start-Process "http://localhost:$WebPort"
Write-Host ""
Say "espresso is running at http://localhost:$WebPort and your browser should show it."
Say "Keep this window open while you use espresso. Ctrl-C here stops it."
try { while ($true) { Start-Sleep -Seconds 3600 } }
finally { StopStarted }
