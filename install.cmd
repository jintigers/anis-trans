@echo off
rem ANIS Trans 설치 (Windows). 번들 폴더 안에 .venv 가상환경을 만든다.
rem   install.cmd                 기본 (CTranslate2: CPU, 그리고 CUDA 12가 설치된 PC면 NVIDIA GPU)
rem   install.cmd --gpu           NVIDIA GPU용 cuBLAS도 pip로 설치 (CUDA 툴킷이 없을 때, 약 1GB)
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set EXTRAS=
:args
if "%~1"=="" goto argsdone
if /i "%~1"=="--gpu" (if defined EXTRAS (set "EXTRAS=%EXTRAS%,gpu") else (set "EXTRAS=gpu"))
shift
goto args
:argsdone
set SPEC=.
if defined EXTRAS set "SPEC=.[%EXTRAS%]"
set PY=
where py >nul 2>nul && set PY=py -3
if not defined PY (where python >nul 2>nul && set PY=python)
if not defined PY (
  echo Python 3.9 이상을 찾지 못했습니다. https://www.python.org 에서 설치할 때 "Add python.exe to PATH"를 켜 주세요.
  pause
  exit /b 1
)
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" || (echo Python 3.9 이상이 필요합니다. & pause & exit /b 1)
%PY% -m venv .venv || (pause & exit /b 1)
.venv\Scripts\python.exe -m pip install --upgrade pip >nul
.venv\Scripts\python.exe -m pip install -e "%SPEC%" || (pause & exit /b 1)
echo.
set PYTHONUTF8=1
.venv\Scripts\python.exe -m anis_trans --info
echo.
echo 설치 완료. 이 폴더에서:
echo   anis-trans "今日は雨が降ってるね。"
echo   anis-trans-gui      (또는 anis-trans-gui.cmd 두 번 클릭)
pause
