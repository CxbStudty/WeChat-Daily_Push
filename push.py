import os
import time
import requests
from datetime import datetime

# ---------- 读取环境变量 ----------
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
PUSHPLUS_TOKEN = os.environ["PUSHPLUS_TOKEN"]

MODEL = "qwen/qwen3.8-27b:free"

# ---------- 1. 准备 OpenRouter 请求 ----------
system_prompt = "你是一个温暖的晨间推送助手，用简洁、积极的语言生成每日早安内容。"

user_prompt = f"""今天是 {datetime.now().strftime('%Y年%m月%d日')}，请生成一条早安推送，包含：
1. 一句温暖的问候语
2. 一句励志或治愈的短句
3. 一个今日小贴士（生活、健康或效率相关）
总字数控制在 150 字以内，语言自然，不要使用 Markdown 标题格式。"""

headers = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json",
}

payload = {
    "model": MODEL,
    "messages": [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ],
    "max_tokens": 500,
    "temperature": 0.8,
}


# ---------- 2. 带重试的 OpenRouter 调用 ----------
def call_openrouter_with_retry(payload, headers, max_retries=4):
    for attempt in range(max_retries):
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=120,
        )

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            wait = int(retry_after) if retry_after else 2 ** attempt
            print(f"触发速率限制，等待 {wait} 秒后重试（第 {attempt + 1}/{max_retries} 次）...")
            time.sleep(wait)
            continue

        # 打印状态码与响应，便于排查其他错误
        print(f"OpenRouter 状态码: {response.status_code}")
        if response.status_code != 200:
            print(f"OpenRouter 响应内容: {response.text}")
        response.raise_for_status()
        return response

    raise Exception("重试多次后仍然触发速率限制，请检查 OpenRouter 账户设置")


response = call_openrouter_with_retry(payload, headers)
ai_content = response.json()["choices"][0]["message"]["content"]
print("AI 生成内容：", ai_content[:80], "...")

# ---------- 3. PushPlus 推送 ----------
push_resp = requests.post(
    "http://www.pushplus.plus/send",
    json={
        "token": PUSHPLUS_TOKEN,
        "title": f"☀️ 早安 · {datetime.now().strftime('%m月%d日')}",
        "content": ai_content,
        "template": "html",
    },
    timeout=30,
)

print(f"PushPlus 状态码: {push_resp.status_code}")
print(f"PushPlus 响应内容: {push_resp.text}")
