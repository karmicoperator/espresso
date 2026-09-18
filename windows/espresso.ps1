# espresso for Windows.
#
# The Start menu and desktop shortcuts run this with its console hidden. A first start, or
# the first after an update, shows a small window while it fetches uv (which brings Python)
# and Node.js, installs the app's packages and builds the web app. Then it starts the two
# servers, waits until both answer, opens the browser, and puts the cup in the notification
# area by the clock: click it to open espresso, right-click it to quit. Starting espresso
# again while it runs just opens the browser.
#
#   -NoUI   no windows, no tray, no browser: start espresso and exit once it answers,
#           leaving it running. For scripted runs and the Windows test in CI.
#   -Stop   stop a running espresso. The installer and uninstaller use this.
#
# Everything it downloads (tools, Python, caches) and its logs live in
# %LOCALAPPDATA%\espresso, so uninstalling removes them. Papers and settings live in the
# app's own folder, under backend\data and backend\.env, and survive an update.
#
# Tested on GitHub's Windows runner in CI (.github/workflows/windows.yml), which installs,
# starts, updates, stops and uninstalls it. Not yet on a person's Windows 10 or 11 machine.

param([switch]$NoUI, [switch]$Stop)

$ErrorActionPreference = "Stop"
# Windows PowerShell 5.1 redraws a progress bar for every block a download reads, which turns
# a 30 MB download into many minutes.
$ProgressPreference = "SilentlyContinue"
$Repo = Split-Path -Parent $PSScriptRoot
$Home_ = Join-Path $env:LOCALAPPDATA "espresso"
$Tools = Join-Path $Home_ "tools"
$Logs = Join-Path $Home_ "logs"
$StateFile = Join-Path $Home_ "running.txt"
New-Item -ItemType Directory -Force -Path $Tools, $Logs | Out-Null
$NodeVersion = "v22.12.0"
$Version = if (Test-Path "$Repo\VERSION") { (Get-Content "$Repo\VERSION" -Raw).Trim() } else { "dev" }
$UI = -not ($NoUI -or $Stop)

$env:UV_CACHE_DIR = Join-Path $Home_ "cache\uv"
$env:UV_PYTHON_INSTALL_DIR = Join-Path $Home_ "python"
$env:npm_config_cache = Join-Path $Home_ "cache\npm"
$env:Path = "$Tools\bin;$Tools\node;$env:Path"

$script:Progress = $null; $script:StatusLabel = $null; $script:Tray = $null; $script:Url = $null

function Log($t) { Add-Content -Path (Join-Path $Logs "launcher.log") -Value "$(Get-Date -Format s) $t" }

# ---------------------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------------------

if ($UI) {
  Add-Type -AssemblyName System.Windows.Forms, System.Drawing
  [System.Windows.Forms.Application]::EnableVisualStyles()
  $IconFile = Join-Path $PSScriptRoot "espresso.ico"
  $AppIcon = if (Test-Path $IconFile) { New-Object System.Drawing.Icon $IconFile } else { [System.Drawing.SystemIcons]::Application }
}

# Long steps run as separate processes while this loop keeps the window painted and its bar
# moving; without it Windows marks the window "Not responding".
function Pump { if ($script:Progress) { [System.Windows.Forms.Application]::DoEvents() } }

function Status($t) {
  Write-Host "  $t"; Log $t
  if ($script:StatusLabel) { $script:StatusLabel.Text = $t }
  Pump
}

function Font($size, $bold) {
  $style = if ($bold) { [System.Drawing.FontStyle]::Bold } else { [System.Drawing.FontStyle]::Regular }
  New-Object System.Drawing.Font("Segoe UI", $size, $style)
}

