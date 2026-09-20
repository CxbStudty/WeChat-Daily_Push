import os
import requests
from datetime import datetime

OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
PUSHPLUS_TOKEN = os.environ["PUSHPLUS_TOKEN"]

# 明确指定模型 ID
MODEL = "qwen/qwen3.6-plus:free"

# ---------- 1. 调用 OpenRouter 生成内容 ----------
system_prompt = "你是一个温暖的晨间推送助手，用简洁、积极的语言生成每日早安内容。"

user_prompt = f"""今天是 {datetime.now().strftime('%Y年%m月%d日')}，请生成一条早安推送，包含：
1. 一句温暖的问候语
2. 一句励志或治愈的短句
3. 一个今日小贴士（生活、健康或效率相关）
总字数控制在 150 字以内，语言自然，不要使用 Markdown 标题格式。"""

response = requests.post(
    "https://openrouter.ai/api/v1/chat/completions",
    headers={
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    },
    json={
        "model": MODEL,          # ← 这里固定为 qwen/qwen3.6-plus:free
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": 500,
        "temperature": 0.8,
    },
    timeout=120,
)

response.raise_for_status()
ai_content = response.json()["choices"][0]["message"]["content"]

# ---------- 2. PushPlus 推送 ----------
push_resp = requests.post(
    "http://www.pushplus.plus/send",     # PushPlus 官方接口地址
    json={
        "token": PUSHPLUS_TOKEN,
        "title": f"☀️ 早安 · {datetime.now().strftime('%m月%d日')}",
        "content": ai_content,
        "template": "html",
    },
    timeout=30,
)

print("AI 生成：", ai_content[:80], "...")
print("PushPlus 结果：", push_resp.json())
