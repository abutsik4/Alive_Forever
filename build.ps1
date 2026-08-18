$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

python create_icon.py
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-build.txt
python -m PyInstaller --noconfirm --clean AliveForever.spec

$makensis = Get-Command makensis -ErrorAction SilentlyContinue
if (-not $makensis) {
    $bundled = Join-Path ${env:ProgramFiles(x86)} 'NSIS\makensis.exe'
    if (Test-Path $bundled) { $makensis = Get-Item $bundled }
}

if ($makensis) {
    & $makensis.FullName installer/AliveForever.nsi
    Write-Host "Installer written to dist/AliveForever-Setup.exe"
} else {
    Write-Host 'makensis not found. The installer script is ready at installer/AliveForever.nsi.'
}

Write-Host "Portable build: dist/AliveForever"
