# Smoke-test a frozen ArtistReferenceManager.exe (Windows).
param(
    [string]$ExePath = "dist/ArtistReferenceManager.exe",
    [int]$WaitSeconds = 30
)

$ErrorActionPreference = "Stop"
$exe = Resolve-Path $ExePath
$workDir = Split-Path $exe -Parent
$dbPath = Join-Path $workDir "data/artist_reference.db"

if (Test-Path (Join-Path $workDir "data")) {
    Remove-Item -Recurse -Force (Join-Path $workDir "data")
}

$proc = Start-Process -FilePath $exe -WorkingDirectory $workDir -PassThru
Start-Sleep -Seconds $WaitSeconds

if (-not (Test-Path $dbPath)) {
    Stop-Process -Name "ArtistReferenceManager" -Force -ErrorAction SilentlyContinue
    throw "Expected database was not created at $dbPath"
}

Stop-Process -Name "ArtistReferenceManager" -Force -ErrorAction SilentlyContinue
Write-Host "Smoke test passed: process ran ${WaitSeconds}s and created data/artist_reference.db"
