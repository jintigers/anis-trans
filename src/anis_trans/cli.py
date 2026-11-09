"""anis-trans 명령줄 도구.

  anis-trans "今日は雨が降ってるね。"                 단문 번역 (방향 자동 판별)
  anis-trans -d ko-ja "오늘은 비가 오네."             방향 지정
  anis-trans --prev "準備はいい？" --next "うん！" "行くぞ"   앞뒤 문맥
  anis-trans -f script.txt -o script.ko.txt            파일 일괄 번역 (한 줄 = 한 문장)
  anis-trans -f lines.jsonl -o out.jsonl               JSONL ({"text","prev","next","direction"})
  cat script.txt | anis-trans -d ja-ko > out.txt       표준입력 파이프
  anis-trans                                           (터미널에서 인자 없이) 대화형 모드
  anis-trans --gui                                     웹 GUI 실행 (anis-trans-gui)
  anis-trans --serve                                   Ollama/OpenAI 호환 API 서버 (anis-trans-server)
"""
import argparse
import json
import os
import re
import sys
import time

from . import __version__

KANA = re.compile(r"[぀-ヿㇰ-ㇿｦ-ﾟ]")
HANGUL = re.compile(r"[가-힣ᄀ-ᇿ㄰-㆏]")


def detect_direction(text):
    """가나가 있으면 일→한, 한글만 있으면 한→일, 둘 다 없으면(한자·영문만) 일→한."""
    if KANA.search(text):
        return "ja-ko"
    if HANGUL.search(text):
        return "ko-ja"
    return "ja-ko"


def _setup_stdio(encoding):
    # Windows에서 파이프/리디렉션일 때 기본 cp949 대신 UTF-8로 주고받는다.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure") and not stream.isatty():
            stream.reconfigure(encoding=encoding, errors="replace")
    if hasattr(sys.stdin, "reconfigure") and sys.stdin is not None and not sys.stdin.isatty():
        sys.stdin.reconfigure(encoding=encoding, errors="replace")


def _quiet():
    import warnings
    warnings.filterwarnings("ignore")


def build_parser():
    ap = argparse.ArgumentParser(
        prog="anis-trans", description=f"ANIS Trans {__version__} — 일본어↔한국어 번역기",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__.split("\n", 1)[1])
    ap.add_argument("text", nargs="*", help="번역할 문장 (여러 개면 각각 번역)")
    g = ap.add_argument_group("방향·문맥")
    g.add_argument("-d", "--direction", default="auto", choices=["auto", "ja-ko", "ko-ja"],
                   help="번역 방향 (기본 auto: 문장마다 문자 종류로 판별)")
    g.add_argument("--prev", action="append", default=[], metavar="문장", help="앞 문맥 (여러 번 지정 가능, 오래된 것부터)")
    g.add_argument("--next", action="append", default=[], metavar="문장", help="뒷 문맥 (여러 번 지정 가능, 가까운 것부터)")
    g.add_argument("--context-lines", default="0,0", metavar="앞,뒤",
                   help="파일/파이프 번역 때 앞뒤 몇 줄을 문맥으로 넣을지 (예: 2,1). 기본 0,0")
    g.add_argument("--line-type", default="대사", choices=["대사", "독백", "나레이션", "선택지", "시스템"],
                   help="문맥을 쓸 때 붙이는 줄 종류 태그 (기본 대사)")
    g = ap.add_argument_group("파일")
    g.add_argument("-f", "--file", metavar="경로", help="입력 파일 (.txt 한 줄 = 한 문장, .jsonl)")
    g.add_argument("-o", "--output", metavar="경로", help="출력 파일 (생략 시 표준출력)")
    g.add_argument("--format", choices=["auto", "txt", "jsonl"], default="auto", help="입력 형식 (기본: 확장자로 판별)")
    g.add_argument("--with-source", action="store_true", help="txt 출력에 원문<TAB>번역 형태로 쓰기")
    g.add_argument("--encoding", default="utf-8", help="파일·파이프 문자 인코딩 (기본 utf-8)")
    g = ap.add_argument_group("장치·실행기")
    g.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"],
                   help="auto: CUDA GPU가 있으면 GPU, 없으면 CPU")
    g.add_argument("--compute-type", default="auto",
                   help="정밀도 (auto, int8, int8_float16, float16, float32). auto = CPU int8 / GPU float16")
    g.add_argument("--threads", type=int, default=0, help="CPU 스레드 수 (0=자동)")
    g.add_argument("--batch-size", type=int, default=16)
    g.add_argument("--beam", type=int, default=4, help="빔 크기 (기본 4, 학습·평가와 같음)")
    g.add_argument("--max-length", type=int, default=512, help="출력 최대 토큰 수")
    g.add_argument("--model", metavar="폴더", help="모델 폴더 (기본: 번들의 model/)")
    ap.add_argument("--gui", action="store_true", help="웹 GUI 실행 (anis-trans-gui 와 같음)")
    ap.add_argument("--serve", action="store_true", help="API 서버 실행 (anis-trans-server 와 같음)")
    ap.add_argument("--info", action="store_true", help="선택된 장치·실행기를 보여 주고 끝냄")
    ap.add_argument("-v", "--verbose", action="store_true", help="장치·속도 정보를 표준오류로 출력")
    ap.add_argument("-V", "--version", action="version", version=f"ANIS Trans {__version__}")
    return ap


