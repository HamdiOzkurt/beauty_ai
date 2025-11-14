@echo off
echo ========================================
echo MCP Server Baslatiliyor...
echo ========================================ssss
cd /d "%~dp0backend"
call ..\myvenv\Scripts\activate.bat
python mcp_server.py
pause
