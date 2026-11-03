@echo off
cd /d "%~dp0"
set NABU_HOME=%~dp0
set NABU_EXE=%~dp0NabuNotes.exe
set PYTHONNOUSERSITE=1
if not exist "runtime\python.exe" (
  echo The runtime has not been unpacked yet. Double-click NabuNotes.exe once first.
  pause
  exit /b 1
)
"runtime\python.exe" "app\nabu_main.py"
echo.
echo Nabu Notes stopped. Details are in logs\nabu.log
pause
