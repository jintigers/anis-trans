#!/usr/bin/env bash
# macOS 독립 실행판 빌드. 결과: release/anis-trans-<버전>-macos-<arm64|x86_64>.zip
#   packaging/build_macos.sh
# - Apple Silicon(M1 이상)에서 빌드하면 arm64판, Intel Mac에서 빌드하면 x86_64판이 나온다.
# - CTranslate2는 macOS에서 CPU만 쓴다(Apple Accelerate). Apple GPU(MPS)는 지원하지 않는다.
# - 서명하지 않은 실행 파일은 Gatekeeper가 막는다. 배포 전에 서명·공증하거나, 받는 사람이
#   xattr -dr com.apple.quarantine anis-trans-<버전>-macos-*  를 실행해야 한다.
#   서명: CODESIGN_IDENTITY="Developer ID Application: ..." 를 지정하면 빌드 뒤 codesign 을 실행한다.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"
"$PY" -m venv .build-venv
.build-venv/bin/python -m pip install --upgrade pip >/dev/null
.build-venv/bin/python -m pip install -e ".[build]"
.build-venv/bin/python packaging/build.py --no-archive "$@"
VER=$(.build-venv/bin/python -c "import anis_trans; print(anis_trans.__version__)")
ARCH=$(uname -m); [ "$ARCH" = "aarch64" ] && ARCH=arm64
NAME="anis-trans-$VER-macos-$ARCH"
if [ -n "${CODESIGN_IDENTITY:-}" ]; then
  find "release/$NAME" -type f \( -name "*.so" -o -name "*.dylib" -o -name "anis-trans" -o -perm -u+x \) -print0 |
    xargs -0 codesign --force --timestamp --options runtime --sign "$CODESIGN_IDENTITY"
  echo "서명 완료. 공증: xcrun notarytool submit release/$NAME.zip --keychain-profile <프로필> --wait"
fi
(cd release && ditto -c -k --keepParent "$NAME" "$NAME.zip")
echo "archive: release/$NAME.zip"
