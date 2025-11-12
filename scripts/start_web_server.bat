@echo off
echo ========================================
echo Web Server Baslatiliyor...
echo ========================================

rem Betik dosyasinin bulundugu dizinden projenin kok dizinine gec
cd /d "%~dp0..\"

rem Sanal ortami etkinlestir (proje kok dizininde oldugu varsayilarak)
call .\venv\Scripts\activate.bat

echo Calisma dizini: %cd%
echo Python komutu: python -m backend.main

python -m backend.main
pause
