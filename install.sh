#!/usr/bin/env bash
# ANIS Trans 설치 (Linux / macOS). 번들 폴더 안에 .venv 가상환경을 만든다.
#   ./install.sh            기본 (CTranslate2: CPU, 그리고 CUDA 12가 설치된 PC면 NVIDIA GPU)
#   ./install.sh --gpu      NVIDIA GPU용 cuBLAS도 pip로 설치 (CUDA 툴킷이 없을 때, 약 1GB)
set -euo pipefail
cd "$(dirname "$0")"
EXTRAS=""
add() { if [ -z "$EXTRAS" ]; then EXTRAS="$1"; else EXTRAS="$EXTRAS,$1"; fi; }
for a in "$@"; do
  case "$a" in
    --gpu) add gpu ;;
    -h|--help) sed -n 2,5p "$0"; exit 0 ;;
    *) echo "알 수 없는 옵션: $a" >&2; exit 2 ;;
  esac
done
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for c in python3.13 python3.12 python3.11 python3.10 python3.9 python3 python; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
      PY="$c"; break
    fi
  done
fi
if [ -z "$PY" ]; then
  echo "Python 3.9 이상을 찾지 못했습니다. https://www.python.org 에서 설치한 뒤 다시 실행하세요." >&2
  exit 1
fi
echo "Python: $(command -v "$PY") ($("$PY" -V))"
"$PY" -m venv .venv
.venv/bin/python -m pip install --upgrade pip >/dev/null
if [ -n "$EXTRAS" ]; then SPEC=".[$EXTRAS]"; else SPEC="."; fi
.venv/bin/python -m pip install -e "$SPEC"
chmod +x anis-trans anis-trans-gui "ANIS Trans GUI.command" 2>/dev/null || true
echo
.venv/bin/python -m anis_trans --info || true
echo
echo "설치 완료. 이 폴더에서:"
echo "  ./anis-trans \"今日は雨が降ってるね。\""
echo "  ./anis-trans-gui"
