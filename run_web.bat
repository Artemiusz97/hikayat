@echo off
echo =======================================================
echo          Hikayat Web RPG Server
echo =======================================================
echo.
echo  - To play on THIS PC, open your browser to:
echo    http://localhost:8000
echo.
echo  - To play on your SMARTPHONE (Same Wi-Fi), open:
echo    http://192.168.0.141:8000
echo.
echo  - To share with friends OUTSIDE your Wi-Fi (Automatic1111/Forge style):
echo    Run: run_web.bat --share
echo    Or double-click: run_web_share.bat
echo.
echo =======================================================
cd /d "%~dp0"
call venv\Scripts\activate.bat
python server.py %*
pause
