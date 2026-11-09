"""번역 엔진: CTranslate2 위에서 ANIS Trans int8 모델을 돌린다.

장치 선택 규칙
  device="auto"  CUDA GPU가 있으면 cuda(float16), 없으면 cpu(int8).
                 GPU 초기화가 실패하면(cuBLAS 없음 등) CPU로 자동 전환
  device="cuda"  NVIDIA GPU. 실패하면 이유를 알려 주고 멈춘다
  device="cpu"   CPU int8
"""
import json
import os
import platform
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from .encoding import DIRECTIONS, InputTooLong, build_source, decode_output, encode_input

DEVICES = ("auto", "cpu", "cuda")


@dataclass
class Item:
    text: str
    prev: list = field(default_factory=list)
    next: list = field(default_factory=list)


@dataclass
class Result:
    text: str
    error: str = ""
    dropped_context: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


def default_model_dir():
    """모델 폴더 찾기: $ANIS_TRANS_MODEL → 실행 파일 옆 model/ → 번들 루트 model/ → ./model"""
    env = os.environ.get("ANIS_TRANS_MODEL")
    candidates = [Path(env)] if env else []
    if getattr(sys, "frozen", False):  # PyInstaller 실행 파일
        candidates += [Path(sys.executable).resolve().parent / "model",
                       Path(getattr(sys, "_MEIPASS", "")) / "model"]
    here = Path(__file__).resolve()
    candidates += [here.parent / "model", here.parents[2] / "model", Path.cwd() / "model"]
    for c in candidates:
        if (c / "tokenizer.model").exists():
            return c
    raise FileNotFoundError("모델 폴더를 찾지 못했습니다. --model 또는 ANIS_TRANS_MODEL 로 지정하세요. "
                            "찾아본 곳: " + ", ".join(str(c) for c in candidates))


_CUDA_PREPARED = False


def _prepare_cuda_libs():
    """pip로 설치한 nvidia-cublas-cu12(install --gpu)가 있으면 CTranslate2가 찾도록 미리 올린다.

    CTranslate2 휠에는 cuBLAS가 들어 있지 않다. 시스템에 CUDA 12 툴킷이 있으면 그것을 쓰고,
    없으면 이 패키지의 라이브러리를 쓴다.
    """
    global _CUDA_PREPARED
    if _CUDA_PREPARED or platform.system() == "Darwin":
        return
    _CUDA_PREPARED = True
    bases = []
    if getattr(sys, "frozen", False):  # 독립 실행 파일에 cuBLAS를 함께 넣어 빌드한 경우
        bases.append(os.path.join(getattr(sys, "_MEIPASS", ""), "nvidia", "cublas"))
    try:
        import nvidia.cublas as cublas
        bases += list(getattr(cublas, "__path__", []))
    except ImportError:
        pass
    import ctypes
    for base in bases:
        if os.name == "nt":
            d = os.path.join(base, "bin")
            if os.path.isdir(d) and d not in os.environ.get("PATH", ""):
                os.add_dll_directory(d)
                os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
        else:
            for name in ("libcublasLt.so.12", "libcublas.so.12"):
                path = os.path.join(base, "lib", name)
                if os.path.exists(path):
                    try:
                        ctypes.CDLL(path, mode=ctypes.RTLD_GLOBAL)
                    except OSError:
                        pass


def _ct2():
    _prepare_cuda_libs()
    import ctranslate2
    return ctranslate2


def available_devices(model_dir=None):
    """GUI 표시용: 이 컴퓨터에서 고를 수 있는 장치 목록."""
    out = ["auto", "cpu"]
    try:
        if _ct2().get_cuda_device_count() > 0:
            out.append("cuda")
    except Exception:
        pass
    return out


