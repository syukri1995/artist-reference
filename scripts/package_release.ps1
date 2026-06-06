# Package a local release zip (run after pyinstaller from repo root).
param(
    [string]$DistDir = "dist"
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$dist = Join-Path $root $DistDir
$exe = Join-Path $dist "ArtistReferenceManager.exe"
if (-not (Test-Path $exe)) {
    throw "Build the exe first: pyinstaller --noconfirm artist_ref_manager.spec"
}

Copy-Item (Join-Path $root "release/README.txt") (Join-Path $dist "README.txt") -Force
Copy-Item (Join-Path $root "LICENSE") (Join-Path $dist "LICENSE") -Force
Copy-Item (Join-Path $root "NOTICES.txt") (Join-Path $dist "NOTICES.txt") -Force
Copy-Item (Join-Path $root ".env.example") (Join-Path $dist ".env.example") -Force

$zip = Join-Path $dist "ArtistReferenceManager-win64.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }

Compress-Archive -Path @(
    $exe,
    (Join-Path $dist "README.txt"),
    (Join-Path $dist "LICENSE"),
    (Join-Path $dist "NOTICES.txt"),
    (Join-Path $dist ".env.example")
) -DestinationPath $zip -Force

Write-Host "Created $zip"
