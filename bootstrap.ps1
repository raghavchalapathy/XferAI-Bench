<#
.SYNOPSIS
  Deprecated entry point kept for old instructions: a thin wrapper around xferAI_setup.ps1 (same parameters,
  same exit codes: 0 ready, 1 a step failed, 2 usage error). Use xferAI_setup.ps1 directly.
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
& (Join-Path $PSScriptRoot "xferAI_setup.ps1") @args
exit $LASTEXITCODE
