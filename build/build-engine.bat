@echo off
rem Builds the engine folder for the Tauri app: build\dist\ee-engine\ee-engine.exe (+ _internal).
rem Needs Python with pyinstaller and fusepy (only on the PC that builds). Then: cd ui && npm run tauri build
cd /d "%~dp0"
python -m PyInstaller --noconfirm --clean --distpath dist --workpath work-engine ee-engine.spec || exit /b 1
rmdir /s /q work-engine
