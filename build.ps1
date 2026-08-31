# Build the OST single-file binary on Windows.
# Usage:   powershell -ExecutionPolicy Bypass -File .\build.ps1
# Output:  dist\ost.exe
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)

$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) { throw "python not found on PATH" }

$Venv = ".build-venv"
if (-not (Test-Path $Venv)) {
    Write-Host ">> creating venv"
    python -m venv $Venv
}

& "$Venv\Scripts\Activate.ps1"

Write-Host ">> installing project + build deps"
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -e ".[all]" pyinstaller

Write-Host ">> building binary"
python -m PyInstaller --noconfirm --clean ost.spec

Write-Host ""
Write-Host ">> DONE: $((Get-Location).Path)\dist\ost.exe"
Write-Host "   try it:     .\dist\ost.exe list"
Write-Host "   launch TUI: .\dist\ost.exe"