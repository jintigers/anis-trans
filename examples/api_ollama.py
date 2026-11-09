"""ollama 파이썬 클라이언트로 ANIS Trans API 서버 호출하기.

  pip install ollama
  anis-trans-server            (다른 창에서 먼저 실행)
  python examples/api_ollama.py
"""
from ollama import Client

client = Client(host="http://127.0.0.1:11435")

print([m.model for m in client.list().models])

# generate: 방향은 모델 이름으로, 문맥은 options 안에
r = client.generate(model="anis-trans:ja-ko", prompt="大丈夫？",
                    options={"prev": ["先輩、顔色悪いですよ。"], "next": ["ああ、少し寝不足なだけだ。"]})
print(r.response)

# chat: system 프롬프트로 방향 지정 + 여러 줄은 줄마다 번역
r = client.chat(model="anis-trans", messages=[
    {"role": "system", "content": "한국어를 일본어로 번역"},
    {"role": "user", "content": "준비됐어?\n가자!"}])
print(r.message.content)

# 스트리밍
for part in client.chat(model="anis-trans", stream=True,
                        messages=[{"role": "user", "content": "このアイテムは<v1>ゴールドで売れます。"}]):
    print(part.message.content, end="", flush=True)
print()
