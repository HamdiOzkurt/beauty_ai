@echo off
echo ========================================
echo Web Server Baslatiliyor...
echo ========================================

rem Proje kok dizininde kal
call .\myenv\Scripts\activate.bat

echo [2/2] Web server baslatiliyor...
echo Calisma dizini: %cd%
echo Python komutu: python -m backend.main
echo.

python -m backend.main
pause
