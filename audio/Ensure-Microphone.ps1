param([switch]$CheckOnly)
$ErrorActionPreference='Stop'
try {
    Add-Type -Path (Join-Path $PSScriptRoot 'DefaultMicrophone.cs')
    [DefaultMicrophone]::Ensure(-not $CheckOnly)
} catch {
    Write-Error $_.Exception.Message
    exit 1
}
