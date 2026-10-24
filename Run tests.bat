@echo off
rem Checks that Nobu still works: presses every button, tries every setting, exports, voice commands.
rem Your own notes and settings are never touched. Add  --quick  for the fast tests only.
cd /d "%~dp0"
set PYTHONNOUSERSITE=1
if not exist "runtime\python.exe" (
  echo The runtime has not been unpacked yet. Double-click NobuNotes.exe once first.
  pause
  exit /b 1
)
"runtime\python.exe" "tests\run_tests.py" %*
echo.
pause