def _load_engine(args):
    from .engine import Engine
    return Engine(args.model, device=args.device, compute_type=args.compute_type,
                  threads=args.threads, beam_size=args.beam, max_length=args.max_length)


def _as_list(v):
    if v is None:
        return []
    return [v] if isinstance(v, str) else list(v)


class Progress:
    """표준오류에 진행률 표시. 전체 시간 기준 속도를 보여 준다."""

    def __init__(self):
        self.start = time.time()

    def __call__(self, done, total):
        rate = done / max(time.time() - self.start, 1e-6)
        sys.stderr.write(f"\r번역 중 {done}/{total} ({rate:.1f} 문장/초)")
        if done >= total:
            sys.stderr.write("\n")
        sys.stderr.flush()


def translate_items(engine, items, direction, args, progress=None):
    """items: [(Item, 방향 또는 None)] → 결과 목록. 방향이 섞여 있으면 방향별로 묶어 번역한다."""
    from .engine import Result
    groups = {}
    for i, (item, d) in enumerate(items):
        d = d or (detect_direction(item.text) if direction == "auto" else direction)
        groups.setdefault(d, []).append(i)
    results = [None] * len(items)
    done_before, total = 0, len(items)
    for d, idx in groups.items():
        cb = (lambda k, n, base=done_before: progress(base + k, total)) if progress else None
        outs = engine.translate([items[i][0] for i in idx], d, args.line_type, args.batch_size, cb)
        for i, r in zip(idx, outs):
            results[i] = r
        done_before += len(idx)
    return [r or Result("") for r in results]


def _context_items(lines, spec):
    from .engine import Item
    try:
        p, n = (int(x) for x in spec.split(","))
    except ValueError:
        raise SystemExit("--context-lines 는 '앞,뒤' 숫자 형식입니다 (예: 2,1)")
    nonempty = [i for i, line in enumerate(lines) if line.strip()]
    pos = {i: k for k, i in enumerate(nonempty)}
    items = []
    for i, line in enumerate(lines):
        if not line.strip() or (p == 0 and n == 0):
            items.append(Item(line))
            continue
        k = pos[i]
        prev = [lines[j] for j in nonempty[max(0, k - p):k]] if p else []
        nxt = [lines[j] for j in nonempty[k + 1:k + 1 + n]] if n else []
        items.append(Item(line, prev, nxt))
    return items


def run_lines(engine, lines, args, out, show_progress):
    items = _context_items(lines, args.context_lines)
    results = translate_items(engine, [(it, None) for it in items], args.direction, args,
                              Progress() if show_progress else None)
    errors = 0
    for line, r in zip(lines, results):
        text = r.text.replace("\n", " <br> ")  # 한 줄 = 한 문장 유지
        if r.error:
            errors += 1
            sys.stderr.write(f"[건너뜀] {r.error}: {line[:40]}\n")
        out.write(f"{line}\t{text}\n" if args.with_source else text + "\n")
    return errors


