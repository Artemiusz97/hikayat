@echo off
echo ========================================================================
echo          Hikayat Web RPG - Public Link Sharing Mode
echo ========================================================================
echo.
echo Launching with Automatic1111 / Forge WebUI style Cloudflare Tunnel...
echo A public https://*.trycloudflare.com link will be generated automatically.
echo Anyone with that link can play from any phone, PC, or network!
echo.
echo ========================================================================
cd /d "%~dp0"
call venv\Scripts\activate.bat
python server.py --share
pause
