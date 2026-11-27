@echo off
echo ========================================================================
echo          Hikayat Web RPG - Private Tailscale Remote Play Mode
echo ========================================================================
echo.
echo Launching with private Tailscale access (no public internet exposure)...
echo Open the displayed Tailscale URL from your phone, tablet, or laptop on
echo any Wi-Fi or 4G/5G network while signed into Tailscale.
echo.
echo ========================================================================
cd /d "%~dp0.."
call venv\Scripts\activate.bat
python server.py --share --share-provider tailscale --no-reload %*
pause
