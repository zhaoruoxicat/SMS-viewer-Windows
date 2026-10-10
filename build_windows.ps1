param(
    [string]$Python = "$PSScriptRoot\.venv\Scripts\python.exe",
    [string]$ISCC = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (!(Test-Path $Python)) { throw "Python not found: $Python" }
if (!(Test-Path $ISCC)) { throw "Inno Setup compiler not found: $ISCC" }
New-Item -ItemType Directory -Force build\windows | Out-Null
& $Python -c "from PIL import Image; Image.open('logo.png').save('build/windows/sms-client.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"
if ($LASTEXITCODE -ne 0) { throw 'Icon conversion failed' }
$version = & $Python -c "from sms_client import __version__; print(__version__)"
& $Python -m PyInstaller --noconfirm --clean --windowed --onedir --name SmsForwardClient --paths $PSScriptRoot --icon "$PSScriptRoot\build\windows\sms-client.ico" --add-data "$PSScriptRoot\logo.png;." --distpath dist --workpath build\windows\pyinstaller --specpath build\windows packaging\windows_entry.py
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
& $ISCC "/DAppVersion=$version" packaging\windows.iss
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup failed' }
$installer = "dist\sms-forward-client-$version-windows-x64-setup.exe"
$hash = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  $([IO.Path]::GetFileName($installer))" | Set-Content "$installer.sha256" -Encoding ASCII
Get-Item -LiteralPath $installer | Select-Object FullName, Length
