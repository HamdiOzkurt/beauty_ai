@echo off
echo ========================================
echo MCP Server Baslatiliyor...
echo ========================================
cd /d "%~dp0backend"
call ..\venv\Scripts\activate.bat

echo [2/2] MCP server baslatiliyor...
python mcp_server.py
pause
