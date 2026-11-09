"""OpenAI 파이썬 SDK로 ANIS Trans API 서버 호출하기.

  pip install openai
  anis-trans-server            (다른 창에서 먼저 실행)
  python examples/api_openai.py
"""
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:11435/v1", api_key="anis")  # --api-key 를 안 썼으면 아무 값이나

# 1) 모델 목록
print([m.id for m in client.models.list().data])

# 2) 일→한 (방향은 모델 이름으로)
r = client.chat.completions.create(model="anis-trans:ja-ko",
                                   messages=[{"role": "user", "content": "今日は雨が降ってるね。"}])
print(r.choices[0].message.content, r.usage)

# 3) 한→일 + 앞뒤 문맥 (extra_body의 "anis" 객체)
r = client.chat.completions.create(
    model="anis-trans:ko-ja",
    messages=[{"role": "user", "content": "괜찮아?"}],
    extra_body={"anis": {"prev": ["선배, 안색이 안 좋아요."], "next": ["응, 잠을 좀 못 잤을 뿐이야."]}})
print(r.choices[0].message.content)

# 4) 채팅 기록을 앞 문맥으로 + 스트리밍
stream = client.chat.completions.create(
    model="anis-trans",
    messages=[{"role": "user", "content": "先輩、顔色悪いですよ。"},
              {"role": "assistant", "content": "선배, 안색이 안 좋아요."},
              {"role": "user", "content": "大丈夫？"}],
    stream=True)
print("".join(c.choices[0].delta.content or "" for c in stream if c.choices))
