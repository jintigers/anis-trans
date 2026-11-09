"""ANIS Trans 로컬 API 서버 — Ollama·OpenAI 호환 엔드포인트를 흉내 낸다.

ANIS Trans는 대화형 언어 모델이 아니라 번역 모델이다. 그래서 "대화"의 마지막 user 메시지를
번역해서 assistant 답으로 돌려준다. 지시문(system 프롬프트)은 번역 방향을 고르는 데만 쓴다.

  anis-trans-server [--port 11435] [--device auto|cpu|cuda] [--host 127.0.0.1] [--api-key 키]

엔드포인트
  Ollama : GET /api/tags, POST /api/generate, POST /api/chat, POST /api/show, GET /api/ps, GET /api/version
  OpenAI : GET /v1/models, GET /v1/models/{id}, POST /v1/chat/completions, POST /v1/completions

모델 이름
  anis-trans (= anis-trans:latest, anis-trans:auto)  방향 자동 판별
  anis-trans:ja-ko                                  일본어 → 한국어
  anis-trans:ko-ja                                  한국어 → 일본어

방향 결정 순서: 요청의 anis.direction > 모델 이름 > system 프롬프트의 방향 표현 > 문장마다 자동 판별

문맥 전달 (자세한 내용은 README의 "API 서버" 절)
  1) 요청 본문의 "anis" 객체 (Ollama는 "options" 안에 넣어도 됨):
       {"prev": [...], "next": [...], "line_type": "대사", "split_lines": true,
        "context_lines": "0,0", "history": 3, "direction": "ja-ko"}
  2) 채팅 기록: 마지막 user 메시지 앞의 user 메시지들이 앞 문맥(<prev>)이 된다 (기본 최근 3개)
  3) 문장에 <tgt> 가 있으면 모델 입력 형식으로 보고 그대로 넣는다
"""
import argparse
import json
import re
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__

BASE = "anis-trans"
MODELS = {"anis-trans": "auto", "anis-trans:latest": "auto", "anis-trans:auto": "auto",
          "anis-trans:ja-ko": "ja-ko", "anis-trans:ko-ja": "ko-ja"}
PUBLIC_MODELS = ["anis-trans:latest", "anis-trans:ja-ko", "anis-trans:ko-ja"]
CREATED = int(time.time())
MAX_BODY = 16 * 1024 * 1024
ANIS_KEYS = ("prev", "next", "line_type", "split_lines", "context_lines", "history", "direction")

KO_JA = re.compile(r"ko-ja|<2ja>|ko\s*(?:→|->)\s*ja|korean\s*(?:→|->|to|into)\s*japanese|(?:in)?to\s+japanese|"
                   r"한국어\s*(?:→|->|에서|를|을)\s*일본어|일본어로|日本語に|日本語へ", re.I)
JA_KO = re.compile(r"ja-ko|<2ko>|ja\s*(?:→|->)\s*ko|japanese\s*(?:→|->|to|into)\s*korean|(?:in)?to\s+korean|"
                   r"일본어\s*(?:→|->|에서|를|을)\s*한국어|한국어로|韓国語に|韓国語へ", re.I)


class ApiError(Exception):
    def __init__(self, status, message, code="invalid_request_error", param=None):
        super().__init__(message)
        self.status, self.message, self.code, self.param = status, message, code, param


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _as_list(v):
    if v is None or v == "":
        return []
    if isinstance(v, str):
        return [x for x in v.replace("\r\n", "\n").split("\n") if x.strip()]
    return [str(x) for x in v if str(x).strip()]


