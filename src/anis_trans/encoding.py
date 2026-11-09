"""ANIS Trans 입력 인코딩.

모델이 학습한 입력 형식과 같은 규칙으로 문장을 토큰 id로 바꾼다.

  방향 접두: ja-ko → "<2ko>", ko-ja → "<2ja>", legacy-ja-ko → 없음
  문맥 형식: <prev> <대사> 앞문장 <tgt> <대사> 대상 <next> <대사> 뒷문장
  길이 제한: 접두 + 본문 + EOS ≤ limit. 넘치면 가장 먼 앞 문맥부터, 그다음 가장 먼 뒷 문맥을
            통째로 버리고, 대상 문장은 절대 자르지 않는다.
"""
import re

DIRECTIONS = ("ja-ko", "ko-ja", "legacy-ja-ko")
PREFIX = {"ja-ko": "<2ko>", "ko-ja": "<2ja>", "legacy-ja-ko": ""}
LINE_TYPES = ("대사", "독백", "나레이션", "선택지", "시스템")
EOS_ID = 3
SEGMENT = re.compile(r"(?=<(?:prev|tgt|next)>)")
BR = re.compile(r"\s*<br>\s*")


class InputTooLong(ValueError):
    pass


def _segments(source):
    return [p.strip() for p in SEGMENT.split(source) if p.strip()]


def _clean(text):
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").strip().split("\n")
    return " <br> ".join(line.strip() for line in lines)


def build_source(text, prev=(), next=(), line_type="대사"):
    """대상 문장과 앞뒤 문맥(문자열 또는 문자열 목록)으로 모델 입력 문자열을 만든다.

    문맥이 없으면 학습 때와 같이 "<tgt> 문장" 형태가 된다.
    문장 안 줄바꿈은 " <br> " 로 바꾼다.
    """
    if isinstance(prev, str):
        prev = [prev] if prev.strip() else []
    if isinstance(next, str):
        next = [next] if next.strip() else []
    prev = [p for p in prev if p and str(p).strip()]
    next = [n for n in next if n and str(n).strip()]
    if "<tgt>" in text and not prev and not next:
        return text  # 이미 모델 입력 형식(<prev>/<tgt>/<next>)으로 쓴 문장은 그대로
    target = _clean(text)
    if not prev and not next:
        return "<tgt> " + target
    if line_type not in LINE_TYPES:
        raise ValueError(f"line_type must be one of {LINE_TYPES}")
    tag = f"<{line_type}>"
    parts = [f"<prev> {tag} {_clean(p)}" for p in prev]
    parts.append(f"<tgt> {tag} {target}")
    parts += [f"<next> {tag} {_clean(n)}" for n in next]
    return " ".join(parts)


def prefix_ids(sp, direction):
    if direction not in DIRECTIONS:
        raise ValueError(f"Unsupported translation direction: {direction}")
    ids = sp.encode(PREFIX[direction]) if PREFIX[direction] else []
    if sp.unk_id() in ids:
        raise ValueError("Direction prefix contains an unknown token")
    return ids


def encode_source(sp, source, limit):
    parts = _segments(source)
    if sum(p.startswith("<tgt>") for p in parts) != 1:
        raise ValueError("Expected exactly one <tgt> segment")
    dropped = 0
    while True:
        ids = sp.encode(" ".join(parts))
        if len(ids) + 1 <= limit:
            return ids + [EOS_ID], dropped
        previous = next((i for i, p in enumerate(parts) if p.startswith("<prev>")), None)
        following = next((i for i in reversed(range(len(parts))) if parts[i].startswith("<next>")), None)
        remove = previous if previous is not None else following
        if remove is None:
            raise InputTooLong(f"대상 문장만으로 {limit} 토큰을 넘습니다. 문장을 나눠 주세요.")
        del parts[remove]
        dropped += 1


def encode_input(sp, text, direction, limit=1024):
    """(token ids, 버린 문맥 수)를 돌려준다."""
    prefix = prefix_ids(sp, direction)
    source = text if "<tgt>" in text else "<tgt> " + text.replace("\n", " <br> ")
    tokens, dropped = encode_source(sp, source, limit - len(prefix))
    return prefix + tokens, dropped


def decode_output(sp, ids, restore_newlines=False):
    text = sp.decode([int(t) for t in ids if int(t) > EOS_ID])
    if restore_newlines:
        text = BR.sub("\n", text)
    return text