function ShowProgress {
  $f = New-Object System.Windows.Forms.Form
  $f.Text = "espresso"; $f.Icon = $AppIcon; $f.BackColor = [System.Drawing.Color]::White
  $f.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedDialog
  $f.MaximizeBox = $false; $f.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen
  $f.ClientSize = New-Object System.Drawing.Size(460, 164)
  $title = New-Object System.Windows.Forms.Label
  $title.Text = "espresso is getting ready"; $title.Font = Font 12 $true; $title.AutoSize = $true
  $title.Location = New-Object System.Drawing.Point(20, 16)
  $note = New-Object System.Windows.Forms.Label
  $note.Text = "The first start takes about five minutes while espresso downloads what it needs and builds itself. Your browser opens by itself when it is done."
  $note.Font = Font 9 $false; $note.Location = New-Object System.Drawing.Point(20, 48)
  $note.Size = New-Object System.Drawing.Size(420, 40)
  $bar = New-Object System.Windows.Forms.ProgressBar
  $bar.Style = [System.Windows.Forms.ProgressBarStyle]::Marquee; $bar.MarqueeAnimationSpeed = 30
  $bar.Location = New-Object System.Drawing.Point(20, 100); $bar.Size = New-Object System.Drawing.Size(420, 14)
  $status = New-Object System.Windows.Forms.Label
  $status.Font = Font 9 $false; $status.ForeColor = [System.Drawing.Color]::DimGray
  $status.Location = New-Object System.Drawing.Point(20, 126); $status.Size = New-Object System.Drawing.Size(420, 22)
  $f.Controls.AddRange(@($title, $note, $bar, $status))
  # Closing the window only hides it: espresso carries on and the browser still opens.
  $f.add_FormClosing({ param($s, $e)
    if ($e.CloseReason -eq [System.Windows.Forms.CloseReason]::UserClosing) { $e.Cancel = $true; $s.Hide() } })
  $f.Show(); $f.Activate()
  $script:Progress = $f; $script:StatusLabel = $status
  Pump
}

function CloseProgress {
  if ($script:Progress) { $script:Progress.Dispose(); $script:Progress = $null; $script:StatusLabel = $null }
}

function Notice($text, $isError) {
  if (-not $UI) { Write-Host "  $text"; return }
  $icon = if ($isError) { [System.Windows.Forms.MessageBoxIcon]::Error } else { [System.Windows.Forms.MessageBoxIcon]::Information }
  [void][System.Windows.Forms.MessageBox]::Show($text, "espresso", [System.Windows.Forms.MessageBoxButtons]::OK, $icon)
}

function Fail($t) {
  Log "FAILED: $t"
  StopServers
  CloseProgress
  if ($UI) {
    $answer = [System.Windows.Forms.MessageBox]::Show("espresso could not start.`n`n$t`n`nOpen the folder with the logs?",
      "espresso", [System.Windows.Forms.MessageBoxButtons]::YesNo, [System.Windows.Forms.MessageBoxIcon]::Error)
    if ($answer -eq [System.Windows.Forms.DialogResult]::Yes) { Start-Process explorer.exe $Logs }
  } else {
    Write-Host ""; Write-Host "  $t" -ForegroundColor Red; Write-Host "  Logs are in $Logs"
  }
  exit 1
}

# Anything unexpected lands here, so it is reported instead of vanishing with the window.
trap { Fail "Something went wrong: $_" }

# ---------------------------------------------------------------------------------------
# Processes
# ---------------------------------------------------------------------------------------

# Start-Process joins its arguments with spaces and quotes nothing, so a path with a space
# in it (a user name like "Anna Muster") would split. Quote each one that needs it.
function Quote($a) { if ($a -match '[\s"]') { '"' + ($a -replace '"', '\"') + '"' } else { $a } }

