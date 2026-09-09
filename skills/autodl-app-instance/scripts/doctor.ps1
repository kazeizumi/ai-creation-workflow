[CmdletBinding()]
param(
    [switch]$Probe
)

$ErrorActionPreference = 'Stop'
$missing = 0
$scriptRoot = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($scriptRoot)) {
    $scriptRoot = Split-Path -Parent $PSCommandPath
}
$instanceTool = Join-Path $scriptRoot 'autodl_instance.py'
$userProfilePath = $env:USERPROFILE
if ([string]::IsNullOrWhiteSpace($userProfilePath)) {
    $userProfilePath = [Environment]::GetFolderPath('UserProfile')
}
$envFile = $env:AUTODL_ENV_FILE
$defaultEnvFile = $null
if (-not [string]::IsNullOrWhiteSpace($userProfilePath)) {
    $defaultEnvFile = Join-Path $userProfilePath '.config\autodl.env'
}
if ([string]::IsNullOrWhiteSpace($envFile)) {
    $envFile = $defaultEnvFile
}

function Write-Check {
    param([bool]$Ok, [string]$Message)
    if ($Ok) {
        Write-Host "[OK] $Message"
    }
    else {
        Write-Host "[MISSING] $Message"
        $script:missing = 1
    }
}

$python = Get-Command python -ErrorAction SilentlyContinue
Write-Check ($null -ne $python) 'Python is available'

if ($python) {
    $pythonPath = if ($python.Path) { $python.Path } else { $python.Source }
    & $pythonPath -c 'import httpx' 2>$null
    Write-Check ($LASTEXITCODE -eq 0) 'Python package httpx is available'
}

$ffprobe = Get-Command ffprobe -ErrorAction SilentlyContinue
$bundledFfprobe = 'C:\tools\ffmpeg\ffprobe.exe'
if (-not $ffprobe -and (Test-Path -LiteralPath $bundledFfprobe)) {
    $ffprobe = Get-Item -LiteralPath $bundledFfprobe
}
Write-Check ($null -ne $ffprobe) 'ffprobe is available for downloaded-video validation'

$tokenPresent = -not [string]::IsNullOrWhiteSpace($env:AUTODL_TOKEN)
if (-not $tokenPresent -and -not [string]::IsNullOrWhiteSpace($envFile) -and (Test-Path -LiteralPath $envFile)) {
    $tokenPresent = [bool](Select-String -LiteralPath $envFile -Pattern '^\s*(?:export\s+)?AUTODL_TOKEN\s*=\s*\S+' -Quiet)
}
$tokenLocation = if ([string]::IsNullOrWhiteSpace($envFile)) { 'the environment' } else { "the environment or $envFile" }
Write-Check $tokenPresent "AUTODL_TOKEN is configured in $tokenLocation"
Write-Check (Test-Path -LiteralPath $instanceTool) 'autodl_instance.py exists'

if ($Probe -and $missing -eq 0) {
    Write-Host '[PROBE] Calling the read-only AutoDL instance-list endpoint'
    & $pythonPath $instanceTool list
    if ($LASTEXITCODE -ne 0) {
        $missing = 1
    }
}

exit $missing
