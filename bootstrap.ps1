# Create or update a project-local environment, install xfer-bench into it and run `xferbench doctor`.
# Uses uv (https://docs.astral.sh/uv/) with the committed uv.lock when uv is on PATH; otherwise falls back to
# `python -m venv` + pip with constraints\core.txt (generated from uv.lock). Safe to re-run: an existing
# environment is updated in place, never deleted.
#
#   powershell -ExecutionPolicy Bypass -File bootstrap.ps1                 # this checkout (editable, dev tools)
#   powershell -ExecutionPolicy Bypass -File bootstrap.ps1 dist\xfer_bench-0.1.0-py3-none-any.whl
#   powershell -ExecutionPolicy Bypass -File bootstrap.ps1 -Extras dev,lightgbm -NoUv
#
# The -ExecutionPolicy flag applies to this one invocation only; the script never changes system policy.
# Exit codes: 0 ready, 1 no suitable Python, 2 bad usage (Venv exists but is not a virtual environment,
#             target missing), 3 install failed, 4 installed but `xferbench doctor` failed.
# Never installs globally. Set XFERBENCH_NO_UV=1 (or pass -NoUv) to force the pip fallback.
param(
    [string]$Target = "",
    [string]$Python = "",
    [string]$Venv = ".venv",
    [string[]]$Extras = @("dev"),
    [switch]$NoUv
)
$ErrorActionPreference = "Stop"

function Write-BootstrapError([int]$Code, [string]$Message) {
    [Console]::Error.WriteLine("bootstrap: error: $Message")
    exit $Code
}

if ($Target -ne "" -and -not (Test-Path $Target)) { Write-BootstrapError 2 "'$Target' not found (pass a wheel/sdist path or nothing)." }
if ($Target -eq "" -and -not (Test-Path "pyproject.toml")) { Write-BootstrapError 2 "run this from the repository root (pyproject.toml not found)." }
if ((Test-Path $Venv) -and -not (Test-Path (Join-Path $Venv "pyvenv.cfg"))) {
    Write-BootstrapError 2 "'$Venv' exists but is not a virtual environment; refusing to touch it. Remove it or pass -Venv <new folder>."
}
# Windows venvs use Scripts\; PowerShell 7 on Linux/macOS (used only to test this script) uses bin/.
$binDir = if ($IsLinux -or $IsMacOS) { "bin" } else { "Scripts" }
$exe = if ($IsLinux -or $IsMacOS) { "" } else { ".exe" }
$vpy = Join-Path (Join-Path $Venv $binDir) "python$exe"
$xb = Join-Path (Join-Path $Venv $binDir) "xferbench$exe"

$useUv = (-not $NoUv) -and (-not $env:XFERBENCH_NO_UV) -and [bool](Get-Command uv -ErrorAction SilentlyContinue)
if ($useUv) {
    Write-Output "bootstrap: using $(uv --version) (uv.lock); pass -NoUv to use pip instead"
    $env:UV_PROJECT_ENVIRONMENT = $Venv
    $pyOpt = @()
    if ($Python -ne "") { $pyOpt = @("--python", $Python) }
    if ($Target -eq "") {
        $exOpt = @()
        foreach ($e in $Extras) { $exOpt += @("--extra", $e) }
        & uv sync --locked @pyOpt @exOpt
        if ($LASTEXITCODE -ne 0) { Write-BootstrapError 3 "uv sync failed (if uv.lock is out of date: uv lock, then retry)." }
    } else {
        if (-not (Test-Path $Venv)) {
            & uv venv @pyOpt $Venv
            if ($LASTEXITCODE -ne 0) { Write-BootstrapError 3 "uv venv failed." }
        }
        & uv pip install --python $vpy $Target
        if ($LASTEXITCODE -ne 0) { Write-BootstrapError 3 "uv pip install $Target failed." }
    }
} else {
    Write-Output "bootstrap: uv not used; python -m venv + pip (install uv for the locked, faster path)"
    $pyCmd = $Python
    $pyArgs = @()
    if ($pyCmd -eq "") {
        if (Get-Command py -ErrorAction SilentlyContinue) { $pyCmd = "py"; $pyArgs = @("-3") } else { $pyCmd = "python3" }
    }
    if (-not (Get-Command $pyCmd -ErrorAction SilentlyContinue)) {
        Write-BootstrapError 1 "Python 3.11+ not found. Install it from https://www.python.org/downloads/ or pass -Python <path>."
    }
    & $pyCmd @pyArgs -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
    if ($LASTEXITCODE -ne 0) { Write-BootstrapError 1 "xfer-bench needs Python 3.11 or newer (pass -Python <path>)." }
    if (Test-Path $Venv) { Write-Output "bootstrap: updating existing $Venv" }
    else {
        & $pyCmd @pyArgs -m venv $Venv
        if ($LASTEXITCODE -ne 0) { Write-BootstrapError 3 "python -m venv failed." }
    }
    & $vpy -m pip install -q --upgrade pip
    if ($LASTEXITCODE -ne 0) { Write-BootstrapError 3 "pip upgrade failed." }
    if ($Target -eq "") {
        $spec = ".[" + ($Extras -join ",") + "]"
        & $vpy -m pip install -c constraints/core.txt -e $spec
        if ($LASTEXITCODE -ne 0) { Write-BootstrapError 3 "pip install -e '$spec' failed." }
    } else {
        & $vpy -m pip install $Target
        if ($LASTEXITCODE -ne 0) { Write-BootstrapError 3 "pip install $Target failed." }
    }
}

& $xb doctor --profile core
if ($LASTEXITCODE -ne 0) { Write-BootstrapError 4 "installed, but 'xferbench doctor --profile core' reported a problem (see above)." }
Write-Output ""
if ($useUv -and $Target -eq "" -and $Venv -eq ".venv") { Write-Output "bootstrap: ready. Try: uv run xferbench demo --preset tiny --out .\xb-demo" }
else { Write-Output "bootstrap: ready. Try: $xb demo --preset tiny --out .\xb-demo" }
exit 0
