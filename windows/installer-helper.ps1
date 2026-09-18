# Run by the espresso installer and uninstaller, never by hand.
#
#   -Action stop           stop a running espresso before its files change
#   -Action upgrade-clean  before installing over an earlier version: remove its code, keep
#                          the papers (backend\data), settings (backend\.env) and installed
#                          packages (backend\.venv, frontend\node_modules)
#   -Action keep-data      uninstalling while keeping the papers: remove everything else
#
# It only ever touches a folder that holds an espresso install.

param(
  [Parameter(Mandatory = $true)][ValidateSet("stop", "upgrade-clean", "keep-data")][string]$Action,
  [Parameter(Mandatory = $true)][string]$InstallDir
)
$ErrorActionPreference = "Continue"
$launcher = Join-Path $InstallDir "windows\espresso.ps1"
if (-not (Test-Path -LiteralPath $launcher)) { exit 0 }

# Everything under $root except the named children of the named folders.
function Clear-Except($root, $keep) {
  foreach ($item in Get-ChildItem -LiteralPath $root -Force) {
    if ($keep.ContainsKey($item.Name)) {
      foreach ($sub in Get-ChildItem -LiteralPath $item.FullName -Force) {
        if ($keep[$item.Name] -notcontains $sub.Name) { Remove-Item -LiteralPath $sub.FullName -Recurse -Force }
      }
    } else {
      Remove-Item -LiteralPath $item.FullName -Recurse -Force
    }
  }
}

switch ($Action) {
  "stop" { & $launcher -Stop }
  "upgrade-clean" { Clear-Except $InstallDir @{ "backend" = @("data", ".env", ".venv"); "frontend" = @("node_modules") } }
  "keep-data" { Clear-Except $InstallDir @{ "backend" = @("data", ".env") } }
}
exit 0
