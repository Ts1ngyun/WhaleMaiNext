param([string]$DotNet = 'dotnet')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& ./Prepare-Source.ps1
$env:DOTNET_CLI_HOME = Join-Path $PSScriptRoot '.dotnet-home'
$env:NUGET_PACKAGES = Join-Path $PSScriptRoot '.nuget'
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$env:DOTNET_GENERATE_ASPNET_CERTIFICATE = 'false'
& $DotNet publish voice-worker/WhaleMaiVoiceWorker.csproj -c Release -o .voice-build -r win-x64 -p:PublishSingleFile=true -p:SelfContained=false -p:ContinuousIntegrationBuild=true -p:RestoreLockedMode=true
if ($LASTEXITCODE) { throw 'Voice worker build failed' }
Copy-Item -LiteralPath .voice-build/WhaleMaiVoiceWorker.exe -Destination WhaleGirl/WhaleMaiVoiceWorker.exe -Force
