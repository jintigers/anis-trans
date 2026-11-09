"""독립 실행 파일 빌드 (Python 없이 실행되는 배포판).

PyInstaller는 교차 빌드를 하지 못하므로 각 OS에서 직접 실행한다.
  Linux  : packaging/build_linux.sh
  macOS  : packaging/build_macos.sh
  Windows: packaging\\build_windows.cmd
(셋 다 .build-venv 를 만들고 이 스크립트를 부른다.)

  python packaging/build.py [--with-cublas] [--no-archive]

결과: release/anis-trans-<버전>-<os>-<arch>/ 와 같은 이름의 .zip(Windows·macOS) 또는 .tar.gz(Linux)
  anis-trans(.exe)        CLI (anis-trans --gui 로 GUI)
  ANIS Trans GUI.*        두 번 클릭용 GUI 실행기
  anis-trans-server(.cmd) API 서버 실행기 (anis-trans --serve)
  model/                  CTranslate2 int8 모델 + tokenizer.model + release.json
  README.md, LICENSE-ko.md, LICENSE-en.md
"""
import argparse
import platform
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def os_tag():
    system = {"Windows": "windows", "Darwin": "macos", "Linux": "linux"}.get(platform.system(), platform.system().lower())
    machine = platform.machine().lower()
    machine = {"amd64": "x86_64", "x64": "x86_64", "aarch64": "arm64"}.get(machine, machine)
    return f"{system}-{machine}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--with-cublas", action="store_true",
                    help="pip nvidia-cublas-cu12 를 실행 파일에 함께 넣음 (Linux·Windows, 약 +1GB). "
                         "넣지 않으면 GPU 사용 시 PC에 CUDA 12 cuBLAS가 있어야 함")
    ap.add_argument("--no-archive", action="store_true", help="압축 파일을 만들지 않음")
    args = ap.parse_args()

    from anis_trans import __version__
    import PyInstaller.__main__

    model = ROOT / "model"
    for need in ("ct2/model.bin", "tokenizer.model", "release.json"):
        if not (model / need).exists():
            raise SystemExit(f"모델 파일이 없습니다: model/{need}")

    work = ROOT / "build"
    name = f"anis-trans-{__version__}-{os_tag()}"
    out = ROOT / "release" / name
    if out.exists():
        shutil.rmtree(out)
    pyi = [
        str(ROOT / "packaging" / "entry.py"),
        "--name", "anis-trans", "--onedir", "--console", "--noconfirm", "--clean",
        "--paths", str(ROOT / "src"),
        "--collect-all", "ctranslate2",
        "--collect-binaries", "sentencepiece",
        "--collect-submodules", "anis_trans",
        "--collect-data", "anis_trans",
        "--exclude-module", "torch", "--exclude-module", "transformers",
        "--exclude-module", "tkinter", "--exclude-module", "matplotlib",
        "--distpath", str(work / "dist"), "--workpath", str(work / "work"), "--specpath", str(work),
    ]
    if args.with_cublas:
        if platform.system() == "Darwin":
            raise SystemExit("macOS에는 CUDA가 없습니다 (--with-cublas 불필요).")
        pyi += ["--collect-binaries", "nvidia.cublas"]
    PyInstaller.__main__.run(pyi)

    shutil.copytree(work / "dist" / "anis-trans", out)
    (out / "model").mkdir()
    shutil.copytree(model / "ct2", out / "model" / "ct2")
    for f in ("tokenizer.model", "release.json"):
        shutil.copy2(model / f, out / "model" / f)
    for f in ("README.md", "LICENSE-ko.md", "LICENSE-en.md"):
        shutil.copy2(ROOT / f, out / f)
    if (ROOT / "examples").is_dir():
        shutil.copytree(ROOT / "examples", out / "examples")

    system = platform.system()
    if system == "Windows":
        (out / "ANIS Trans GUI.cmd").write_text(
            '@echo off\r\n"%~dp0anis-trans.exe" --gui %*\r\nif errorlevel 1 pause\r\n', encoding="utf-8")
        (out / "ANIS Trans API server.cmd").write_text(
            '@echo off\r\n"%~dp0anis-trans.exe" --serve %*\r\nif errorlevel 1 pause\r\n', encoding="utf-8")
    else:
        launcher = out / ("ANIS Trans GUI.command" if system == "Darwin" else "anis-trans-gui")
        launcher.write_text('#!/usr/bin/env sh\ncd "$(dirname "$0")" && exec ./anis-trans --gui "$@"\n', encoding="utf-8")
        launcher.chmod(0o755)
        server = out / "anis-trans-server"
        server.write_text('#!/usr/bin/env sh\ncd "$(dirname "$0")" && exec ./anis-trans --serve "$@"\n', encoding="utf-8")
        server.chmod(0o755)

    # 빌드한 실행 파일로 바로 번역해 본다
    exe = out / ("anis-trans.exe" if system == "Windows" else "anis-trans")
    r = subprocess.run([str(exe), "--device", "cpu", "今日は雨が降ってるね。"], capture_output=True, text=True,
                       encoding="utf-8", timeout=300)
    print("self-test:", r.returncode, r.stdout.strip(), r.stderr.strip()[-300:])
    if r.returncode != 0:
        raise SystemExit("빌드한 실행 파일 자체 시험 실패")

    if not args.no_archive:
        if system == "Linux":
            archive = out.parent / (name + ".tar.gz")
            with tarfile.open(archive, "w:gz") as t:
                t.add(out, arcname=name)
        else:
            archive = Path(shutil.make_archive(str(out), "zip", out.parent, name))
        print("archive:", archive)
    print("done:", out)


if __name__ == "__main__":
    main()
