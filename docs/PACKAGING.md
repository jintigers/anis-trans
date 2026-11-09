# 배포판 만들기

ANIS Trans는 두 가지 형태로 배포할 수 있습니다.

| 형태 | 받는 사람에게 필요한 것 | 크기 | 만드는 곳 |
|---|---|---|---|
| **A. 소스 번들** (이 폴더) | Python 3.9+ 와 인터넷(설치 때 패키지 내려받기) | 약 0.3GB | 아무 OS에서나 한 번 |
| **B. 독립 실행판** (PyInstaller) | 없음. 압축 풀고 바로 실행 | Linux 614MB(tar.gz 358MB) | OS마다 그 OS에서 빌드 |

## 이 서버에서 한 것과 하지 못한 것

| 대상 | 상태 |
|---|---|
| A. 소스 번들, Linux | **확인함.** 깨끗한 가상환경에 `install.sh` 로 설치하고 `tools/smoke_test.py --gpu` 36개 항목 통과(CLI 단문·문맥·파이프·txt·jsonl, GUI 장치 전환·문장·일괄 번역, API 서버 Ollama·OpenAI 엔드포인트·스트리밍, CPU·CUDA 모두). `openai`·`ollama` 파이썬 클라이언트로도 서버 호출 확인. 헤드리스 Chromium으로 GUI 화면도 직접 조작해 확인 |
| A. `install.sh --gpu` (pip cuBLAS) | **확인함.** 시스템 CUDA 경로를 가린 상태에서 pip의 `nvidia-cublas-cu12` 라이브러리를 불러 GPU 번역 성공. GPU 초기화 실패 시 `auto` → CPU 전환도 확인 |
| B. Linux x86_64 독립 실행판 | **빌드하고 확인함** (Rocky Linux 9.5, glibc 2.34, Python 3.12, PyInstaller 6.22). CPU·CUDA 번역과 GUI 서버 동작 확인 |
| A. Windows (`install.cmd`) | **시험하지 못함.** Windows 기기 없음 |
| A. macOS (`install.sh`) | **시험하지 못함.** macOS 기기 없음 |
| B. Windows / macOS 독립 실행판 | **이 서버에서 빌드할 수 없음.** PyInstaller는 교차 빌드를 지원하지 않습니다. 아래 스크립트를 각 OS에서 실행해야 합니다 |

## B. 독립 실행판 빌드

빌드 스크립트는 모두 `.build-venv` 가상환경을 만들고 `pip install -e ".[build]"` 한 뒤 `packaging/build.py` 를 실행합니다. `build.py` 가 하는 일은 다음과 같습니다.

1. PyInstaller로 `anis-trans`(`.exe`)를 onedir 형식으로 빌드합니다. ctranslate2·sentencepiece·GUI 화면이 들어갑니다.
2. `release/anis-trans-<버전>-<os>-<arch>/` 에 실행 파일, `model/`(ct2 int8, tokenizer, release.json), README, LICENSE-ko/en, 예제, GUI·API 서버 실행기를 모읍니다.
3. 빌드한 실행 파일로 "今日は雨が降ってるね。"를 번역해 봅니다. 실패하면 빌드를 실패로 처리합니다.
4. 압축합니다. Linux는 `.tar.gz`, Windows·macOS는 `.zip` 입니다.

번들 폴더 밖의 파일은 들어가지 않습니다. 번들의 `model/`, `src/`, 문서만 씁니다.

### Linux

```bash
packaging/build_linux.sh                 # → release/anis-trans-0.1.0-linux-x86_64.tar.gz
packaging/build_linux.sh --with-cublas   # GPU용 cuBLAS까지 포함 (약 +1GB)
```

- 빌드한 시스템의 glibc보다 오래된 배포판에서는 실행되지 않습니다. 이 서버(glibc 2.34)에서 빌드하면 Ubuntu 22.04+, Debian 12+, RHEL/Rocky 9+ 에서 돕니다. 더 넓게 배포하려면 Rocky/Alma 8(glibc 2.28) 같은 오래된 시스템이나 컨테이너에서 빌드하세요. CTranslate2 휠이 요구하는 최소 버전이 manylinux_2_28 입니다.
- `--with-cublas` 없이 빌드하면 GPU를 쓸 때 받는 PC에 CUDA 12 cuBLAS(`libcublas.so.12`)가 있어야 합니다. 없으면 경고를 보여 주고 CPU로 실행합니다.

