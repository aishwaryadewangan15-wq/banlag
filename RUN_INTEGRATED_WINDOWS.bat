@echo off
setlocal
cd /d "%~dp0"
if not exist "run_integrated.py" (
  if not exist "BANLAG_INTEGRATED_APP.zip" (
    echo Missing run_integrated.py and BANLAG_INTEGRATED_APP.zip.
    pause
    exit /b 2
  )
  echo Extracting integrated BANLAG files in this folder...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -LiteralPath '%~dp0BANLAG_INTEGRATED_APP.zip' -DestinationPath '%~dp0' -Force"
  if errorlevel 1 (
    echo Extraction failed.
    pause
    exit /b 3
  )
)
echo Starting integrated BANLAG...
echo Leave this window open while using the app.
echo Open the local browser URL printed below.
python -B run_integrated.py
set "EXITCODE=%ERRORLEVEL%"
echo.
echo Integrated BANLAG stopped with exit code %EXITCODE%.
pause
exit /b %EXITCODE%