def _text(content):
    """OpenAI 메시지 content는 문자열 또는 [{type: text, text: ...}] 목록."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type", "text") == "text")
    return str(content)


def direction_from_system(system):
    if not system:
        return None
    ko, ja = bool(KO_JA.search(system)), bool(JA_KO.search(system))
    if ko and not ja:
        return "ko-ja"
    if ja and not ko:
        return "ja-ko"
    return None


class Translator:
    """요청 → 엔진 호출. 엔진 하나를 잠금으로 공유한다."""

    def __init__(self, engine, accept_any_model=False):
        self.engine, self.accept_any_model = engine, accept_any_model
        self.lock = threading.Lock()

    def resolve_model(self, name):
        name = (name or BASE).strip()
        key = name.lower()
        if key in MODELS:
            return name, MODELS[key]
        if self.accept_any_model:
            return name, "auto"
        raise ApiError(404, f"model '{name}' not found (사용 가능: {', '.join(PUBLIC_MODELS)})", "model_not_found", "model")

    def run(self, model, target, history=(), system=None, body=None):
        """target 문자열을 번역. 반환: (번역문, 입력 토큰 수, 출력 토큰 수, 걸린 시간 ns)."""
        from .cli import _context_items, detect_direction
        from .engine import Item
        body = body or {}
        cfg = {}
        opts = body.get("options") if isinstance(body.get("options"), dict) else {}
        for src in (opts, body, body.get("anis") if isinstance(body.get("anis"), dict) else {}):
            cfg.update({k: src[k] for k in ANIS_KEYS if k in src})
        name, model_dir = self.resolve_model(model)
        direction = cfg.get("direction") or (model_dir if model_dir != "auto" else None) \
            or direction_from_system(system) or "auto"
        if direction not in ("auto", "ja-ko", "ko-ja"):
            raise ApiError(400, "direction은 auto, ja-ko, ko-ja 중 하나입니다.", param="direction")
        line_type = cfg.get("line_type", "대사")
        try:
            n_hist = max(0, int(cfg.get("history", 3)))
        except (TypeError, ValueError):
            raise ApiError(400, "history는 0 이상의 정수입니다.", param="history")
        prev = (list(history)[-n_hist:] if n_hist else []) + _as_list(cfg.get("prev"))
        nxt = _as_list(cfg.get("next"))
        target = target.replace("\r\n", "\n")
        lines = target.split("\n")
        if cfg.get("split_lines", True) and len([x for x in lines if x.strip()]) > 1 and "<tgt>" not in target:
            items = _context_items(lines, str(cfg.get("context_lines", "0,0")))
            nonempty = [i for i, x in enumerate(lines) if x.strip()]
            items[nonempty[0]].prev = prev + items[nonempty[0]].prev
            items[nonempty[-1]].next = items[nonempty[-1]].next + nxt
        else:
            items, lines = [Item(target, prev, nxt)], [target]
        t = time.perf_counter_ns()
        groups = {}
        for i, it in enumerate(items):
            d = detect_direction(it.text) if direction == "auto" else direction
            groups.setdefault(d, []).append(i)
        results = [None] * len(items)
        with self.lock:
            for d, idx in groups.items():
                for i, r in zip(idx, self.engine.translate([items[i] for i in idx], d, line_type)):
                    results[i] = r
        errors = [r.error for r in results if r.error]
        if errors and len(results) == 1:
            raise ApiError(400, errors[0], "input_too_long")
        text = "\n".join(r.text if not r.error else "" for r in results)
        return (name, text, sum(r.input_tokens for r in results), sum(r.output_tokens for r in results),
                time.perf_counter_ns() - t)


class Handler(BaseHTTPRequestHandler):
    server_version = f"ANIS-Trans-API/{__version__}"
    protocol_version = "HTTP/1.1"
    tr = None
    args = None

    # ---------- 공통 ----------
    def log_message(self, fmt, *a):
        if self.args.verbose:
            super().log_message(fmt, *a)

    def _is_openai(self):
        return self.path.startswith("/v1")

    def _headers(self, code, ctype, length=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        if length is not None:
            self.send_header("Content-Length", str(length))
        origin = self.headers.get("Origin")
        if origin and self._origin_ok(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Cache-Control", "no-store")

    def _json(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self._headers(code, "application/json; charset=utf-8", len(data))
        self.end_headers()
        self.wfile.write(data)

    def _error(self, e):
        if self._is_openai():
            self._json(e.status, {"error": {"message": e.message, "type": "invalid_request_error"
                                            if e.status < 500 else "server_error", "param": e.param, "code": e.code}})
        else:
            self._json(e.status, {"error": e.message})

    def _origin_ok(self, origin):
        allowed = self.args.allow_origin or []
        if "*" in allowed or origin in allowed:
            return True
        return bool(re.match(r"^https?://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$", origin))

    def _guard(self):
        origin = self.headers.get("Origin")
        if origin and not self._origin_ok(origin):  # 다른 웹사이트의 브라우저 요청 차단
            raise ApiError(403, "origin not allowed (--allow-origin 으로 허용)", "forbidden")
        if self.args.api_key:
            auth = self.headers.get("Authorization", "")
            if auth != f"Bearer {self.args.api_key}":
                raise ApiError(401, "invalid api key (Authorization: Bearer <키>)", "invalid_api_key")

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ApiError(413, "request too large")
        raw = self.rfile.read(n) if n else b""
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError as e:
            raise ApiError(400, f"invalid JSON: {e}")
        if not isinstance(body, dict):
            raise ApiError(400, "JSON object expected")
        return body

    def do_OPTIONS(self):
        origin = self.headers.get("Origin")
        if origin and self._origin_ok(origin):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self.send_response(403)
            self.send_header("Content-Length", "0")
            self.end_headers()

    def do_HEAD(self):
        self._headers(200, "text/plain; charset=utf-8", 0)
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        try:
            self._guard()
            if path == "/":
                data = f"ANIS Trans {__version__} API server is running (Ollama/OpenAI compatible)".encode()
                self._headers(200, "text/plain; charset=utf-8", len(data))
                self.end_headers()
                return self.wfile.write(data)
            if path == "/api/version":
                return self._json(200, {"version": __version__})
            if path == "/api/tags":
                return self._json(200, {"models": [self._ollama_model(m) for m in PUBLIC_MODELS]})
            if path == "/api/ps":
                return self._json(200, {"models": [dict(self._ollama_model(m), expires_at="0001-01-01T00:00:00Z",
                                                        size_vram=0) for m in PUBLIC_MODELS]})
            if path == "/v1/models":
                return self._json(200, {"object": "list", "data": [self._openai_model(m) for m in PUBLIC_MODELS]})
            if path.startswith("/v1/models/"):
                name, _ = self.tr.resolve_model(path[len("/v1/models/"):])
                return self._json(200, self._openai_model(name))
            raise ApiError(404, f"not found: {path}", "not_found")
        except ApiError as e:
            self._error(e)

    def do_POST(self):
        path = self.path.split("?", 1)[0].rstrip("/")
        try:
            body = self._body()  # 연결 재사용을 위해 거절할 때도 본문은 먼저 읽는다
            self._guard()
            if path == "/api/generate":
                return self._ollama_generate(body)
            if path == "/api/chat":
                return self._ollama_chat(body)
            if path == "/api/show":
                name, d = self.tr.resolve_model(body.get("model") or body.get("name"))
                return self._json(200, {"modelfile": "", "parameters": "num_beam 4", "template": "{{ .Prompt }}",
                                        "details": self._ollama_details(), "model_info": {
                                            "general.architecture": "anis-trans", "anis.direction": d,
                                            "general.parameter_count": self._params()},
                                        "capabilities": ["completion"]})
            if path == "/v1/chat/completions":
                return self._openai_chat(body)
            if path == "/v1/completions":
                return self._openai_completion(body)
            raise ApiError(404, f"not found: {path}", "not_found")
        except ApiError as e:
            self._error(e)
        except Exception as e:  # 엔진 오류
            self._error(ApiError(500, f"{type(e).__name__}: {e}", "server_error"))

    # ---------- 모델 정보 ----------
    def _params(self):
        return int(self.tr.engine.release.get("parameters", 0)) or None

    def _ollama_details(self):
        return {"parent_model": "", "format": "ctranslate2", "family": "anis-trans", "families": ["anis-trans"],
                "parameter_size": "300M", "quantization_level": "int8"}

    def _ollama_model(self, name):
        return {"name": name, "model": name, "modified_at": datetime.fromtimestamp(CREATED, timezone.utc)
                .isoformat().replace("+00:00", "Z"), "size": 0, "digest": "", "details": self._ollama_details()}

    def _openai_model(self, name):
        return {"id": name, "object": "model", "created": CREATED, "owned_by": "anis-trans"}

    # ---------- Ollama ----------
    def _ollama_stats(self, n_in, n_out, ns):
        return {"total_duration": ns, "load_duration": 0, "prompt_eval_count": n_in,
                "prompt_eval_duration": ns // 4, "eval_count": n_out, "eval_duration": ns - ns // 4}

    def _ndjson(self, objs):
        self._headers(200, "application/x-ndjson")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        for o in objs:
            line = (json.dumps(o, ensure_ascii=False) + "\n").encode()
            self.wfile.write(f"{len(line):x}\r\n".encode() + line + b"\r\n")
            self.wfile.flush()
        self.wfile.write(b"0\r\n\r\n")

    def _pieces(self, text):
        """스트리밍 조각: 줄 단위 (끝 줄바꿈 포함)."""
        parts = text.split("\n")
        return [p + ("\n" if i < len(parts) - 1 else "") for i, p in enumerate(parts)] or [""]

    def _ollama_generate(self, body):
        prompt = body.get("prompt", "")
        if not str(prompt).strip():  # Ollama는 빈 prompt를 "모델 불러오기"로 쓴다
            name, _ = self.tr.resolve_model(body.get("model"))
            return self._json(200, {"model": name, "created_at": _now_iso(), "response": "", "done": True,
                                    "done_reason": "load"})
        name, text, n_in, n_out, ns = self.tr.run(body.get("model"), str(prompt), (), body.get("system"), body)
        final = {"model": name, "created_at": _now_iso(), "response": "", "done": True, "done_reason": "stop",
                 "context": [], **self._ollama_stats(n_in, n_out, ns)}
        if body.get("stream", True):
            chunks = [{"model": name, "created_at": _now_iso(), "response": p, "done": False} for p in self._pieces(text)]
            return self._ndjson(chunks + [final])
        final["response"] = text
        self._json(200, final)

    def _split_messages(self, messages):
        if not isinstance(messages, list) or not messages:
            raise ApiError(400, "messages가 비어 있습니다.", param="messages")
        system = "\n".join(_text(m.get("content")) for m in messages if m.get("role") in ("system", "developer"))
        users = [i for i, m in enumerate(messages) if m.get("role") == "user"]
        if not users:
            raise ApiError(400, "user 메시지가 없습니다.", param="messages")
        target = _text(messages[users[-1]].get("content"))
        history = [_text(messages[i].get("content")) for i in users[:-1]]
        history = [h for h in history if h.strip() and "\n" not in h.strip()]  # 한 줄짜리만 문맥으로
        return target, history, system

    def _ollama_chat(self, body):
        target, history, system = self._split_messages(body.get("messages"))
        name, text, n_in, n_out, ns = self.tr.run(body.get("model"), target, history, system, body)
        final = {"model": name, "created_at": _now_iso(), "message": {"role": "assistant", "content": ""},
                 "done": True, "done_reason": "stop", **self._ollama_stats(n_in, n_out, ns)}
        if body.get("stream", True):
            chunks = [{"model": name, "created_at": _now_iso(), "message": {"role": "assistant", "content": p},
                       "done": False} for p in self._pieces(text)]
            return self._ndjson(chunks + [final])
        final["message"]["content"] = text
        self._json(200, final)

    # ---------- OpenAI ----------
    def _sse(self, objs):
        self._headers(200, "text/event-stream; charset=utf-8")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        for o in objs + ["[DONE]"]:
            data = o if isinstance(o, str) else json.dumps(o, ensure_ascii=False)
            line = f"data: {data}\n\n".encode()
            self.wfile.write(f"{len(line):x}\r\n".encode() + line + b"\r\n")
            self.wfile.flush()
        self.wfile.write(b"0\r\n\r\n")

    def _usage(self, n_in, n_out):
        return {"prompt_tokens": n_in, "completion_tokens": n_out, "total_tokens": n_in + n_out}

    def _openai_chat(self, body):
        target, history, system = self._split_messages(body.get("messages"))
        name, text, n_in, n_out, _ = self.tr.run(body.get("model"), target, history, system, body)
        cid, created = "chatcmpl-" + uuid.uuid4().hex[:24], int(time.time())
        base = {"id": cid, "created": created, "model": name, "system_fingerprint": f"anis-trans-{__version__}"}
        if body.get("stream", False):
            first = {**base, "object": "chat.completion.chunk",
                     "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "logprobs": None,
                                  "finish_reason": None}]}
            parts = [{**base, "object": "chat.completion.chunk",
                      "choices": [{"index": 0, "delta": {"content": p}, "logprobs": None, "finish_reason": None}]}
                     for p in self._pieces(text)]
            last = {**base, "object": "chat.completion.chunk",
                    "choices": [{"index": 0, "delta": {}, "logprobs": None, "finish_reason": "stop"}]}
            if (body.get("stream_options") or {}).get("include_usage"):
                tail = [last, {**base, "object": "chat.completion.chunk", "choices": [], "usage": self._usage(n_in, n_out)}]
            else:
                tail = [last]
            return self._sse([first] + parts + tail)
        self._json(200, {**base, "object": "chat.completion",
                         "choices": [{"index": 0, "message": {"role": "assistant", "content": text, "refusal": None},
                                      "logprobs": None, "finish_reason": "stop"}],
                         "usage": self._usage(n_in, n_out)})

    def _openai_completion(self, body):
        prompt = body.get("prompt", "")
        if isinstance(prompt, list):
            prompt = "\n".join(str(p) for p in prompt)
        name, text, n_in, n_out, _ = self.tr.run(body.get("model"), str(prompt), (), None, body)
        cid, created = "cmpl-" + uuid.uuid4().hex[:24], int(time.time())
        if body.get("stream", False):
            chunks = [{"id": cid, "object": "text_completion", "created": created, "model": name,
                       "choices": [{"index": 0, "text": p, "logprobs": None, "finish_reason": None}]}
                      for p in self._pieces(text)]
            chunks.append({"id": cid, "object": "text_completion", "created": created, "model": name,
                           "choices": [{"index": 0, "text": "", "logprobs": None, "finish_reason": "stop"}]})
            return self._sse(chunks)
        self._json(200, {"id": cid, "object": "text_completion", "created": created, "model": name,
                         "choices": [{"index": 0, "text": text, "logprobs": None, "finish_reason": "stop"}],
                         "usage": self._usage(n_in, n_out)})


def main(argv=None):
    ap = argparse.ArgumentParser(prog="anis-trans-server", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1",
                    help="기본 127.0.0.1 (이 컴퓨터에서만). 0.0.0.0 이면 다른 기기도 접속 가능 — --api-key 권장")
    ap.add_argument("--port", type=int, default=11435, help="기본 11435 (Ollama 대신 쓰려면 11434)")
    ap.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    ap.add_argument("--compute-type", default="auto")
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--model", help="모델 폴더 (기본: 번들의 model/)")
    ap.add_argument("--api-key", help="지정하면 Authorization: Bearer <키> 가 있어야 응답")
    ap.add_argument("--allow-origin", action="append", metavar="ORIGIN",
                    help="브라우저에서 호출을 허용할 출처 (예: http://example.com, 모두 허용은 *). 기본: localhost만")
    ap.add_argument("--accept-any-model", action="store_true",
                    help="모르는 모델 이름도 anis-trans(자동 방향)로 처리 (모델 이름을 바꿀 수 없는 클라이언트용)")
    ap.add_argument("-v", "--verbose", action="store_true", help="요청 기록 출력")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass

    from .engine import Engine
    from .notice import show_once
    show_once(sys.stdout)
    try:
        engine = Engine(args.model, device=args.device, compute_type=args.compute_type, threads=args.threads)
    except Exception as e:
        raise SystemExit(f"모델을 불러오지 못했습니다: {e}")
    if engine.info.get("warning"):
        print(f"[주의] {engine.info['warning']}")
    Handler.tr = Translator(engine, args.accept_any_model)
    Handler.args = args
    try:
        httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as e:
        raise SystemExit(f"{args.host}:{args.port} 에 열 수 없습니다 ({e}). --port 로 다른 포트를 고르세요.")
    httpd.daemon_threads = True
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(f"주의: {args.host} 에 열었습니다. 같은 네트워크의 다른 기기도 접속할 수 있습니다."
              + ("" if args.api_key else " --api-key 를 함께 쓰는 것을 권장합니다."))
    i = engine.info
    print(f"ANIS Trans {__version__} API 서버: http://{args.host}:{args.port}  "
          f"[{i['device']} · {i['compute_type']}]  모델: {', '.join(PUBLIC_MODELS)}  (끝내려면 Ctrl+C)", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n종료합니다.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
