@echo off
rem Builds EnhancedExtract.exe in this folder. Needs Python with pyinstaller, pygame,
rem pillow and fusepy installed (only on the PC that builds, not on the PCs that run it).
cd /d "%~dp0"
python -m PyInstaller --noconfirm --clean --distpath . --workpath work EnhancedExtract.spec
rmdir /s /q work
