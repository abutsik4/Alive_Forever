$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

python create_icon.py
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --clean AliveForever.spec

$makensis = Get-Command makensis -ErrorAction SilentlyContinue
if ($makensis) {
    & $makensis.Source installer/AliveForever.nsi
} else {
    Write-Host 'makensis not found. The installer script is ready at installer/AliveForever.nsi.'
}