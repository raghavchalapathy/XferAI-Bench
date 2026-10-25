<#
.SYNOPSIS
  One-command setup for XferAI-Bench on Windows (PowerShell 5.1 or 7+). Mirrors xferAI_setup.sh.
.DESCRIPTION
  Run from the repository root:  powershell -ExecutionPolicy Bypass -File xferAI_setup.ps1
  Checks git and Python, gets uv if needed, installs into .\.venv from uv.lock (or with pip as a fallback),
  runs `xferbench doctor --profile core` and a tiny offline demo. Touches only .\.venv, .\.xferai-setup.log,
  .\xb-demo and (if it installs uv) uv's own user folder. No administrator rights, no system changes,
  no profile or PATH changes. Exit codes: 0 ready, 1 a step failed, 2 usage error.
#>
[CmdletBinding()]
param(
    [string]$Python = "",
    [switch]$NoInstallUv,
    [switch]$WithLightgbm,
    [switch]$WithSpark,
    [switch]$NoDemo,
    [switch]$YesOwnData,
    [switch]$NonInteractive,
    [switch]$DryRun,
    [switch]$Quiet,
    [switch]$Help,
    [switch]$Version,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$SetupVersion = "1.0.0"
$UvVersion = "0.13.5"
$UvInstallerUrl = "https://astral.sh/uv/$UvVersion/install.ps1"
# astral publishes no checksum for its installer scripts; this is the sha256 we observed on 2026-10-24.
$UvInstallerSha256Observed = "84b66aa3018e9d800886543380d967bb3fb9652cfb251cfa5f3c73f4e62f59f2"
$Total = 7
$Log = ".xferai-setup.log"
$Venv = ".venv"
$script:Step = 0
$script:StepName = "start"

function Show-Usage {
    Write-Output @'
Usage: powershell -ExecutionPolicy Bypass -File xferAI_setup.ps1 [options]

Sets up XferAI-Bench in .\.venv. No options are required. Safe to run again.
  -Python VERSION|PATH  Python to use (3.11 or newer), e.g. 3.13
  -NoInstallUv          Do not install uv; use python -m venv + pip if uv is missing
  -WithLightgbm         Also install the lightgbm extra
  -WithSpark            Also install the distributed (Spark) extra
  -NoDemo               Skip the offline demo
  -YesOwnData           Print the "your own data" instructions without asking
  -NonInteractive       Never ask (also automatic when CI is set or input is redirected)
  -DryRun               Show what would be done, change nothing
  -Quiet                Only print failures and the final summary
  -Verbose              Also show the output of every command (always written to .xferai-setup.log)
  -Version              Print the setup script version
  -Help                 Show this help
Exit codes: 0 ready, 1 a step failed, 2 usage error.
'@
}

if ($Rest) { [Console]::Error.WriteLine("xferAI_setup: unknown option '$($Rest[0])'. Run with -Help for the options."); exit 2 }
if ($Help) { Show-Usage; exit 0 }
if ($Version) { Write-Output "xferAI_setup.ps1 $SetupVersion (uv $UvVersion)"; exit 0 }
$Verbose = $PSBoundParameters.ContainsKey("Verbose")
if ($Quiet -and $Verbose) { [Console]::Error.WriteLine("xferAI_setup: -Quiet and -Verbose cannot be combined"); exit 2 }
if (-not ((Test-Path pyproject.toml) -and (Test-Path uv.lock))) {
    [Console]::Error.WriteLine("xferAI_setup: run this from the XferAI-Bench folder (pyproject.toml and uv.lock not found here)"); exit 2
}

# Symbols: UTF-8 console -> check marks, otherwise ASCII (older Windows consoles).
$utf8 = $false
try { $utf8 = ([Console]::OutputEncoding.CodePage -eq 65001) } catch { $utf8 = $false }
if ($utf8) { $OkMark = [string][char]0x2713; $BadMark = [string][char]0x2717 } else { $OkMark = "[ok]"; $BadMark = "[x]" }
$useColor = (-not $env:NO_COLOR) -and (-not [Console]::IsOutputRedirected)

function Write-Say([string]$Text) { if (-not $Quiet) { Write-Output $Text } }
function Add-SetupLog([string]$Text) { Add-Content -Path $Log -Value $Text -Encoding utf8 }
function Show-StepStart([string]$Name) { $script:Step++; $script:StepName = $Name; Add-SetupLog "== [$($script:Step)/$Total] $Name" }
function Write-Ok([string]$Detail = "") {
    $d = if ($Detail) { " - $Detail" } else { "" }
    $line = "[$($script:Step)/$Total] $OkMark $($script:StepName)$d"
    if ($Quiet) { return }
    if ($useColor) { Write-Output "$([char]27)[32m$line$([char]27)[0m" } else { Write-Output $line }
    Add-SetupLog "ok: $line"
}
function Write-Fail([string]$What, [string]$Fix) {
    [Console]::Error.WriteLine("[$($script:Step)/$Total] $BadMark $($script:StepName): $What")
    [Console]::Error.WriteLine("  Fix: $Fix")
    [Console]::Error.WriteLine("  Full log: $(Join-Path (Get-Location) $Log)")
    Add-SetupLog "FAILED: $($script:StepName): $What | fix: $Fix"
    exit 1
}
function Invoke-Logged([string]$Exe, [string[]]$Arguments) {
    Add-SetupLog "`$ $Exe $($Arguments -join ' ')"
    $ErrorActionPreference = "Continue"
    if ($Verbose) { & $Exe @Arguments 2>&1 | Tee-Object -FilePath $Log -Append | Out-Host }
    else { & $Exe @Arguments *>> $Log }
    return ($LASTEXITCODE -eq 0)
}
trap {
    [Console]::Error.WriteLine("[$($script:Step)/$Total] $BadMark $($script:StepName): unexpected error: $_")
    [Console]::Error.WriteLine("  Fix: read the log, fix the cause, then run xferAI_setup.ps1 again (it is safe to re-run).")
    [Console]::Error.WriteLine("  Full log: $(Join-Path (Get-Location) $Log)")
    exit 1
}

Set-Content -Path $Log -Value "xferAI_setup.ps1 $SetupVersion started $(Get-Date -Format o)" -Encoding utf8

# ---- detect (no changes) ----
$arch = $env:PROCESSOR_ARCHITECTURE
$os = [System.Environment]::OSVersion.VersionString
$isWin = ($env:OS -eq "Windows_NT")
$bin = if ($isWin) { Join-Path $Venv "Scripts" } else { Join-Path $Venv "bin" }
function Find-Python {
    $cands = @()
    if ($Python) {
        if ($Python -match '^[0-9]') { $cands = @(@("py", "-$Python"), @("python$Python")) } else { $cands = @(, @($Python)) }
    } else { $cands = @(@("py", "-3"), @("python"), @("python3")) }
    foreach ($c in $cands) {
        $exe = $c[0]; $pre = @($c | Select-Object -Skip 1)
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        $v = & $exe @pre -c "import sys; print('%d.%d.%d' % sys.version_info[:3])" 2>$null
        if ($LASTEXITCODE -eq 0 -and $v) { return , @($exe, $pre, "$v".Trim()) }
    }
    return $null
}
$py = Find-Python
$haveUv = [bool](Get-Command uv -ErrorAction SilentlyContinue)
$mode = if ($haveUv) { "uv" } elseif (-not $NoInstallUv) { "uv-install" } else { "pip" }
$extras = @("dev"); if ($WithLightgbm) { $extras += "lightgbm" }; if ($WithSpark) { $extras += "distributed" }
$interactive = -not ($NonInteractive -or $env:CI -or [Console]::IsInputRedirected)
$pyText = if ($py) { "$($py[2]) ($($py[0]))" } else { "not found" }
$uvText = if ($haveUv) { "$(uv --version)" } else { "not found" }
Add-SetupLog "detected: os=$os arch=$arch python=$pyText uv=$uvText mode=$mode extras=$($extras -join ',') interactive=$interactive"

Write-Say "XferAI-Bench setup: checks git and Python, gets uv if needed, installs into .\.venv, runs a health check and a tiny offline demo."
Write-Say "Measured on a Linux box with a fast connection: about 20 s with uv, 30 s with pip, 13 s when re-run (slower networks take longer)."
Write-Say "Detected: $os $arch, Python $pyText, uv $uvText"
Write-Say "Plan:"
$exArgs = @(); foreach ($e in $extras) { $exArgs += @("--extra", $e) }
switch ($mode) {
    "uv" { Write-Say "  - use uv: uv sync --locked $($exArgs -join ' ') into $Venv" }
    "uv-install" { Write-Say "  - install uv $UvVersion for your user only (from $UvInstallerUrl), then uv sync --locked $($exArgs -join ' ')" }
    "pip" { Write-Say "  - no uv: python -m venv $Venv, then pip install -c constraints/core.txt -e .[$($extras -join ',')]" }
}
Write-Say "  - run: xferbench doctor --profile core"
if (-not $NoDemo) { Write-Say "  - run: xferbench demo --preset tiny --out xb-demo (offline, synthetic)" }
if ($DryRun) { Write-Say "Dry run: nothing was changed."; exit 0 }
Write-Say ""

Show-StepStart "Check git"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Write-Fail "git was not found" "install git (https://git-scm.com/downloads), then run this again" }
Write-Ok "$(git --version)"

