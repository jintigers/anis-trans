"""설치 점검: 설치한 환경에서 CLI·GUI·API 서버가 실제로 번역하는지 확인한다.

  python tools/smoke_test.py                 CPU만
  python tools/smoke_test.py --gpu           CPU + CUDA GPU
  python tools/smoke_test.py --exe <실행 파일>  독립 실행판(anis-trans/anis-trans.exe) 점검

모든 항목이 통과하면 "ALL OK" 를 출력하고 0으로 끝난다.
"""
import argparse
import json
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HANGUL = lambda s: any("가" <= c <= "힣" for c in s)
KANA = lambda s: any("぀" <= c <= "ヿ" for c in s)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gpu", action="store_true")
    ap.add_argument("--exe", help="독립 실행판 경로 (기본: 현재 Python으로 python -m anis_trans)")
    args = ap.parse_args()
    base = [args.exe] if args.exe else [sys.executable, "-m", "anis_trans"]
    devices = ["cpu"] + (["cuda"] if args.gpu else [])
    fails = []

    def check(name, ok, detail=""):
        print(("PASS " if ok else "FAIL ") + name + (f"  → {detail}" if detail else ""), flush=True)
        if not ok:
            fails.append(name)

    def run(cmd, stdin=None):
        r = subprocess.run(base + cmd, input=stdin, capture_output=True, text=True, encoding="utf-8", timeout=600)
        return r.returncode, r.stdout.strip(), r.stderr.strip()

    with tempfile.TemporaryDirectory() as tmp:
        for dev in devices:
            code, out, err = run(["--device", dev, "--info"])
            check(f"[{dev}] 장치 선택", code == 0 and f"device: {dev}" in out, out.replace("\n", " ") or err)
            code, out, err = run(["--device", dev, "今日は雨が降ってるね。"])
            check(f"[{dev}] 단문 일→한", code == 0 and HANGUL(out), out or err)
            code, out, err = run(["--device", dev, "-d", "ko-ja", "오늘은 비가 오네."])
            check(f"[{dev}] 단문 한→일", code == 0 and KANA(out), out or err)
            code, out, err = run(["--device", dev, "--prev", "先輩、顔色悪いですよ。", "--next", "ああ、少し寝不足なだけだ。", "大丈夫？"])
            check(f"[{dev}] 앞뒤 문맥", code == 0 and HANGUL(out), out or err)
            code, out, err = run(["--device", dev, "--context-lines", "1,1"], stdin="準備はいい？\n\n行くぞ！\n")
            lines = out.split("\n")
            check(f"[{dev}] 표준입력 파이프", code == 0 and len(lines) == 3 and lines[1] == "" and HANGUL(lines[2]), out or err)
            src = Path(tmp) / "in.txt"
            src.write_text("おはようございます、先輩！\n선배, 같이 가요.\n", encoding="utf-8")
            dst = Path(tmp) / f"out-{dev}.txt"
            code, out, err = run(["--device", dev, "-f", str(src), "-o", str(dst)])
            got = dst.read_text(encoding="utf-8").splitlines() if dst.exists() else []
            check(f"[{dev}] 파일 일괄 (방향 자동)", code == 0 and len(got) == 2 and HANGUL(got[0]) and KANA(got[1]), " | ".join(got) or err)
            jl = Path(tmp) / "in.jsonl"
            jl.write_text(json.dumps({"text": "大丈夫？", "prev": "先輩、顔色悪いですよ。"}, ensure_ascii=False) + "\n", encoding="utf-8")
            code, out, err = run(["--device", dev, "-f", str(jl)])
            check(f"[{dev}] JSONL", code == 0 and HANGUL(json.loads(out)["translation"]), out or err)

        # GUI 서버
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        proc = subprocess.Popen(base + ["--gui", "--no-browser", "--port", str(port), "--device", "cpu"],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            url = f"http://127.0.0.1:{port}"

            def get(path):
                return json.load(urllib.request.urlopen(url + path, timeout=30))

            def post(path, body):
                req = urllib.request.Request(url + path, json.dumps(body).encode(),
                                             {"Content-Type": "application/json", "X-Anis-Trans": "1"})
                return json.load(urllib.request.urlopen(req, timeout=120))

            info = None
            for _ in range(120):
                try:
                    info = get("/api/info")
                    if not info["loading"]:
                        break
                except OSError:
                    pass
                time.sleep(0.5)
            check("[gui] 서버 시작", bool(info and info["engine"]), json.dumps(info, ensure_ascii=False)[:200] if info else "응답 없음")
            page = urllib.request.urlopen(url + "/", timeout=10).read().decode()
            check("[gui] 화면", "ANIS Trans" in page)
            for dev in devices:
                post("/api/device", {"device": dev})
                for _ in range(120):
                    time.sleep(0.5)
                    info = get("/api/info")
                    if not info["loading"]:
                        break
                check(f"[gui:{dev}] 장치 전환", (info.get("engine") or {}).get("device") == dev, json.dumps(info.get("engine"), ensure_ascii=False))
                r = post("/api/translate", {"text": "大丈夫？", "prev": "先輩、顔色悪いですよ。", "direction": "auto"})
                check(f"[gui:{dev}] 문장 번역", HANGUL(r["results"][0]["text"]), r["results"][0]["text"])
                job = post("/api/batch", {"lines": ["準備はいい？", "", "선배, 같이 가요."], "direction": "auto", "ctx_prev": 1})
                for _ in range(120):
                    j = get("/api/job/" + job["id"])
                    if j["status"] != "running":
                        break
                    time.sleep(0.3)
                texts = [x["text"] for x in j.get("results", [])]
                check(f"[gui:{dev}] 일괄 번역", j["status"] == "done" and HANGUL(texts[0]) and texts[1] == "" and KANA(texts[2]), " | ".join(texts))
        finally:
            proc.terminate()
            proc.wait(timeout=10)

        # API 서버 (Ollama·OpenAI 호환)
        for dev in devices:
            with socket.socket() as s:
                s.bind(("127.0.0.1", 0))
                port = s.getsockname()[1]
            proc = subprocess.Popen(base + ["--serve", "--port", str(port), "--device", dev],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            url = f"http://127.0.0.1:{port}"
            try:
                def req(path, body=None):
                    data = None if body is None else json.dumps(body).encode()
                    r = urllib.request.Request(url + path, data, {"Content-Type": "application/json"})
                    return urllib.request.urlopen(r, timeout=120).read().decode()

                up = False
                for _ in range(120):
                    try:
                        req("/")
                        up = True
                        break
                    except OSError:
                        time.sleep(0.5)
                check(f"[api:{dev}] 서버 시작", up)
                tags = json.loads(req("/api/tags"))
                check(f"[api:{dev}] Ollama /api/tags", "anis-trans:ja-ko" in [m["name"] for m in tags["models"]])
                models = json.loads(req("/v1/models"))
                check(f"[api:{dev}] OpenAI /v1/models", models["object"] == "list" and len(models["data"]) == 3)
                g = json.loads(req("/api/generate", {"model": "anis-trans:ja-ko", "prompt": "今日は雨が降ってるね。", "stream": False}))
                check(f"[api:{dev}] Ollama generate", g["done"] and HANGUL(g["response"]), g.get("response"))
                lines = [json.loads(x) for x in req("/api/chat", {"model": "anis-trans", "messages": [
                    {"role": "user", "content": "先輩、顔色悪いですよ。"}, {"role": "user", "content": "大丈夫？"}]}).splitlines()]
                text = "".join(x["message"]["content"] for x in lines)
                check(f"[api:{dev}] Ollama chat 스트리밍+기록 문맥", lines[-1]["done"] and HANGUL(text), text)
                c = json.loads(req("/v1/chat/completions", {"model": "anis-trans:ko-ja", "messages": [
                    {"role": "user", "content": "괜찮아?"}], "anis": {"prev": "선배, 안색이 안 좋아요."}}))
                msg = c["choices"][0]["message"]["content"]
                check(f"[api:{dev}] OpenAI chat (ko-ja, anis.prev)", c["object"] == "chat.completion"
                      and c["choices"][0]["finish_reason"] == "stop" and msg.strip() and not HANGUL(msg) and c["usage"]["total_tokens"] > 0, msg)
                sse = [x[6:] for x in req("/v1/chat/completions", {"model": "anis-trans", "stream": True, "messages": [
                    {"role": "user", "content": "준비됐어?\n가자!"}]}).splitlines() if x.startswith("data: ")]
                text = "".join((json.loads(x)["choices"][0]["delta"].get("content") or "") for x in sse[:-1]
                               if json.loads(x)["choices"])
                check(f"[api:{dev}] OpenAI 스트리밍 (줄마다)", sse[-1] == "[DONE]" and text.count("\n") == 1 and KANA(text), text)
            except Exception as e:
                check(f"[api:{dev}] 예외", False, repr(e))
            finally:
                proc.terminate()
                proc.wait(timeout=10)

    print("ALL OK" if not fails else f"{len(fails)} FAILED: {', '.join(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
