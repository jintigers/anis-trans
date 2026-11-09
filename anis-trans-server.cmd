@echo off
rem ANIS Trans API 서버 실행기 (Windows)
set PYTHONUTF8=1
"%~dp0.venv\Scripts\python.exe" -m anis_trans.server %*
if errorlevel 1 pause