Show-StepStart "Check Python 3.11+"
if ($py) {
    $parts = $py[2].Split(".")
    if ([int]$parts[0] -lt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -lt 11)) {
        Write-Fail "Python $($py[2]) is too old; 3.11 or newer is needed" "install Python 3.11+ or pass -Python 3.11"
    }
    Write-Ok $pyText
} elseif ($mode -ne "pip") { Write-Ok "none found; uv will download a Python 3.11+ into its own folder" }
else { Write-Fail "no Python 3.11 or newer found" "install Python 3.11+ (https://www.python.org/downloads/) or drop -NoInstallUv so uv can provide one" }

Show-StepStart "Get uv"
if ($mode -eq "uv") { Write-Ok "already installed: $uvText" }
elseif ($mode -eq "pip") { Write-Ok "skipped (-NoInstallUv); using pip instead" }
else {
    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("uv-installer-" + [guid]::NewGuid().ToString() + ".ps1")
    Write-Say "  downloading the uv $UvVersion installer: $UvInstallerUrl"
    try { Invoke-WebRequest -UseBasicParsing -Uri $UvInstallerUrl -OutFile $tmp }
    catch { Write-Fail "could not download $UvInstallerUrl" "check your connection or proxy (HTTPS_PROXY), or run with -NoInstallUv" }
    $got = (Get-FileHash -Algorithm SHA256 -Path $tmp).Hash.ToLowerInvariant()
    $want = if ($env:XFERAI_UV_INSTALLER_SHA256) { $env:XFERAI_UV_INSTALLER_SHA256 } else { $UvInstallerSha256Observed }
    Write-Say "  installer sha256: $got"
    Write-Say "  expected:         $want (observed 2026-10-24; astral publishes no installer checksum)"
    if ($got -ne $want) {
        Remove-Item $tmp -Force
        Write-Fail "the downloaded installer does not match the expected sha256" "do not run it; install uv yourself (https://docs.astral.sh/uv/getting-started/installation/) or use -NoInstallUv"
    }
    $env:UV_NO_MODIFY_PATH = "1"
    $shell = if (Get-Command pwsh -ErrorAction SilentlyContinue) { "pwsh" } else { "powershell" }
    $okInst = Invoke-Logged $shell @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $tmp)
    Remove-Item $tmp -Force
    if (-not $okInst) { Write-Fail "the uv installer failed" "see the log, or run with -NoInstallUv to use pip" }
    foreach ($d in @($env:UV_INSTALL_DIR, (Join-Path $HOME ".local\bin"), (Join-Path $HOME ".cargo\bin"))) {
        if ($d -and (Test-Path (Join-Path $d "uv.exe"))) { $env:PATH = "$d;$env:PATH"; break }
    }
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { Write-Fail "uv was installed but is not on PATH" "add %USERPROFILE%\.local\bin to PATH, then run this again" }
    Write-Ok "installed $(uv --version) (PATH and profile were not changed)"
    $mode = "uv"
}

