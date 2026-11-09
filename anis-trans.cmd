@echo off
rem ANIS Trans CLI 실행기 (Windows)
set PYTHONUTF8=1
"%~dp0.venv\Scripts\python.exe" -m anis_trans %*
