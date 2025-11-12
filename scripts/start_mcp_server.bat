@echo off
echo ========================================
echo MCP Server Baslatiliyor...
echo ========================================
cd /d "%~dp0..\backend"
call ..\venv\Scripts\activate.bat
python mcp_server.py
pause