function RunStep($label, $file, [string[]]$arguments, $cwd) {
  Status $label
  $out = Join-Path $Logs "step.out"; $err = Join-Path $Logs "step.err"
  $p = Start-Process -FilePath $file -ArgumentList (($arguments | ForEach-Object { Quote $_ }) -join " ") `
    -WorkingDirectory $cwd -WindowStyle Hidden -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
  $null = $p.Handle   # without this, ExitCode is empty once the process has gone
  while (-not $p.HasExited) { Pump; Start-Sleep -Milliseconds 150 }
  $p.WaitForExit()
  Add-Content -Path (Join-Path $Logs "setup.log") -Value "== $(Get-Date -Format s) $label (exit $($p.ExitCode))"
  foreach ($f in $out, $err) { Get-Content $f -ErrorAction SilentlyContinue | Add-Content -Path (Join-Path $Logs "setup.log") }
  return $p.ExitCode
}

# A PowerShell snippet in a separate process, so a download does not freeze the window.
# -EncodedCommand sidesteps every quoting rule between here and there.
function RunPowerShell($label, $code) {
  $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($code))
  $shell = Join-Path $PSHOME "powershell.exe"   # Windows PowerShell; pwsh.exe under PowerShell 7
  if (-not (Test-Path $shell)) { $shell = Join-Path $PSHOME "pwsh.exe" }
  RunStep $label $shell @("-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", $encoded) $Home_
}

# The servers this launcher started, as "name=pid,start-ticks". The start time guards
# against a stale file after a restart, when the same pid may belong to something else.
function SaveState($entries) { Set-Content -Path $StateFile -Value $entries }
function TrayEntry { "tray=$PID,$((Get-Process -Id $PID).StartTime.Ticks)" }
# A launcher that adopts running servers records itself as their tray, so -Stop closes it.
function AdoptAsTray {
  if (Test-Path $StateFile) { SaveState (@(Get-Content $StateFile | Where-Object { $_ -notlike "tray=*" }) + (TrayEntry)) }
}

function StopServers([switch]$AndTray) {
  if (-not (Test-Path $StateFile)) { return }
  foreach ($line in Get-Content $StateFile) {
    $name, $rest = $line -split "=", 2
    if ($name -eq "tray" -and -not $AndTray) { continue }
    $id, $ticks = $rest -split ","
    $proc = Get-Process -Id $id -ErrorAction SilentlyContinue
    if ($proc -and "$($proc.StartTime.Ticks)" -eq $ticks) {
      # The whole tree: a venv's python.exe is a launcher that runs the real interpreter as
      # its child, and stopping the launcher alone would leave the API up.
      taskkill.exe /PID $id /T /F 2>&1 | Out-Null
    }
  }
  Remove-Item $StateFile -Force -ErrorAction SilentlyContinue
}

function Free($port) { -not (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) }
function IsOurApi($port) {
  try { return (Invoke-RestMethod "http://127.0.0.1:$port/api/health" -TimeoutSec 3).app -eq "espresso" } catch { return $false }
}
function IsOurWeb($port) {
  try { return (Invoke-WebRequest "http://127.0.0.1:$port/" -UseBasicParsing -TimeoutSec 5).Content -match "espresso" } catch { return $false }
}
function RunningWeb { 3000..3012 | Where-Object { -not (Free $_) -and (IsOurWeb $_) } | Select-Object -First 1 }
function RunningApi { 8000..8012 | Where-Object { -not (Free $_) -and (IsOurApi $_) } | Select-Object -First 1 }

function OpenBrowser($url) {
  if (-not $UI) { return }
  try { Start-Process $url }
  catch { if ($script:Tray) { $script:Tray.ShowBalloonTip(10000, "espresso", "Open $url in your browser.", [System.Windows.Forms.ToolTipIcon]::Info) } }
}

# ---------------------------------------------------------------------------------------
# The cup in the notification area
# ---------------------------------------------------------------------------------------

function RunTray {
  $tray = New-Object System.Windows.Forms.NotifyIcon
  $tray.Icon = $AppIcon; $tray.Text = "espresso"
  $menu = New-Object System.Windows.Forms.ContextMenuStrip
  $open = $menu.Items.Add("Open espresso"); $open.Font = Font 9 $true
  $open.add_Click({ Start-Process $script:Url })
  [void]$menu.Items.Add("-")
  $quit = $menu.Items.Add("Quit espresso")
  $quit.add_Click({ $script:Tray.Visible = $false; [System.Windows.Forms.Application]::Exit() })
  $tray.ContextMenuStrip = $menu
  $tray.add_MouseClick({ param($s, $e)
    if ($e.Button -eq [System.Windows.Forms.MouseButtons]::Left) { Start-Process $script:Url } })
  $tray.Visible = $true
  $script:Tray = $tray
  OpenBrowser $script:Url
  $tray.ShowBalloonTip(8000, "espresso is running",
    "Click the cup here to open espresso again. Right-click it to quit.", [System.Windows.Forms.ToolTipIcon]::Info)
  if ($env:ESPRESSO_TEST_QUIT) {
    # CI: show the tray, then quit through the same path as the menu.
    $timer = New-Object System.Windows.Forms.Timer; $timer.Interval = 4000
    $timer.add_Tick({ $script:Tray.Visible = $false; [System.Windows.Forms.Application]::Exit() }); $timer.Start()
  }
  [System.Windows.Forms.Application]::Run()
  $tray.Dispose()
  StopServers
  Log "quit"
}

# ---------------------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------------------

if ($Stop) { StopServers -AndTray; Log "stopped"; exit 0 }

Log "start $Version"
Write-Host "espresso"; Write-Host ""

# One launcher at a time. A second one while the first is still getting ready would install
# into the same folders; while espresso runs it only needs to open the browser.
$mutex = New-Object System.Threading.Mutex($false, "Local\espresso-launcher")
try { $owned = $mutex.WaitOne(0) }
catch { if ($_.Exception.InnerException -is [System.Threading.AbandonedMutexException]) { $owned = $true } else { throw } }
if (-not $owned) {
  $web = RunningWeb
  if ($web) { OpenBrowser "http://localhost:$web" }
  else { Notice "espresso is still getting ready. Your browser opens by itself when it is done." $false }
  exit 0
}

# Already running, left over from -NoUI or from a launcher that is gone: reuse it.
$web = RunningWeb; $apiUp = RunningApi
if ($web -and $apiUp) {
  $script:Url = "http://localhost:$web"
  Status "espresso is already running at $script:Url"
  if ($UI) { AdoptAsTray; RunTray }
  exit 0
}

# What a start has to do, decided up front so the window shows only when there is work.
function NodeMajor { try { [int]((& (Get-Command node).Source --version) -replace '^v(\d+).*', '$1') } catch { 0 } }
$haveUv = [bool](Get-Command uv -ErrorAction SilentlyContinue)
$haveNode = [bool](Get-Command node -ErrorAction SilentlyContinue) -and (NodeMajor) -ge 20
$be = Join-Path $Repo "backend"; $fe = Join-Path $Repo "frontend"
$beStamp = Join-Path $be ".venv\.espresso-installed"
$beHash = (Get-FileHash (Join-Path $be "uv.lock")).Hash
$feStamp = Join-Path $fe "node_modules\.espresso-installed"
$feHash = (Get-FileHash (Join-Path $fe "package-lock.json")).Hash
$buildStamp = Join-Path $fe ".next\.espresso-built"
function Stamped($stamp, $value) { (Test-Path $stamp) -and ((Get-Content $stamp -Raw).Trim() -eq $value) }
function BuildNeeded {
  if (-not (Stamped $buildStamp $Version)) { return $true }
  # A clone rebuilds when a source file changed; an installed copy by its version.
  $built = (Get-Item $buildStamp).LastWriteTime
  $dirs = @("app", "components", "lib", "public") | ForEach-Object { Join-Path $fe $_ } | Where-Object { Test-Path $_ }
  $files = @("next.config.ts", "package.json", "tsconfig.json", "postcss.config.mjs") |
    ForEach-Object { Join-Path $fe $_ } | Where-Object { Test-Path $_ } | ForEach-Object { Get-Item $_ }
  $newest = @(Get-ChildItem $dirs -Recurse -File) + @($files) | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  return $newest.LastWriteTime -gt $built
}
$needSetup = -not $haveUv -or -not $haveNode -or -not (Stamped $beStamp $beHash) -or -not (Stamped $feStamp $feHash) -or (BuildNeeded)
if ($UI -and $needSetup) { ShowProgress }

if (-not $haveUv) {
  $env:UV_INSTALL_DIR = Join-Path $Tools "bin"; $env:UV_NO_MODIFY_PATH = "1"
  $code = RunPowerShell "Downloading uv, which brings Python..." "irm https://astral.sh/uv/install.ps1 | iex"
  if ($code -ne 0 -or -not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Fail "Could not download uv. Check the internet connection, then start espresso again."
  }
}
if (-not $haveNode) {
  $arch = if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64" -or $env:PROCESSOR_ARCHITEW6432 -eq "ARM64") { "arm64" } else { "x64" }
  $name = "node-$NodeVersion-win-$arch"
  $zip = Join-Path $Tools "$name.zip"; $unpack = Join-Path $Tools "node-unpack"
  $env:ESPRESSO_DL_URL = "https://nodejs.org/dist/$NodeVersion/$name.zip"; $env:ESPRESSO_DL_OUT = $zip
  $code = RunPowerShell "Downloading Node.js..." ('$ProgressPreference = "SilentlyContinue"; ' +
    'Invoke-WebRequest -UseBasicParsing -Uri $env:ESPRESSO_DL_URL -OutFile $env:ESPRESSO_DL_OUT')
  if ($code -ne 0 -or -not (Test-Path $zip)) { Fail "Could not download Node.js. Check the internet connection, then start espresso again." }
  if (Test-Path $unpack) { Remove-Item $unpack -Recurse -Force }
  New-Item -ItemType Directory -Force -Path $unpack | Out-Null
  # tar.exe (Windows 10 1803 and later) unpacks the zip in seconds; Expand-Archive takes minutes.
  $tar = Get-Command tar.exe -ErrorAction SilentlyContinue
  if ($tar) { $code = RunStep "Unpacking Node.js..." $tar.Source @("-xf", $zip, "-C", $unpack) $Tools }
  else {
    $env:ESPRESSO_DL_DEST = $unpack
    $code = RunPowerShell "Unpacking Node.js..." 'Expand-Archive -LiteralPath $env:ESPRESSO_DL_OUT -DestinationPath $env:ESPRESSO_DL_DEST -Force'
  }
  if ($code -ne 0) { Fail "Could not unpack Node.js." }
  if (Test-Path "$Tools\node") { Remove-Item "$Tools\node" -Recurse -Force }
  Move-Item (Join-Path $unpack $name) "$Tools\node"
  Remove-Item $unpack, $zip -Recurse -Force
}
$uv = (Get-Command uv).Source
$node = if (Test-Path "$Tools\node\node.exe") { "$Tools\node\node.exe" } else { (Get-Command node).Source }
$npmCli = Join-Path (Split-Path $node) "node_modules\npm\bin\npm-cli.js"

if (-not (Stamped $beStamp $beHash)) {
  $code = RunStep "Installing the API's Python packages..." $uv @("sync", "--frozen", "--extra", "dev") $be
  if ($code -ne 0) { Fail "The API's packages did not install. The details are in setup.log." }
  Set-Content $beStamp $beHash
}
if (-not (Stamped $feStamp $feHash)) {
  $code = RunStep "Installing the web app's packages..." $node @($npmCli, "install", "--no-fund", "--no-audit") $fe
  if ($code -ne 0) { Fail "The web app's packages did not install. The details are in setup.log." }
  Set-Content $feStamp $feHash
}
if (BuildNeeded) {
  $code = RunStep "Building the web app..." $node @("node_modules\next\dist\bin\next", "build") $fe
  if ($code -ne 0) { Fail "The web app did not build. The details are in setup.log." }
  Set-Content $buildStamp $Version
}

# Ports: the defaults, stepping past ones that are taken.
$ApiPort = 8000; while (-not (Free $ApiPort) -and $ApiPort -lt 8012) { $ApiPort++ }
$WebPort = 3000; while (-not (Free $WebPort) -and $WebPort -lt 3012) { $WebPort++ }

# Both servers run from their own executables, not through npm or uv: Start-Process cannot
# run npm's .cmd and .ps1 shims with redirected output, and uv run re-checks the environment.
Status "Starting espresso..."
$env:API_PORT = "$ApiPort"
$api = Start-Process -PassThru -WindowStyle Hidden -WorkingDirectory $be `
  -FilePath (Join-Path $be ".venv\Scripts\python.exe") -ArgumentList "main.py" `
  -RedirectStandardOutput (Join-Path $Logs "api.log") -RedirectStandardError (Join-Path $Logs "api.err.log")
$env:API_URL = "http://127.0.0.1:$ApiPort"
$webProc = Start-Process -PassThru -WindowStyle Hidden -WorkingDirectory $fe -FilePath $node `
  -ArgumentList "node_modules\next\dist\bin\next start -H 127.0.0.1 -p $WebPort" `
  -RedirectStandardOutput (Join-Path $Logs "web.log") -RedirectStandardError (Join-Path $Logs "web.err.log")
SaveState @("api=$($api.Id),$($api.StartTime.Ticks)", "web=$($webProc.Id),$($webProc.StartTime.Ticks)", (TrayEntry))

# Open the browser only once both answer; earlier, it shows "can't reach this page".
function WaitFor($what, $probe, $proc, $log) {
  for ($i = 0; $i -lt 240; $i++) {
    if (& $probe) { return }
    if ($proc.HasExited) { Fail "The $what stopped while starting. The details are in $log." }
    Pump; Start-Sleep -Milliseconds 500
  }
  Fail "The $what did not start within two minutes. The details are in $log."
}
WaitFor "API" { IsOurApi $ApiPort } $api "api.err.log"
WaitFor "web app" { IsOurWeb $WebPort } $webProc "web.err.log"

$script:Url = "http://localhost:$WebPort"
CloseProgress
Status "espresso is running at $script:Url"
if ($UI) { RunTray }
exit 0
