@echo off
echo ========================================
echo MCP Server Baslatiliyor...
echo ========================================
cd /d "%~dp0backend"
call ..\myenv\Scripts\activate.bat
python mcp_server.py
pause
