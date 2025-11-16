@echo off
echo ========================================
echo Web Server Baslatiliyor...
echo ========================================

rem Proje kok dizininde kal
call .\myenv\Scripts\activate.bat

echo Calisma dizini: %cd%
echo Python komutu: python -m backend.main

python -m backend.main
pause
