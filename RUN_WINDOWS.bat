@echo off
cd /d "%~dp0"
echo BANLAG - Local-only research prototype. NO external or SerpApi requests.
echo Open http://127.0.0.1:8765 when the server is ready.
python -m banlag
pause