Show-StepStart "Create $Venv"
if ((Test-Path $Venv) -and -not (Test-Path (Join-Path $Venv "pyvenv.cfg"))) { Write-Fail "$Venv exists but is not a virtual environment" "move or delete $Venv, then run this again" }
if (Test-Path (Join-Path $Venv "pyvenv.cfg")) { Write-Ok "reusing the existing $Venv" }
elseif ($mode -eq "uv") {
    $a = @("venv"); if ($Python) { $a += @("--python", $Python) }; $a += $Venv
    if (-not (Invoke-Logged "uv" $a)) { Write-Fail "uv venv failed" "pass -Python 3.11 (or newer), or see the log" }
    Write-Ok "created with uv"
} else {
    if (-not (Invoke-Logged $py[0] (@($py[1]) + @("-m", "venv", $Venv)))) { Write-Fail "python -m venv failed" "see the log" }
    Write-Ok "created with $($py[0])"
}

Show-StepStart "Install XferAI-Bench (extras: $($extras -join ' '))"
if ($mode -eq "uv") {
    $env:UV_PROJECT_ENVIRONMENT = $Venv
    $a = @("sync", "--locked") + $exArgs; if ($Python) { $a += @("--python", $Python) }
    if (-not (Invoke-Logged "uv" $a)) { Write-Fail "uv sync --locked failed" "if uv.lock is out of date run 'uv lock', or see the log" }
    Write-Ok "from uv.lock"
} else {
    $vpy = Join-Path $bin "python"
    if (-not (Invoke-Logged $vpy @("-m", "pip", "install", "-q", "--upgrade", "pip"))) { Write-Fail "pip could not be upgraded" "check your connection or PIP_INDEX_URL" }
    if (-not (Invoke-Logged $vpy @("-m", "pip", "install", "-c", "constraints/core.txt", "-e", ".[$($extras -join ',')]"))) { Write-Fail "pip install failed" "check your connection or PIP_INDEX_URL, or see the log" }
    Write-Ok "with pip and constraints/core.txt"
}

