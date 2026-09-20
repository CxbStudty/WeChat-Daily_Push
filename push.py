import os
import time
import requests
from datetime import datetime

# ---------- 读取环境变量 ----------
ZHIPU_API_KEY = os.environ["ZHIPU_API_KEY"]
PUSHPLUS_TOKEN = os.environ["PUSHPLUS_TOKEN"]

# 使用智谱免费模型
MODEL = "glm-4.7-flash"

# ---------- 1. 准备智谱GLM请求 ----------
system_prompt = "你是一个温暖的晨间推送助手，用简洁、积极的语言生成每日早安内容。"

user_prompt = f"""今天是 {datetime.now().strftime('%Y年%m月%d日')}，请生成一条早安推送，包含：
1. 一句温暖的问候语
2. 一句励志或治愈的短句
3. 一个今日小贴士（生活、健康或效率相关）
总字数控制在 150 字以内，语言自然，不要使用 Markdown 标题格式。"""

headers = {
    "Authorization": f"Bearer {ZHIPU_API_KEY}",
    "Content-Type": "application/json",
}

payload = {
    "model": MODEL,
    "messages": [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ],
    "temperature": 0.8,
    "max_tokens": 500,
}


# ---------- 2. 带重试的智谱GLM调用 ----------
def call_zhipu_with_retry(payload, headers, max_retries=4):
    for attempt in range(max_retries):
        response = requests.post(
            "https://open.bigmodel.cn/api/paas/v4/chat/completions",
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

        print(f"智谱GLM 状态码: {response.status_code}")
        if response.status_code != 200:
            print(f"智谱GLM 响应内容: {response.text}")
        response.raise_for_status()
        return response

    raise Exception("重试多次后仍然触发速率限制，请检查智谱账户设置")


response = call_zhipu_with_retry(payload, headers)
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
