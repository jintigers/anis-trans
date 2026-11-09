"""ANIS Trans 웹 GUI — 표준 라이브러리 HTTP 서버 + 브라우저 화면.

  anis-trans-gui [--port 7870] [--device auto|cpu|cuda] [--no-browser] [--host 127.0.0.1]

기본으로 이 컴퓨터(127.0.0.1)에서만 접속된다. 번역은 모두 로컬에서 이루어지며
입력 문장은 외부로 나가지 않는다.
"""
import argparse
import json
import os
import socket
import sys
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .. import __version__

HERE = Path(__file__).resolve().parent
MAX_BODY = 64 * 1024 * 1024


class State:
    def __init__(self, args):
        self.args = args
        self.engine = None
        self.error = ""
        self.loading = False
        self.lock = threading.Lock()       # 번역·장치 전환 직렬화
        self.jobs = {}
        self.devices = ["auto", "cpu"]
        self.requested = dict(device=args.device, compute_type=args.compute_type)

    def load(self, device, compute_type):
        from ..engine import Engine, available_devices
        self.loading, self.error = True, ""
        self.requested = dict(device=device, compute_type=compute_type)
        try:
            with self.lock:
                self.engine = None
                self.engine = Engine(self.args.model, device=device,
                                     compute_type=compute_type, threads=self.args.threads)
                self.devices = available_devices(self.engine.model_dir)
        except Exception as e:
            self.error = str(e)
        finally:
            self.loading = False

    def info(self):
        from ..notice import SUMMARY
        return dict(version=__version__, loading=self.loading, error=self.error, license=SUMMARY,
                    engine=self.engine.info if self.engine else None, devices=self.devices,
                    requested=self.requested)


def _items(payload):
    from ..engine import Item
    lines = payload.get("lines")
    if lines is None:
        return [Item(payload.get("text", ""), _list(payload.get("prev")), _list(payload.get("next")))]
    from ..cli import _context_items
    return _context_items([str(x) for x in lines], f"{int(payload.get('ctx_prev', 0))},{int(payload.get('ctx_next', 0))}")


def _list(v):
    if not v:
        return []
    if isinstance(v, str):
        return [x for x in v.replace("\r\n", "\n").split("\n") if x.strip()]
    return [str(x) for x in v if str(x).strip()]


def run_translation(state, payload, progress=None):
    from ..cli import detect_direction
    items = _items(payload)
    direction = payload.get("direction", "auto")
    line_type = payload.get("line_type", "대사")
    if direction not in ("auto", "ja-ko", "ko-ja"):
        raise ValueError("direction 값 오류")
    groups = {}
    for i, it in enumerate(items):
        d = detect_direction(it.text) if direction == "auto" else direction
        groups.setdefault(d, []).append(i)
    out = [None] * len(items)
    done = 0
    t = time.perf_counter()
    with state.lock:
        if state.engine is None:
            raise RuntimeError(state.error or "모델을 아직 불러오는 중입니다.")
        for d, idx in groups.items():
            cb = (lambda k, n, base=done: progress(base + k, len(items))) if progress else None
            res = state.engine.translate([items[i] for i in idx], d, line_type, 16, cb)
            for i, r in zip(idx, res):
                out[i] = dict(text=r.text, error=r.error, direction=d, dropped_context=r.dropped_context)
            done += len(idx)
    return dict(results=out, seconds=round(time.perf_counter() - t, 3))


class Handler(BaseHTTPRequestHandler):
    server_version = f"ANIS-Trans/{__version__}"
    state = None

    def log_message(self, fmt, *a):
        if self.state.args.verbose:
            super().log_message(fmt, *a)

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            return self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/api/info":
            return self._send(200, self.state.info())
        if path.startswith("/api/job/"):
            job = self.state.jobs.get(path.rsplit("/", 1)[1])
            if not job:
                return self._send(404, {"error": "작업 없음"})
            return self._send(200, job)
        self._send(404, {"error": "not found"})

    def do_POST(self):
        # 다른 웹사이트가 이 로컬 서버로 요청을 보내지 못하게 사용자 정의 헤더를 요구한다
        # (브라우저는 교차 출처 요청에 이 헤더를 붙이려면 사전 확인을 거치고, 이 서버는 허용하지 않는다).
        if self.headers.get("X-Anis-Trans") != "1":
            return self._send(403, {"error": "forbidden"})
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            return self._send(413, {"error": "입력이 너무 큽니다"})
        try:
            payload = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, {"error": "JSON 오류"})
        path = self.path.split("?", 1)[0]
        st = self.state
        try:
            if path == "/api/translate":
                return self._send(200, run_translation(st, payload))
            if path == "/api/batch":
                jid = uuid.uuid4().hex[:12]
                job = st.jobs[jid] = dict(id=jid, done=0, total=len(payload.get("lines", [])), status="running")
                st.jobs = {k: v for k, v in list(st.jobs.items())[-20:]}  # 오래된 작업 정리

                def work():
                    def prog(k, total):
                        job["done"] = k
                    try:
                        job.update(run_translation(st, payload, prog), status="done", done=job["total"])
                    except Exception as e:
                        job.update(status="error", error=str(e))
                threading.Thread(target=work, daemon=True).start()
                return self._send(200, {"id": jid})
            if path == "/api/device":
                if st.loading:
                    return self._send(409, {"error": "모델을 불러오는 중입니다"})
                st.loading = True
                threading.Thread(target=st.load, args=(payload.get("device", "auto"),
                                                       payload.get("compute_type", "auto")), daemon=True).start()
                return self._send(200, {"ok": True})
        except Exception as e:
            return self._send(400, {"error": str(e)})
        self._send(404, {"error": "not found"})


def _free_port(host, start):
    for port in range(start, start + 50):
        with socket.socket() as s:
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    raise SystemExit("빈 포트를 찾지 못했습니다. --port 로 지정하세요.")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="anis-trans-gui", description=f"ANIS Trans {__version__} 웹 GUI")
    ap.add_argument("--host", default="127.0.0.1", help="기본 127.0.0.1 (이 컴퓨터에서만 접속)")
    ap.add_argument("--port", type=int, default=7870, help="기본 7870 (사용 중이면 다음 빈 포트)")
    ap.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    ap.add_argument("--compute-type", default="auto")
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--model", help="모델 폴더 (기본: 번들의 model/)")
    ap.add_argument("--no-browser", action="store_true", help="브라우저를 자동으로 열지 않음")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure") and stream is not None:
            try:
                stream.reconfigure(errors="replace")
            except Exception:
                pass

    state = State(args)
    Handler.state = state
    state.loading = True
    threading.Thread(target=state.load, args=(args.device, args.compute_type), daemon=True).start()
    port = _free_port(args.host, args.port)
    httpd = ThreadingHTTPServer((args.host, port), Handler)
    url = f"http://{'127.0.0.1' if args.host in ('0.0.0.0', '::') else args.host}:{port}/"
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(f"주의: {args.host} 에 열었습니다. 같은 네트워크의 다른 컴퓨터도 접속할 수 있습니다.")
    from ..notice import show_once
    show_once(sys.stdout)
    print(f"ANIS Trans {__version__} GUI: {url}  (끝내려면 Ctrl+C)", flush=True)
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n종료합니다.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
