# ============================================================
#  JarDiff Windows packaging (PowerShell)
#  Run in PowerShell:  .\build_windows.ps1
#  Requires: Python 3.10+ (and JDK if you want .class decompiling)
#  Output:   dist\JarDiff\JarDiff.exe  (self-contained onedir)
#  Installer: compile packaging\jardiff_inno.iss with Inno Setup 6.1+
# ============================================================
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

Write-Host "[1/5] Checking Python..." -ForegroundColor Cyan
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python not found. Install Python 3.10+ and add it to PATH."
    exit 1
}

Write-Host "[2/5] Creating/reusing virtual env .venv-win ..." -ForegroundColor Cyan
if (-not (Test-Path ".venv-win\Scripts\python.exe")) {
    python -m venv .venv-win
}
$py = Join-Path $PSScriptRoot ".venv-win\Scripts\python.exe"

Write-Host "[3/5] Installing dependencies..." -ForegroundColor Cyan
& $py -m pip install --upgrade pip
& $py -m pip install -r packaging\requirements-windows.txt

Write-Host "[4/5] Generating icon.ico (if missing)..." -ForegroundColor Cyan
if (-not (Test-Path "jardiff_app\icon.ico")) {
    & $py make_icon.py
}

Write-Host "[5/5] PyInstaller packaging..." -ForegroundColor Cyan
if (Test-Path build) { Remove-Item -Recurse -Force build }
if (Test-Path dist)  { Remove-Item -Recurse -Force dist }
& $py -m PyInstaller --noconfirm jardiff.spec
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller failed (exit $LASTEXITCODE)."
    exit 1
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host " Done: dist\JarDiff\JarDiff.exe" -ForegroundColor Green
Write-Host " Installer: compile packaging\jardiff_inno.iss with Inno Setup" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
