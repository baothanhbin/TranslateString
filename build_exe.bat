@echo off
setlocal

python -m pip install --upgrade pyinstaller
python -m PyInstaller --clean --onefile --windowed --name StringTranslator translate_strings.py

echo.
echo Build done: dist\StringTranslator.exe
