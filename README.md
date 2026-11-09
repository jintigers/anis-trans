# ANIS Trans 0.1

일본어 ↔ 한국어 번역 모델입니다(약 3억 파라미터, 버전 0.1). 인터넷 연결 없이 내 컴퓨터에서 번역합니다.

- 방향: 일본어 → 한국어, 한국어 → 일본어 (기본은 문장마다 자동 판별)
- 앞뒤 문맥: 대상 문장 앞뒤의 대사를 같이 넣으면 말투·지시어를 더 잘 맞춥니다
- 쓰는 방법 세 가지: 명령줄(CLI), 브라우저 화면(GUI), Ollama·OpenAI 호환 로컬 API 서버
- 실행 엔진: CTranslate2 (CPU int8 / NVIDIA GPU). Linux·Windows·macOS에서 같은 명령으로 실행합니다

## 모델 파일 받기

이 저장소에는 프로그램 소스만 있고, 모델 파일(`model/ct2`, `model/tokenizer.model`)은 들어 있지 않습니다.
모델과 실행 프로그램이 모두 든 배포판은 **[ANIS 한글패치 커뮤니티 다운로드](https://krmod.anis.co.kr/ai-lab?section=download)** 에서 라이선스에 동의하고 받아 주세요 (로그인 필요).

- 바로 쓰려면: 받은 압축 파일을 풀고 아래 설치 방법을 따르면 됩니다.
- 이 저장소의 소스로 실행하려면: 받은 배포판의 `model/` 폴더 내용을 이 저장소의 `model/` 에 복사하거나, `--model <폴더>` / 환경 변수 `ANIS_TRANS_MODEL` 로 모델 폴더를 지정하세요.

웹에서 먼저 써 보려면 [번역 테스트](https://krmod.anis.co.kr/ai-lab?section=test)를 이용하세요.

## 라이선스 요약 (초안)

- 개인·비영리 이용은 무료입니다.
- 후원·광고·판매·기업 이용 등 **모든 영리 이용에는 별도 상업 라이선스가 필요합니다.**
- **파인튜닝·역변환·재배포는 금지됩니다.**

전문은 [LICENSE-ko.md](LICENSE-ko.md)(정본)와 [LICENSE-en.md](LICENSE-en.md)(영어 번역)에 있습니다. 아직 초안이라 내용이 바뀔 수 있습니다. 프로그램을 처음 실행할 때 이 요약이 한 번 표시됩니다.

## 알려진 한계와 개선 계획

ANIS Trans는 아직 개발 중인 모델입니다. 지금 알고 있는 한계를 적어 두며, 아래 항목은 모두 다음 공개판들에서 계속 개선할 예정입니다.

| 한계 | 내용 |
|---|---|
| 호칭·성별 선택 | 문맥 없이 한 줄만 넣으면 先輩를 "형"으로 옮기는 것처럼 호칭이나 화자의 성별을 잘못 고를 수 있습니다. 앞뒤 대사를 함께 넣으면(`--prev`, `--next`, `--context-lines`) 줄어듭니다 |
| 사투리·옛말투 어미 | のう·じゃ 같은 어미를 말투로 살리지 못하고 단어처럼 옮기는 경우가 남아 있습니다 |
| 변수·형식 보존 | 형식 보존은 88.3%입니다. 한 문장에 변수가 여러 개면 일부가 빠지거나 바뀔 수 있으니 번역 후 확인하세요 |
| 게임 밖 문장 | 게임 대사(JK Trans Bench 56.41)에 비해 강연(19.57)·뉴스(24.13) 같은 긴 일반 문장은 점수가 낮습니다 |
| 앞뒤 문맥 활용 | 문맥을 넣으면 나아지지만, 먼 문맥까지 정확히 반영하는 능력(문맥 점수 29.95)은 아직 부족합니다 |
| 실행 환경 | GPU는 NVIDIA만 지원합니다. Python 없이 쓰는 독립 실행판은 지금 Linux용만 배포합니다 |

---

## 1. 설치

### 필요한 것

| 항목 | 내용 |
|---|---|
| Python | 3.9 이상 (3.10~3.12 권장). Windows는 [python.org](https://www.python.org/downloads/) 설치 때 **"Add python.exe to PATH"** 를 켜 주세요 |
| 디스크 | 설치 후 약 0.6GB (GPU용 cuBLAS를 pip로 받으면 +1.1GB) |
| 메모리 | CPU 실행 시 약 1GB |
| GPU (선택) | NVIDIA GPU + 드라이버. CUDA 12 툴킷이 없으면 설치 때 `--gpu` 옵션을 쓰세요 |

설치 스크립트는 이 폴더 안에 `.venv` 가상환경을 만들고 필요한 패키지(ctranslate2, sentencepiece)를 내려받습니다. 시스템 Python은 건드리지 않습니다.

### Linux / macOS

```bash
cd anis-trans-0.1
./install.sh
```

```bash
./install.sh --gpu      # NVIDIA GPU를 쓰는데 CUDA 12 툴킷이 없을 때 (Linux)
```

### Windows

폴더에서 `install.cmd` 를 두 번 클릭하거나, 명령 프롬프트에서:

```bat
cd anis-trans-0.1
install.cmd
install.cmd --gpu
```

`--gpu` 는 NVIDIA GPU를 쓰는데 CUDA 12 툴킷을 설치하지 않은 PC에 씁니다.

### Python 없이 쓰는 독립 실행판

`packaging/` 의 빌드 스크립트로 Python 없이 실행되는 압축 파일을 만들 수 있습니다. 압축을 풀고 `anis-trans`(Windows는 `anis-trans.exe`)를 바로 실행하면 됩니다. 만드는 방법은 [docs/PACKAGING.md](docs/PACKAGING.md)에 있습니다.

### 설치 확인

```bash
./anis-trans --info                      # Windows: anis-trans --info
.venv/bin/python tools/smoke_test.py     # Windows: .venv\Scripts\python tools\smoke_test.py
```

`tools/smoke_test.py --gpu` 는 GPU까지 점검합니다. CLI·GUI·API 서버를 모두 시험하고, 모든 항목이 통과하면 `ALL OK` 가 나옵니다.

### 어디서나 `anis-trans` 로 실행하기 (선택)

- Linux / macOS: `ln -s "$PWD/anis-trans" ~/.local/bin/anis-trans` (`anis-trans-gui`, `anis-trans-server` 도 같은 방법)
- Windows: 이 폴더를 사용자 환경 변수 `Path` 에 추가하면 어디서나 `anis-trans` 로 실행됩니다
- 또는 가상환경을 켜도 됩니다: `source .venv/bin/activate` (Windows: `.venv\Scripts\activate`)

아래 예시는 모두 `anis-trans` 로 적었습니다. 이 폴더에서 실행할 때 Linux·macOS는 `./anis-trans`, Windows PowerShell은 `.\anis-trans` 로 입력하세요.

---

## 2. 명령줄(CLI) 사용법

```bash
# 단문 번역: 방향은 자동 판별 (가나가 있으면 일→한, 한글이 있으면 한→일)
anis-trans "今日は雨が降ってるね。"
anis-trans "오늘 저녁은 뭐 먹을까?"

# 방향 고정
anis-trans -d ja-ko "東京"
anis-trans -d ko-ja "선배, 얼굴색이 안 좋아요."

# 앞뒤 문맥 (--prev 는 오래된 것부터, --next 는 가까운 것부터 여러 번 쓸 수 있음)
anis-trans --prev "先輩、顔色悪いですよ。" --next "ああ、少し寝不足なだけだ。" "大丈夫？"

# 파일 일괄 번역: 한 줄 = 한 문장, 빈 줄은 그대로
anis-trans -f examples/sample_ja.txt -o out.txt
anis-trans -f examples/sample_ja.txt --context-lines 2,1 -o out.txt   # 앞 2줄·뒤 1줄을 문맥으로
anis-trans -f examples/sample_ja.txt --with-source                     # 원문<TAB>번역

# JSONL: 줄마다 {"text", "prev", "next", "direction"} → "translation" 을 붙여 출력
anis-trans -f examples/sample.jsonl -o out.jsonl

# 표준입력 파이프
cat examples/sample_ja.txt | anis-trans -d ja-ko > out.txt

# 인자 없이 실행하면 대화형 모드 (모델을 한 번만 불러옴)
anis-trans

# 장치 선택
anis-trans --device cpu  "…"     # CPU (int8)
anis-trans --device cuda "…"     # NVIDIA GPU
```

### 주요 옵션

| 옵션 | 설명 | 기본값 |
|---|---|---|
| `-d`, `--direction` | `auto`, `ja-ko`, `ko-ja` | `auto` |
| `--prev`, `--next` | 앞·뒤 문맥 문장 (여러 번 지정 가능) | 없음 |
| `--context-lines 앞,뒤` | 파일·파이프 번역 때 이웃한 줄을 문맥으로 넣음 | `0,0` |
| `--line-type` | 문맥을 쓸 때 붙이는 줄 종류: 대사, 독백, 나레이션, 선택지, 시스템 | 대사 |
| `-f`, `-o` | 입력 파일 (`.txt`, `.jsonl`), 출력 파일 | 표준입출력 |
| `--format` | `auto`(확장자로 판별), `txt`, `jsonl` | `auto` |
| `--device` | `auto`, `cpu`, `cuda` | `auto` |
| `--compute-type` | `auto`, `int8`, `int8_float16`, `float16`, `float32` | `auto` |
| `--threads` | CPU 스레드 수 (0이면 자동) | 0 |
| `--beam` | 빔 크기 | 4 |
| `--encoding` | 파일·파이프 문자 인코딩 | `utf-8` |
| `-v`, `--info`, `-V` | 장치·속도 표시 / 장치 정보만 보기 / 버전 | |

번역에 실패한 줄이 있으면 종료 코드가 1이고, 그 줄은 빈 칸으로 남긴 채 이유를 표준오류에 출력합니다.

---

## 3. GUI (브라우저 화면)

```bash
anis-trans-gui                 # Windows: anis-trans-gui.cmd 두 번 클릭
anis-trans --gui               # 같은 동작
```

macOS는 Finder에서 `ANIS Trans GUI.command` 를 두 번 클릭해도 됩니다. 실행하면 기본 브라우저에 `http://127.0.0.1:7870/` 이 열립니다. 7870 포트가 사용 중이면 다음 빈 포트를 고르고, 그 주소를 터미널에 표시합니다. 끝낼 때는 터미널 창을 닫거나 Ctrl+C를 누르세요.

- **문장 번역**: 입력창과 출력창, 방향(자동·일→한·한→일, ⇄로 바꾸기), 줄 종류, 앞뒤 문맥 칸이 있습니다. 번역 단축키는 Ctrl+Enter(맥은 ⌘+Enter)입니다. "줄마다 따로 번역"을 켜면 여러 줄을 각각 번역합니다.
- **일괄 번역**: `.txt`/`.jsonl` 파일을 고르거나 붙여넣고, 앞뒤 문맥 줄 수를 정해 번역합니다. 진행률이 표시되고, 결과는 `.txt`(또는 `.jsonl`)나 원문+번역 `.tsv` 로 내려받습니다.
- **장치·정밀도**: 오른쪽 위에서 자동·CPU·GPU(CUDA)를 고르고 "적용"을 누르면 모델을 다시 불러옵니다. 이 컴퓨터에서 쓸 수 없는 장치는 비활성화됩니다.

| 옵션 | 설명 |
|---|---|
| `--port 7870` | 포트 |
| `--device`, `--compute-type` | 처음 불러올 장치·정밀도 |
| `--no-browser` | 브라우저를 자동으로 열지 않음 |
| `--host 127.0.0.1` | 기본은 이 컴퓨터에서만 접속됩니다. `0.0.0.0` 으로 열면 같은 네트워크의 다른 기기도 접속할 수 있으니 주의하세요 |

### 왜 로컬 웹 UI인가

Qt·Tk 데스크톱 앱 대신 **Python 표준 라이브러리 HTTP 서버와 브라우저 화면**을 골랐습니다.

1. **추가 의존성이 없습니다.** Qt(PySide6)는 플랫폼별 바이너리만 100MB가 넘고, Gradio 같은 웹 프레임워크도 의존성이 수십 개입니다. 이 GUI는 CLI와 같은 두 패키지(ctranslate2, sentencepiece)만 씁니다.
2. **일본어·한국어 입력이 안정적입니다.** Tk는 Linux(X11)에서 한글·일본어 입력기(IME) 조합이 자주 깨지고, macOS의 Homebrew·pyenv Python에는 Tk가 빠져 있는 경우가 많습니다. 브라우저는 모든 OS에서 IME·글꼴·복사/붙여넣기를 제대로 처리합니다.
3. **어디서나 같은 화면입니다.** Linux·Windows·macOS에서 똑같이 동작하고, 독립 실행판(PyInstaller)에도 그대로 들어갑니다. 원격 데스크톱이나 SSH 포트 포워딩으로도 쓸 수 있습니다.

서버는 기본으로 127.0.0.1에만 열립니다. 다른 웹사이트가 이 서버로 요청을 보내지 못하도록 전용 헤더 확인도 합니다. 입력한 문장은 컴퓨터 밖으로 나가지 않습니다.

---

## 4. 로컬 API 서버 (Ollama·OpenAI 호환)

Ollama와 vLLM은 이 모델 같은 인코더-디코더 번역 모델을 돌리지 못합니다. 그래서 같은 API 형식으로 응답하는 작은 서버를 넣었습니다. Ollama나 OpenAI API를 쓰는 번역 도구·스크립트에서 주소와 모델 이름만 바꾸면 됩니다.

```bash
anis-trans-server                          # Windows: anis-trans-server.cmd
anis-trans --serve                         # 같은 동작
anis-trans-server --device cuda --port 11434   # GPU로, Ollama 기본 포트에서 (Ollama를 끈 뒤)
```

기본 주소는 `http://127.0.0.1:11435` 입니다. 실제 Ollama(11434)와 겹치지 않도록 한 칸 옆 포트를 씁니다.

### 엔드포인트

| 형식 | 엔드포인트 |
|---|---|
| Ollama | `GET /api/tags`(모델 목록), `POST /api/generate`, `POST /api/chat`, `POST /api/show`, `GET /api/ps`, `GET /api/version` |
| OpenAI | `GET /v1/models`, `POST /v1/chat/completions`, `POST /v1/completions` |

- 비스트리밍 응답은 각 API의 표준 형식을 따릅니다. OpenAI는 `choices[0].message.content` 와 `usage`, Ollama는 `response` 또는 `message.content` 와 `done`, `eval_count` 등입니다.
- 스트리밍도 됩니다. Ollama는 NDJSON이고 `stream` 을 생략하면 켜집니다(Ollama와 같음). OpenAI는 `"stream": true` 일 때 SSE로 보내고, 마지막에 `data: [DONE]` 을 보냅니다. 번역을 다 마친 뒤 줄 단위로 나눠 보내므로, 글자가 하나씩 나오지는 않습니다.
- `temperature`, `top_p` 같은 샘플링 옵션은 무시합니다. 번역은 항상 빔 4로 합니다.

### 모델 이름과 번역 방향

| 모델 이름 | 방향 |
|---|---|
| `anis-trans` (`anis-trans:latest`, `anis-trans:auto`) | 문장마다 자동 판별 |
| `anis-trans:ja-ko` | 일본어 → 한국어 |
| `anis-trans:ko-ja` | 한국어 → 일본어 |

방향은 다음 순서로 정합니다.

1. 요청의 `anis.direction`
2. 모델 이름
3. system 프롬프트 속 방향 표현. 예: "Japanese to Korean", "ko-ja", "일본어로", "한국어로 번역"
4. 문장마다 자동 판별

system 프롬프트의 나머지 지시는 쓰지 않습니다. 이 모델은 지시를 따르는 대화형 모델이 아니라 번역 모델이기 때문입니다.

모델 이름을 바꿀 수 없는 도구(예: `gpt-4o-mini` 로 고정)에는 `--accept-any-model` 을 쓰세요. 모르는 이름도 자동 방향으로 처리합니다.

### 무엇을 번역하나 — 문맥 전달 규칙

- `/api/chat`, `/v1/chat/completions`: **마지막 user 메시지**를 번역합니다.
- `/api/generate`, `/v1/completions`: `prompt` 를 번역합니다.
- 여러 줄을 보내면 기본으로 **줄마다 따로** 번역하고, 줄 구조(빈 줄 포함)를 그대로 돌려줍니다.

문맥은 세 가지 방법으로 넣습니다.

1. **채팅 기록**: 마지막 user 메시지 앞의 user 메시지들(한 줄짜리)이 앞 문맥(`<prev>`)이 됩니다. 기본은 최근 3개이고, assistant 메시지는 쓰지 않습니다. 앞 대사를 차례로 보내는 도구라면 따로 설정하지 않아도 문맥이 들어갑니다.
2. **`anis` 객체**: 요청 본문에 넣습니다. Ollama 요청은 `options` 안에 넣어도 되고, OpenAI 파이썬 SDK는 `extra_body={"anis": {...}}` 로 넣습니다.

   | 키 | 뜻 | 기본값 |
   |---|---|---|
   | `prev` | 앞 문맥 (문자열 또는 목록, 오래된 것부터) | 없음 |
   | `next` | 뒷 문맥 (문자열 또는 목록, 가까운 것부터) | 없음 |
   | `direction` | `auto`, `ja-ko`, `ko-ja` | 모델 이름에 따름 |
   | `line_type` | 대사, 독백, 나레이션, 선택지, 시스템 | 대사 |
   | `history` | 채팅 기록에서 문맥으로 쓸 user 메시지 수 (0이면 안 씀) | 3 |
   | `split_lines` | 여러 줄을 줄마다 번역할지. `false` 면 한 문장으로 보고 줄바꿈을 `<br>` 로 넣음 | `true` |
   | `context_lines` | 줄마다 번역할 때 이웃한 줄을 문맥으로 쓸 수 `"앞,뒤"` | `"0,0"` |

   여러 줄을 줄마다 번역할 때 `prev`·채팅 기록은 첫 줄 앞에, `next` 는 마지막 줄 뒤에 붙습니다.
3. **모델 입력 형식 직접 쓰기**: 메시지에 `<tgt>` 가 들어 있으면 그대로 넣습니다. 예: `<prev> <B> <대사> 準備はいい？ <tgt> <A> <대사> 行くぞ`

### 호출 예

```bash
# Ollama 형식
curl http://127.0.0.1:11435/api/generate -d '{"model":"anis-trans:ja-ko","prompt":"今日は雨が降ってるね。","stream":false}'
curl http://127.0.0.1:11435/api/chat -d '{"model":"anis-trans","stream":false,
  "messages":[{"role":"user","content":"大丈夫？"}],
  "options":{"prev":["先輩、顔色悪いですよ。"],"next":"ああ、少し寝不足なだけだ。"}}'

# OpenAI 형식
curl http://127.0.0.1:11435/v1/chat/completions -H "Content-Type: application/json" \
  -d '{"model":"anis-trans:ko-ja","messages":[{"role":"user","content":"오늘 저녁은 뭐 먹을까?"}]}'
```

파이썬 예제는 [examples/api_openai.py](examples/api_openai.py)(`pip install openai`)와 [examples/api_ollama.py](examples/api_ollama.py)(`pip install ollama`)에 있습니다.

### 서버 옵션

| 옵션 | 설명 | 기본값 |
|---|---|---|
| `--host` | `127.0.0.1` 이면 이 컴퓨터에서만 접속. `0.0.0.0` 으로 열면 다른 기기도 접속 가능 (`--api-key` 권장) | `127.0.0.1` |
| `--port` | 포트. 사용 중이면 오류를 내고 끝냅니다 | 11435 |
| `--device`, `--compute-type`, `--threads` | 장치·정밀도·CPU 스레드 | `auto` |
| `--api-key 키` | 지정하면 `Authorization: Bearer 키` 가 있는 요청만 받음 | 없음 |
| `--allow-origin URL` | 브라우저 웹앱에서 호출을 허용할 출처 (여러 번 지정, `*` 는 모두). 기본은 localhost 출처만 허용하고 다른 웹사이트의 브라우저 요청은 막음 | localhost |
| `--accept-any-model` | 모르는 모델 이름도 자동 방향으로 처리 | 끔 |
| `-v` | 요청 기록 출력 | 끔 |

---

## 5. CPU / GPU 선택

| `--device` | 동작 |
|---|---|
| `auto` (기본) | NVIDIA CUDA GPU가 있으면 GPU, 없으면 CPU. GPU 초기화에 실패하면(cuBLAS 없음 등) 경고를 보여 주고 CPU로 바꿉니다 |
| `cpu` | int8로 계산합니다 |
| `cuda` | NVIDIA GPU. 실패하면 이유와 해결 방법을 보여 주고 멈춥니다 |

- 모델 파일은 `model/ct2`(CTranslate2 int8 형식) 하나입니다. CPU는 int8, GPU는 float16으로 계산합니다(`--compute-type int8_float16` 등으로 바꿀 수 있음).
- **NVIDIA GPU**: CTranslate2 패키지에는 cuBLAS가 들어 있지 않습니다. CUDA 12 툴킷이 설치된 PC는 그대로 GPU를 씁니다. 툴킷이 없으면 `install.sh --gpu`/`install.cmd --gpu` 로 pip용 cuBLAS(`nvidia-cublas-cu12`, 약 1.1GB)를 받으세요. 프로그램이 이 라이브러리를 자동으로 찾아 씁니다.
- **macOS**: CTranslate2는 macOS에서 CPU(Apple Accelerate)를 쓰고, Apple GPU(MPS)는 지원하지 않습니다. 그래서 macOS에서는 CPU int8로 실행합니다.
- **AMD GPU / Intel GPU**: 지원하지 않습니다. CPU로 실행됩니다.

---

## 6. 입력 형식 참고

- **문맥**: 문맥을 주면 모델 입력은 `<prev> <대사> 앞문장 <tgt> <대사> 대상 <next> <대사> 뒷문장` 형태가 됩니다. `<대사>` 자리는 `--line-type` 으로 바꿀 수 있습니다. 문맥이 없으면 `<tgt> 대상` 만 넣습니다.
- **직접 입력**: 문장에 `<tgt>` 가 들어 있으면 이미 모델 형식으로 쓴 것으로 보고 그대로 넣습니다. 화자 태그(`<A>`~`<H>`)도 이때 쓸 수 있습니다. 예: `"<prev> <B> <대사> 準備はいい？ <tgt> <A> <대사> 行くぞ"`
- **줄바꿈**: 한 문장 안의 줄바꿈은 `<br>` 로 바꿔 넣고, 번역문에서 다시 줄바꿈으로 돌립니다. 파일 번역은 한 줄 = 한 문장을 유지하므로 `<br>` 그대로 둡니다.
- **게임 변수**: `<v1>` 같은 자리 표시자는 대체로 그대로 남습니다. 다만 한 문장에 변수가 여러 개면 일부가 빠지거나 바뀔 수 있으니 번역 후 확인하세요.
- **길이**: 방향 접두와 끝 토큰을 합쳐 1,024토큰까지 넣을 수 있습니다. 넘치면 가장 먼 앞 문맥부터, 그다음 가장 먼 뒷 문맥을 통째로 뺍니다. 대상 문장은 자르지 않습니다. 대상 문장만으로 넘치면 그 줄은 오류로 표시됩니다.
- **생성**: 빔 4, 출력 최대 512토큰(`--max-length`).

---

## 7. 문제 해결

| 증상 | 해결 |
|---|---|
| Windows에서 파이프 결과가 깨짐 | 명령 프롬프트: `chcp 65001`. PowerShell 5.1: `$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()`. 파일 번역(`-f`, `-o`)은 영향을 받지 않습니다 |
| `GPU 실행 실패 … libcublas` | CUDA 12 툴킷을 설치하거나 `install.sh --gpu`/`install.cmd --gpu` 로 다시 설치하세요. 당장은 `--device cpu` 로 쓸 수 있습니다 |
| `--device auto` 인데 CPU로 실행됨 | `anis-trans --info` 의 `warning` 줄에 이유가 나옵니다 |
| API 서버: `… 에 열 수 없습니다` | 그 포트를 다른 프로그램(예: Ollama)이 쓰고 있습니다. `--port` 로 다른 포트를 고르세요 |
| API 서버: `model '…' not found` | 모델 이름을 `anis-trans:ja-ko` 등으로 바꾸거나 `--accept-any-model` 을 쓰세요 |
| API 서버: `origin not allowed` | 브라우저 웹앱에서 부를 때는 `--allow-origin <웹앱 주소>` 로 허용하세요 |
| macOS: "확인되지 않은 개발자" | 독립 실행판은 서명되지 않았습니다. 폴더에서 `xattr -dr com.apple.quarantine .` 을 실행하거나, Finder에서 오른쪽 클릭 → 열기를 고르세요 |
| Windows: SmartScreen 경고 | "추가 정보 → 실행"을 누르세요. 독립 실행판은 서명되지 않았습니다 |
| GUI가 열리지 않음 | 터미널에 표시된 주소(`http://127.0.0.1:포트/`)를 브라우저에 직접 입력하세요 |
| 모델 폴더를 못 찾음 | `--model <폴더>` 를 쓰거나 환경 변수 `ANIS_TRANS_MODEL` 을 지정하세요 |

---

## 8. 폴더 구성

```
anis-trans-0.1/
├─ README.md                       이 문서
├─ LICENSE-ko.md, LICENSE-en.md    라이선스 (초안, 한국어 정본·영어 번역)
├─ install.sh / install.cmd        설치 (Linux·macOS / Windows)
├─ anis-trans, anis-trans-gui, anis-trans-server              실행기 (Linux·macOS)
├─ anis-trans.cmd, anis-trans-gui.cmd, anis-trans-server.cmd  실행기 (Windows)
├─ ANIS Trans GUI.command          macOS 두 번 클릭용 GUI 실행기
├─ pyproject.toml                  Python 패키지 정의 (anis-trans)
├─ src/anis_trans/                 프로그램 (CLI, 엔진, 입력 인코딩, 웹 GUI, API 서버)
├─ model/
│  ├─ ct2/                         번역 모델 (CTranslate2 int8)
│  ├─ tokenizer.model              토크나이저
│  └─ release.json                 버전 정보
├─ examples/                       예제 입력(txt, jsonl), API 호출 예제(api_openai.py, api_ollama.py)
├─ tools/smoke_test.py             설치 점검
├─ packaging/                      독립 실행판 빌드 스크립트 (Linux·macOS·Windows)
└─ docs/PACKAGING.md               배포판 빌드 방법
```

## 9. 버전

ANIS Trans **0.1**은 첫 공개판입니다. 공개판은 0.1 → 0.2처럼 올리고, 그 사이의 학습 빌드는 끝자리를 붙입니다(0.1.1 …). 프로그램 내부 버전 번호(`anis-trans -V`)는 0.1.0으로 표시됩니다.