$xb = Join-Path $bin "xferbench"
Show-StepStart "Health check (xferbench doctor --profile core)"
if (-not (Invoke-Logged $xb @("doctor", "--profile", "core"))) { Write-Fail "doctor reported a problem" "read the doctor output in the log; re-run this script to repair the install" }
Write-Ok "profile core satisfied"

Show-StepStart "Offline demo (tiny synthetic data)"
if (-not $NoDemo) {
    if (Test-Path xb-demo) { Remove-Item -Recurse -Force xb-demo }
    if (-not (Invoke-Logged $xb @("demo", "--preset", "tiny", "--out", "xb-demo"))) { Write-Fail "the demo failed" "see the log; run with -NoDemo to skip it" }
    Write-Ok "open $(Join-Path xb-demo report.html)"
} else { Write-Ok "skipped (-NoDemo)" }

if ($Quiet) { Write-Output "XferAI-Bench is ready in $Venv ($mode, extras: $($extras -join ' '))."; exit 0 }
Write-Output ""
Write-Output "Done. Installed XferAI-Bench into $Venv with $mode (extras: $($extras -join ' ')); doctor passed."
if (-not $NoDemo) { Write-Output "The tiny demo report is at $(Join-Path xb-demo report.html). Setup log: $Log" }
Write-Output ""
Get-Content -Encoding utf8 setup\next_demo.txt | Write-Output
Write-Output ""
if ($YesOwnData) { Write-Output ""; Get-Content -Encoding utf8 setup\own_data.txt | Write-Output }
elseif ($interactive) {
    $answer = Read-Host "Do you want to run on your own data? [y/N]"
    if ($answer -match '^(y|yes)$') { Write-Output ""; Get-Content -Encoding utf8 setup\own_data.txt | Write-Output }
    else { Write-Output "OK. Start with the demo above: docs/GETTING_STARTED.md Step 1, and experiments/README.md." }
} else {
    Write-Output "(Not asking about your own data: non-interactive. Run with -YesOwnData, or see docs/GETTING_STARTED.md Step 2.)"
}
exit 0
