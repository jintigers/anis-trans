@echo off
rem Windows 독립 실행판 빌드. 결과: release\anis-trans-<버전>-windows-x86_64.zip
rem   packaging\build_windows.cmd [--with-cublas]
rem python.org 의 Python 3.10~3.12 (64비트)를 권장한다.
rem --with-cublas : NVIDIA GPU용 cuBLAS DLL을 함께 넣는다 (약 +1GB). 넣지 않으면 GPU를 쓰려는 PC에 CUDA 12가 있어야 한다.
setlocal
chcp 65001 >nul
cd /d "%~dp0.."
set PY=
where py >nul 2>nul && set PY=py -3
if not defined PY set PY=python
%PY% -m venv .build-venv || exit /b 1
.build-venv\Scripts\python.exe -m pip install --upgrade pip >nul
set EXTRA=build
if /i "%~1"=="--with-cublas" set EXTRA=build,gpu
.build-venv\Scripts\python.exe -m pip install -e ".[%EXTRA%]" || exit /b 1
.build-venv\Scripts\python.exe packaging\build.py %* || exit /b 1
