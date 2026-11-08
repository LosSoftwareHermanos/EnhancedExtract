@echo off
rem Starts the EnhancedExtract desktop app (ui\, Tauri) from source, using the Python engine
rem in this folder, so no engine build is needed. The first start compiles the Rust side and
rem takes a few minutes; later starts are quick. Keep this window open while the app runs.
rem The old Tkinter app still starts with: pythonw app.py
cd /d "%~dp0ui"

where cargo >nul 2>nul
if errorlevel 1 (
  echo Rust is not installed. Get it from https://rustup.rs and run this again.
  pause
  exit /b 1
)

rem The app's bundle settings list the packaged engine folder, which only exists after
rem build\build-engine.bat. From source the Python engine is used, so an empty folder will do.
if not exist "%~dp0build\dist\ee-engine" mkdir "%~dp0build\dist\ee-engine"

if not exist node_modules\.bin\tauri.cmd (
  echo Installing the UI's packages, once...
  call npm install --no-audit --no-fund
  if errorlevel 1 (
    pause
    exit /b 1
  )
)

call npm run tauri dev
if errorlevel 1 pause
