@echo off
rem Builds dist\SiebDiff.exe, the single file that is shared with users.
cd /d "%~dp0"
".venv\Scripts\pyinstaller.exe" --noconfirm --clean --onefile --console --name SiebDiff ^
  --add-data "web;web" ^
  --hidden-import cryptography.hazmat.primitives.kdf.pbkdf2 ^
  --hidden-import secrets --hidden-import getpass --hidden-import uuid ^
  run.py
