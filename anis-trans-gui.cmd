@echo off
rem ANIS Trans 웹 GUI 실행기 (Windows) - 두 번 클릭해도 된다
set PYTHONUTF8=1
"%~dp0.venv\Scripts\python.exe" -m anis_trans.web %*
if errorlevel 1 pause
