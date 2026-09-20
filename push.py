import os
import requests
from datetime import datetime
import time

OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
PUSHPLUS_TOKEN = os.environ["PUSHPLUS_TOKEN"]

# 明确指定模型 ID
MODEL = "qwen/qwen3.8-27b:free"

# ---------- 1. 调用 OpenRouter 生成内容 ----------
system_prompt = "你是一个温暖的晨间推送助手，用简洁、积极的语言生成每日早安内容。"

user_prompt = f"""今天是 {datetime.now().strftime('%Y年%m月%d日')}，请生成一条早安推送，包含：
1. 一句温暖的问候语
2. 一句励志或治愈的短句
3. 一个今日小贴士（生活、健康或效率相关）
总字数控制在 150 字以内，语言自然，不要使用 Markdown 标题格式。"""

def call_openrouter_with_retry(payload, headers, max_retries=4):
    """带指数退避的 OpenRouter 调用，专门处理 429 错误。"""
    for attempt in range(max_retries):
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=120,
        )

        if response.status_code == 429:
            # 优先使用服务端建议的等待时间
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                wait = int(retry_after)
            else:
                # 指数退避：2s, 4s, 8s, 16s
                wait = 2 ** attempt

            print(f"触发速率限制，等待 {wait} 秒后重试（第 {attempt + 1}/{max_retries} 次）...")
            time.sleep(wait)
            continue

        # 非 429 错误直接抛出，由外层处理
        response.raise_for_status()
        return response

    raise Exception("重试多次后仍然触发速率限制，请检查 OpenRouter 账户设置")

# 使用方式
response = call_openrouter_with_retry(payload, headers)
ai_content = response.json()["choices"][0]["message"]["content"]

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
