@echo off
cd /d "%~dp0"
call venv\Scripts\activate
python stamp_version.py
pyinstaller --noconfirm --windowed --onefile --name TrendScout ^
  --add-data "universe\universe.csv;universe" ^
  main.py
copy /y dist\TrendScout.exe TrendScout.exe
echo.
echo Build complete. Exe is TrendScout.exe in this folder.
