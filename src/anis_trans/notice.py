"""라이선스 요약을 처음 실행할 때 한 번만 보여 준다 (동의 절차 없음)."""
import os
import platform
import sys
from pathlib import Path

from . import __version__

SUMMARY = ("ANIS Trans 라이선스 요약(초안): 개인·비영리 이용은 무료입니다. 후원·광고·판매·기업 이용 등 "
           "모든 영리 이용에는 별도 상업 라이선스가 필요합니다. 파인튜닝·역변환·재배포는 금지됩니다. "
           "전문은 LICENSE-ko.md(정본) / LICENSE-en.md 를 보세요.")


def _marker():
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "anis-trans" / f"license-notice-{__version__}"


def show_once(stream=None):
    """처음이면 요약을 출력하고 True. 표시 기록은 사용자 설정 폴더에 남긴다."""
    stream = stream or sys.stderr
    marker = _marker()
    try:
        if marker.exists():
            return False
    except OSError:
        pass
    if stream is not None:
        try:
            stream.write(SUMMARY + "\n\n")
            stream.flush()
        except Exception:
            pass
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("shown\n", encoding="utf-8")
    except OSError:
        pass
    return True
