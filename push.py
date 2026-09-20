try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import os
import time
import requests
from datetime import datetime

# ---------- 读取环境变量 ----------
ZHIPU_API_KEY = os.environ["ZHIPU_API_KEY"]
PUSHPLUS_TOKEN = os.environ["PUSHPLUS_TOKEN"]

MODEL = "glm-4.7-flash"
CITY = "烟台"   # ← 改成你的城市


# ---------- 天气获取（Open-Meteo，无需 API Key）----------
def get_weather(city):
    """获取指定城市的当前天气和今日预报"""
    try:
        # 1. 地理编码：城市名 → 经纬度
        geo_url = (
            f"https://geocoding-api.open-meteo.com/v1/search"
            f"?name={city}&count=1&language=zh&format=json"
        )
        geo_resp = requests.get(geo_url, timeout=10)
        geo_data = geo_resp.json()

        if not geo_data.get("results"):
            print(f"未找到城市：{city}")
            return None

        result = geo_data["results"][0]
        lat = result["latitude"]
        lon = result["longitude"]
        city_name = result.get("name", city)

        # 2. 获取天气数据
        weather_url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
            f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
            f"&timezone=Asia/Shanghai&forecast_days=1"
        )
        weather_resp = requests.get(weather_url, timeout=10)
        weather_data = weather_resp.json()

        current = weather_data["current"]
        daily = weather_data["daily"]

        # 3. WMO 天气代码转中文
        code_map = {
            0: "晴", 1: "大部晴朗", 2: "多云", 3: "阴",
            45: "雾", 48: "雾凇",
            51: "毛毛雨", 53: "小雨", 55: "中雨",
            56: "冻毛毛雨", 57: "冻雨",
            61: "小雨", 63: "中雨", 65: "大雨",
            66: "冻雨", 67: "强冻雨",
            71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒",
            80: "阵雨", 81: "中阵雨", 82: "强阵雨",
            85: "小阵雪", 86: "大阵雪",
            95: "雷阵雨", 96: "雷阵雨伴小冰雹", 99: "雷阵雨伴大冰雹",
        }
        weather_code = current["weather_code"]
        weather_desc = code_map.get(weather_code, f"未知天气({weather_code})")

        return {
            "city": city_name,
            "weather": weather_desc,
            "temp": current["temperature_2m"],
            "temp_max": daily["temperature_2m_max"][0],
            "temp_min": daily["temperature_2m_min"][0],
            "humidity": current["relative_humidity_2m"],
            "wind_speed": current["wind_speed_10m"],
            "precip_prob": daily["precipitation_probability_max"][0],
        }

    except Exception as e:
        print(f"获取天气失败：{e}")
        return None


# ---------- 获取天气并构建上下文 ----------
weather = get_weather(CITY)

if weather:
    weather_context = (
        f"{weather['city']}今日天气：{weather['weather']}，"
        f"气温 {weather['temp_min']}~{weather['temp_max']}°C，"
        f"当前 {weather['temp']}°C，"
        f"湿度 {weather['humidity']}%，"
        f"风速 {weather['wind_speed']} km/h，"
        f"降水概率 {weather['precip_prob']}%。"
    )
    print("天气信息：", weather_context)
else:
    weather_context = ""
    print("未获取到天气数据，将生成通用早安内容。")


# ---------- 1. 准备 GLM 请求 ----------
system_prompt = "你是一个温暖的晨间推送助手，用简洁、积极的语言生成每日早安内容。"

user_prompt = f"""今天是 {datetime.now().strftime('%Y年%m月%d日')}。

{weather_context}

请根据以上信息生成一条早安推送，包含：
1. 一句温暖的问候语
2. 一句励志或治愈的短句
3. 一个今日小贴士（结合天气给出穿衣、出行或健康建议）
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
    "max_tokens": 2048,
    "thinking": {"type": "disabled"},
}


# ---------- 2. 带重试的智谱GLM调用 ----------
def call_zhipu_with_retry(payload, headers, max_retries=3):
    error_msg = ""
    for attempt in range(max_retries):
        response = requests.post(
            "https://open.bigmodel.cn/api/paas/v4/chat/completions",
            headers=headers,
            json=payload,
            timeout=120,
        )

        if response.status_code == 429:
            try:
                error_body = response.json()
                error_code = error_body.get("error", {}).get("code", "")
                error_msg = error_body.get("error", {}).get("message", "")
            except Exception:
                error_code = ""
                error_msg = response.text

            print(f"429 错误，业务码: {error_code}，信息: {error_msg}")

            if error_code == "1302":
                wait = 10 * (attempt + 1)
                print(f"触发速率限制，等待 {wait} 秒后重试...")
                time.sleep(wait)
                continue

            if error_code == "1305":
                wait = 15 * (attempt + 1)
                print(f"平台过载，等待 {wait} 秒后重试...")
                time.sleep(wait)
                continue

            wait = 10 * (attempt + 1)
            time.sleep(wait)
            continue

        print(f"智谱GLM 状态码: {response.status_code}")
        if response.status_code != 200:
            print(f"智谱GLM 响应内容: {response.text}")
        response.raise_for_status()
        return response

    raise Exception(f"重试 {max_retries} 次后仍然失败，最后错误: {error_msg}")


response = call_zhipu_with_retry(payload, headers)

# ---------- 3. 提取内容 ----------
message = response.json()["choices"][0]["message"]
ai_content = message.get("content") or message.get("reasoning_content", "")
ai_content = ai_content.strip()

print("AI 生成内容：", repr(ai_content))

if not ai_content:
    raise Exception("AI 返回内容为空")

# ---------- 4. PushPlus 推送 ----------
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