def run_jsonl(engine, lines, args, out, show_progress):
    from .engine import Item
    rows, items = [], []
    for n, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            raise SystemExit(f"{n}번째 줄 JSON 오류: {e}")
        if isinstance(row, str):
            row = {"text": row}
        if "text" not in row:
            raise SystemExit(f"{n}번째 줄에 \"text\" 가 없습니다")
        rows.append(row)
        d = row.get("direction")
        if d not in (None, "auto", "ja-ko", "ko-ja"):
            raise SystemExit(f"{n}번째 줄 direction 값 오류: {d}")
        items.append((Item(row["text"], _as_list(row.get("prev")), _as_list(row.get("next"))),
                      None if d in (None, "auto") else d))
    results = translate_items(engine, items, args.direction, args, Progress() if show_progress else None)
    errors = 0
    for row, r in zip(rows, results):
        row["translation"] = r.text
        if r.error:
            row["error"] = r.error
            errors += 1
        out.write(json.dumps(row, ensure_ascii=False) + "\n")
    return errors


def interactive(engine, args):
    print(f"ANIS Trans {__version__} 대화형 모드 [{engine.info['device']}/{engine.info['compute_type']}] "
          "— 빈 줄 또는 Ctrl+D(Windows: Ctrl+Z 후 Enter)로 끝냄", file=sys.stderr)
    while True:
        try:
            line = input("> ")
        except (EOFError, KeyboardInterrupt):
            print(file=sys.stderr)
            return
        if not line.strip():
            return
        d = detect_direction(line) if args.direction == "auto" else args.direction
        print(engine.translate_text(line, d, args.prev, args.next, args.line_type))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if "--gui" in argv:  # anis-trans --gui [GUI 옵션] == anis-trans-gui [GUI 옵션]
        from .web import main as gui_main
        return gui_main([a for a in argv if a != "--gui"])
    if "--serve" in argv:  # anis-trans --serve [서버 옵션] == anis-trans-server [서버 옵션]
        from .server import main as server_main
        return server_main([a for a in argv if a != "--serve"])
    args = build_parser().parse_args(argv)
    _quiet()
    _setup_stdio(args.encoding)
    from .notice import show_once
    show_once()
    try:
        t0 = time.time()
        engine = _load_engine(args)
    except Exception as e:  # 장치·모델 오류는 짧게 안내
        raise SystemExit(f"모델을 불러오지 못했습니다: {e}")
    info = engine.info
    if info.get("warning"):
        sys.stderr.write(f"[주의] {info['warning']}\n")
    if args.info:
        for k, v in info.items():
            print(f"{k}: {v}")
        return 0
    if args.verbose:
        sys.stderr.write(f"[ANIS Trans {info['version']}] {info['backend']} {info['device']} "
                         f"{info['compute_type']} (로딩 {time.time() - t0:.1f}초)\n")

    out = open(args.output, "w", encoding=args.encoding, newline="\n") if args.output else sys.stdout
    errors = 0
    try:
        if args.file:
            with open(args.file, encoding="utf-8-sig" if args.encoding.lower() in ("utf-8", "utf8") else args.encoding) as f:
                lines = f.read().splitlines()
            fmt = args.format if args.format != "auto" else ("jsonl" if args.file.lower().endswith(".jsonl") else "txt")
            run = run_jsonl if fmt == "jsonl" else run_lines
            errors = run(engine, lines, args, out, show_progress=True)
        elif args.text:
            from .engine import Item
            items = [(Item(t, args.prev, args.next), None) for t in args.text]
            for r in translate_items(engine, items, args.direction, args):
                if r.error:
                    errors += 1
                    sys.stderr.write(f"오류: {r.error}\n")
                print(r.text, file=out)
        elif not sys.stdin.isatty():
            lines = sys.stdin.read().splitlines()
            if args.format == "jsonl":
                errors = run_jsonl(engine, lines, args, out, show_progress=bool(args.output))
            else:
                errors = run_lines(engine, lines, args, out, show_progress=bool(args.output))
        else:
            interactive(engine, args)
    finally:
        if args.output:
            out.close()
    sys.stdout.flush()
    if args.verbose:
        sys.stderr.write(f"완료 ({time.time() - t0:.1f}초)\n")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
