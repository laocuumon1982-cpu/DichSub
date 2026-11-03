@echo off
cd /d "%~dp0"
where py >nul 2>nul && py -3 -c "import reportlab, PIL, pypdf, faster_whisper, opencc, rapidocr" >nul 2>nul || py -3 -m pip install -q reportlab pillow pypdf faster-whisper opencc-python-reimplemented rapidocr >nul 2>nul
where pyw >nul 2>nul && (start "" pyw -3 dich_viet.py & exit /b)
where pythonw >nul 2>nul && (start "" pythonw dich_viet.py & exit /b)
echo Chua cai Python 3. Tai tai https://www.python.org/downloads/ (nho tick "Add python.exe to PATH").
pause
