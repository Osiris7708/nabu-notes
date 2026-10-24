@echo off
cd /d "%~dp0"
set NOBU_HOME=%~dp0
set NOBU_EXE=%~dp0NobuNotes.exe
set PYTHONNOUSERSITE=1
if not exist "runtime\python.exe" (
  echo The runtime has not been unpacked yet. Double-click NobuNotes.exe once first.
  pause
  exit /b 1
)
"runtime\python.exe" "app\nobu_main.py"
echo.
echo Nobu Notes stopped. Details are in logs\nobu.log
pause
