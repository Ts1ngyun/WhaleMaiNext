$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:UV_CACHE_DIR = Join-Path $PSScriptRoot '.uv-cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $PSScriptRoot '.python'
& ./Prepare-Source.ps1

function Invoke-Checked([scriptblock]$Command) {
    & $Command
    if ($LASTEXITCODE -ne 0) { throw '安装命令失败，请查看上方错误。' }
}

if (!(Test-Path '.venv/Scripts/python.exe')) {
    Invoke-Checked { uv venv --python 3.12 .venv }
}
Invoke-Checked { uv pip sync --python .venv/Scripts/python.exe relay.lock.txt }
if (!(Test-Path 'MaiBot/.venv/Scripts/python.exe')) {
    Invoke-Checked { uv venv --python .venv/Scripts/python.exe MaiBot/.venv }
}
Invoke-Checked { uv pip sync --python MaiBot/.venv/Scripts/python.exe maibot.lock.txt }
Invoke-Checked { & .venv/Scripts/python.exe setup_local.py }
Set-Content -LiteralPath .setup-complete -Value '0.1.0' -Encoding ascii
