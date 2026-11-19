@echo off
rem Start the desktop app from the source code (developers). Users install it with the setup program.
cd /d "%~dp0"
start "" pythonw -m randomizer_gui
