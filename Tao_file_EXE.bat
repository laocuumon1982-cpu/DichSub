@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Tao file exe - Dich Viet by Duy Anh v3.1
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo Chua cai Python. Tai Python 3.12 tai https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^)
  pause
  exit /b 1
)
set "NAME=Dich Viet by Duy Anh"

echo [1/4] Cai cong cu build va thu vien (HachimiMT, Whisper)...
%PY% -m pip install -U pyinstaller ctranslate2 sentencepiece pypdf reportlab pillow faster-whisper opencc-python-reimplemented
if errorlevel 1 goto :loi
if exist build_out rmdir /s /q build_out

echo [2/4] Build ban 1 file exe...
set "DICHVIET_MODE=onefile"
%PY% -m PyInstaller --noconfirm --distpath build_out\onefile --workpath build_out\work1 "%~dp0DichViet.spec"
if errorlevel 1 goto :loi

echo [3/4] Build ban portable...
set "DICHVIET_MODE=onedir"
%PY% -m PyInstaller --noconfirm --distpath build_out\portable --workpath build_out\work2 "%~dp0DichViet.spec"
if errorlevel 1 goto :loi
set "PORT=build_out\portable\%NAME%"
> "%PORT%\portable.ini" echo [DichSub]
>> "%PORT%\portable.ini" echo ; Ban portable: cau hinh, model HachimiMT, Whisper va thu vien GPU luu trong thu muc data ben canh.
if not exist "%PORT%\data" mkdir "%PORT%\data"
copy /y HUONG_DAN.txt "%PORT%\" >nul

echo [4/4] Dong goi...
copy /y "build_out\onefile\%NAME%.exe" "%NAME%.exe" >nul
if exist "%NAME% Portable" rmdir /s /q "%NAME% Portable"
xcopy /e /i /q /y "%PORT%" "%NAME% Portable" >nul
powershell -NoProfile -Command "Compress-Archive -Path '%NAME% Portable' -DestinationPath '%NAME% Portable.zip' -Force"

echo.
echo ============================================================
echo  XONG!
echo  1) Ban 1 file:   %NAME%.exe
echo  2) Ban portable: thu muc "%NAME% Portable" (va file .zip)
echo     - Mo bang file "%NAME%.exe" ben trong thu muc do
echo     - Model, cau hinh luu ngay trong thu muc data, mang di USB duoc
echo ============================================================
explorer "%~dp0"
pause
exit /b 0

:loi
echo.
echo LOI khi build. Chup man hinh cua so nay gui lai de duoc ho tro.
echo Goi y: dung Python 3.12 hoac 3.13 ^(ban 3.14 co the chua co ctranslate2^).
pause
exit /b 1
