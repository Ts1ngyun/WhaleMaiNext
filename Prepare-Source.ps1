$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$cache = Join-Path $PSScriptRoot '.sources'
New-Item -ItemType Directory -Path $cache -Force | Out-Null

function Expand-PinnedSource($Name, $Repository, $Commit, $Digest) {
    $destination = Join-Path $PSScriptRoot $Name
    if (Test-Path -LiteralPath $destination) { return }
    $archive = Join-Path $cache "$Name.zip"
    if (!(Test-Path -LiteralPath $archive)) {
        $download = "$archive.part"
        curl.exe --fail --location --silent --show-error --retry 2 --output $download "https://codeload.github.com/$Repository/zip/$Commit"
        if ($LASTEXITCODE) { throw "Unable to retrieve $Name at $Commit" }
        Move-Item -LiteralPath $download -Destination $archive
    }
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $Digest) {
        throw "SHA-256 mismatch for $Name"
    }
    $unpack = Join-Path $cache ([guid]::NewGuid().ToString('N'))
    Expand-Archive -LiteralPath $archive -DestinationPath $unpack
    $source = (Get-ChildItem -LiteralPath $unpack -Directory).FullName
    if ($Name -eq 'WhaleGirl') {
        foreach ($file in @('WhaleLauncher.exe','launcher/Assets/app.ico','launcher/Assets/app.png')) {
            $path = Join-Path $source $file
            if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path }
        }
        Get-ChildItem -LiteralPath 'upstream-overlay' -File -Recurse | ForEach-Object {
            $relative = $_.FullName.Substring((Resolve-Path 'upstream-overlay').Path.Length + 1)
            Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $source $relative)
        }
    }
    Move-Item -LiteralPath $source -Destination $destination
}

Expand-PinnedSource WhaleGirl Banan1cee/whale_girl ca5ad645b71460ee9c17171ecee3f8be673f68d1 AD945676C1C07244C5025A8CA924AC32EF8C0678B02E707D42C8C0B2BAF417BA
Expand-PinnedSource MaiBot Mai-with-u/MaiBot 478f671e64467121fd3e39205c8d3507b5ce0bd6 F015F0443F2AD1480846EA40F1B219DD381E8A62B30F592C79E80C62979AEFB0