### Windows (Windows 10/11 x64에서)

```bat
packaging\build_windows.cmd                 & rem → release\anis-trans-0.1.0-windows-x86_64.zip
packaging\build_windows.cmd --with-cublas   & rem GPU용 cuBLAS DLL 포함 (약 +1GB)
```

- python.org 의 64비트 Python 3.10~3.12를 권장합니다. Microsoft Store판 Python은 경로 문제로 PyInstaller와 잘 맞지 않습니다.
- 결과 폴더에는 `anis-trans.exe`(CLI)와 `ANIS Trans GUI.cmd`(두 번 클릭용 GUI)가 들어 있습니다. CLI 실행 파일은 콘솔 앱이므로 GUI를 띄우면 콘솔 창이 함께 열립니다. 그 창을 닫으면 GUI 서버도 끝납니다.
- GPU: CTranslate2 Windows 휠도 cuBLAS를 포함하지 않습니다. CUDA 12 툴킷(`cublas64_12.dll`)이 있는 PC는 그대로 GPU를 씁니다. 없는 PC에 배포하려면 `--with-cublas` 로 빌드하세요. 프로그램이 `_internal\nvidia\cublas\bin` 을 DLL 검색 경로에 넣습니다. **이 동작은 Windows에서 시험하지 못했습니다.**
- 서명하지 않은 exe는 SmartScreen 경고가 뜹니다. 정식 배포 때는 코드 서명 인증서로 서명하세요: `signtool sign /fd sha256 /tr http://timestamp.digicert.com /td sha256 /a release\…\anis-trans.exe`.

### macOS (Apple Silicon 또는 Intel Mac에서)

```bash
packaging/build_macos.sh                 # → release/anis-trans-0.1.0-macos-arm64.zip (Apple Silicon)
CODESIGN_IDENTITY="Developer ID Application: 이름 (팀ID)" packaging/build_macos.sh   # 서명 포함
```

- Apple Silicon에서 빌드하면 arm64판, Intel Mac에서 빌드하면 x86_64판이 나옵니다. 두 판을 따로 배포하세요. CTranslate2 휠이 아키텍처별로 나뉘어 있어 universal2 빌드는 하지 않습니다.
- macOS에서는 CTranslate2 CPU(int8, Apple Accelerate)로 실행합니다. CTranslate2는 Apple GPU(MPS)를 지원하지 않습니다.
- 서명·공증하지 않으면 Gatekeeper가 실행을 막습니다. 받는 사람이 `xattr -dr com.apple.quarantine anis-trans-0.1.0-macos-arm64` 를 실행해야 합니다. 정식 배포 때는 `CODESIGN_IDENTITY` 로 서명하고 `xcrun notarytool submit … --wait` 로 공증한 뒤 `xcrun stapler staple` 하세요.
- `.app` 번들이 아니라 폴더 형태입니다. Finder에서는 `ANIS Trans GUI.command` 를 두 번 클릭해 GUI를 엽니다.

## 라이선스를 바꿀 때

`LICENSE-ko.md`·`LICENSE-en.md` 를 바꾸고(필요하면 `pyproject.toml` 의 license 항목도) 다시 빌드하세요.

## 검토했지만 쓰지 않은 방법

- **Nuitka**: 실행 속도 이점이 거의 없고(계산은 CTranslate2 네이티브 코드), 빌드가 느리고 OS별 C 컴파일러가 필요합니다.
- **Briefcase / py2app / MSIX 설치 프로그램**: OS별 설치 프로그램은 만들 수 있지만, 서명 인증서 없이는 이점이 적습니다. 라이선스와 배포 경로가 정해진 뒤 검토할 만합니다.
- **conda-pack**: 크기가 크고 conda 환경이 필요합니다.
