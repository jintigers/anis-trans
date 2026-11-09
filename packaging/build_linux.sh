#!/usr/bin/env bash
# Linux 독립 실행판 빌드. 결과: release/anis-trans-<버전>-linux-<arch>.tar.gz
#   packaging/build_linux.sh [--with-cublas]
# 오래된 배포판에서도 돌게 하려면 가능한 한 오래된 glibc를 가진 시스템(예: Rocky/Alma 8)에서 빌드한다.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"
"$PY" -m venv .build-venv
.build-venv/bin/python -m pip install --upgrade pip >/dev/null
EXTRA="build"
for a in "$@"; do [ "$a" = "--with-cublas" ] && EXTRA="build,gpu"; done
.build-venv/bin/python -m pip install -e ".[$EXTRA]"
.build-venv/bin/python packaging/build.py "$@"