class Engine:
    def __init__(self, model_dir=None, device="auto", compute_type="auto",
                 threads=0, beam_size=4, max_length=512, source_limit=1024, ct2_name="ct2"):
        if device not in DEVICES:
            raise ValueError(f"device는 {', '.join(DEVICES)} 중 하나입니다.")
        import sentencepiece as spm

        self.model_dir = Path(model_dir) if model_dir else default_model_dir()
        self.sp = spm.SentencePieceProcessor(model_file=str(self.model_dir / "tokenizer.model"))
        rel = self.model_dir / "release.json"
        self.release = json.loads(rel.read_text(encoding="utf-8")) if rel.exists() else {}
        self.beam_size, self.max_length, self.source_limit = beam_size, max_length, source_limit
        self.threads, self.ct2_name = threads, ct2_name
        t0 = time.time()
        self._load(device, compute_type)
        self.info["load_seconds"] = round(time.time() - t0, 2)
        self.info["version"] = self.release.get("version", "?")

    def _load(self, device, compute_type):
        path = self.model_dir / self.ct2_name
        if not (path / "model.bin").exists():
            raise FileNotFoundError(f"CTranslate2 모델이 없습니다: {path}")
        ctranslate2 = _ct2()
        n_gpu = ctranslate2.get_cuda_device_count()
        requested = device
        if device == "auto":
            device = "cuda" if n_gpu > 0 else "cpu"
        if device == "cuda" and n_gpu == 0:
            raise RuntimeError("CUDA GPU를 찾지 못했습니다. NVIDIA 드라이버를 확인하거나 --device cpu 를 쓰세요.")
        fallback = ""
        if device == "cuda":
            try:
                supported = ctranslate2.get_supported_compute_types("cuda")
                # int8로 저장한 가중치를 GPU에서는 float16으로 풀어 계산한다
                ct = compute_type if compute_type != "auto" else next(
                    (c for c in ("float16", "int8_float16", "float32") if c in supported), "float32")
                self.translator = ctranslate2.Translator(str(path), device="cuda", compute_type=ct,
                                                         inter_threads=1, intra_threads=self.threads or 0)
                # cuBLAS는 첫 계산 때 불러오므로 한 번 돌려 봐야 실제로 쓸 수 있는지 안다
                self.translator.translate_batch([[self.sp.id_to_piece(5), self.sp.id_to_piece(3)]],
                                                beam_size=1, max_decoding_length=2)
                compute_type = ct
            except Exception as e:
                if requested != "auto":
                    raise RuntimeError(f"GPU 실행 실패: {e}\n→ CUDA 12 cuBLAS가 필요합니다. 설치 때 --gpu 옵션을 쓰거나 "
                                       "CUDA 12 툴킷을 설치하세요. CPU로 쓰려면 --device cpu.") from e
                fallback = f"GPU를 쓸 수 없어 CPU로 전환: {str(e).splitlines()[0]}"
                device, self.translator = "cpu", None
                if compute_type not in ("auto", "int8", "float32", "int8_float32"):
                    compute_type = "auto"
        if device == "cpu":
            if compute_type == "auto":
                compute_type = "int8"
            self.translator = ctranslate2.Translator(str(path), device="cpu", compute_type=compute_type,
                                                     inter_threads=1, intra_threads=self.threads or 0)
        self.info = dict(backend="ctranslate2", backend_version=ctranslate2.__version__,
                         device=device, compute_type=compute_type, model=str(path))
        if fallback:
            self.info["warning"] = fallback

    # ---------- 번역 ----------
    def translate(self, items, direction="ja-ko", line_type="대사", batch_size=16, progress=None):
        """items: Item 또는 문자열 목록. Result 목록을 같은 순서로 돌려준다."""
        if direction not in DIRECTIONS:
            raise ValueError(f"direction must be one of {DIRECTIONS}")
        items = [Item(x) if isinstance(x, str) else x for x in items]
        results = [None] * len(items)
        encoded = []
        for i, it in enumerate(items):
            if not it.text.strip():
                results[i] = Result("")
                continue
            try:
                ids, dropped = encode_input(self.sp, build_source(it.text, it.prev, it.next, line_type),
                                            direction, self.source_limit)
            except InputTooLong as e:
                results[i] = Result("", error=str(e))
                continue
            encoded.append((i, ids, dropped, "\n" in it.text.strip()))
        encoded.sort(key=lambda e: len(e[1]))  # 길이가 비슷한 것끼리 묶어 빠르게
        done = len(items) - len(encoded)  # 빈 줄·오류 줄은 이미 끝난 것으로 센다
        for start in range(0, len(encoded), batch_size):
            chunk = encoded[start:start + batch_size]
            outs = self._generate([c[1] for c in chunk])
            for (i, ids, dropped, nl), out in zip(chunk, outs):
                kept = [t for t in out if int(t) > 3]
                results[i] = Result(decode_output(self.sp, out, restore_newlines=nl), dropped_context=dropped,
                                    input_tokens=len(ids), output_tokens=len(kept) + 1)
            done += len(chunk)
            if progress:
                progress(done, len(items))
        if progress and not encoded:
            progress(len(items), len(items))
        return results

    def translate_text(self, text, direction="ja-ko", prev=(), next=(), line_type="대사"):
        r = self.translate([Item(text, list(prev), list(next))], direction, line_type)[0]
        if r.error:
            raise InputTooLong(r.error)
        return r.text

    def _generate(self, batch):
        """토큰 id 목록들 → 출력 토큰 id 목록들 (빔 4)."""
        tokens = [[self.sp.id_to_piece(t) for t in ids] for ids in batch]
        res = self.translator.translate_batch(
            tokens, beam_size=self.beam_size, max_decoding_length=self.max_length,
            max_batch_size=len(tokens), return_scores=False)
        return [[self.sp.piece_to_id(p) for p in r.hypotheses[0]] for r in res]
