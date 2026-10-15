# Create a project-local virtual environment, install xfer-bench into it and run `xferbench doctor`.
#
#   powershell -ExecutionPolicy Bypass -File bootstrap.ps1                 # this checkout (editable, dev tools)
#   powershell -ExecutionPolicy Bypass -File bootstrap.ps1 dist\xfer_bench-0.1.0-py3-none-any.whl
#
# The -ExecutionPolicy flag applies to this one invocation only; the script never changes system policy.
# Never installs globally and never overwrites an existing environment.
param(
    [string]$Target = "",
    [string]$Python = "py",
    [string]$Venv = ".venv"
)
$ErrorActionPreference = "Stop"

$pyArgs = @()
if ($Python -eq "py") { $pyArgs = @("-3.11") }
try { & $Python @pyArgs -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" }
catch { Write-Error "Python 3.11+ not found. Install it from https://www.python.org/downloads/ or pass -Python <path>."; exit 1 }
if ($LASTEXITCODE -ne 0) { Write-Error "xfer-bench needs Python 3.11 or newer."; exit 1 }
if (Test-Path $Venv) { Write-Error "'$Venv' already exists; refusing to modify it. Remove it or pass -Venv <new folder>."; exit 1 }

& $Python @pyArgs -m venv $Venv
$vpy = Join-Path $Venv "Scripts\python.exe"
& $vpy -m pip install --upgrade pip
if ($Target -eq "") { & $vpy -m pip install -e ".[dev]" } else { & $vpy -m pip install $Target }
& (Join-Path $Venv "Scripts\xferbench.exe") doctor --profile core
Write-Host ""
Write-Host "ready. Try: $Venv\Scripts\xferbench demo --preset tiny --out .\xb-demo"
