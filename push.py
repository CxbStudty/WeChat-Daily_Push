```python
import os
import time
import requests
from datetime import datetime

# ============================================================
# 环境变量
# ============================================================

ZHIPU_API_KEY = os.environ.get("ZHIPU_API_KEY", "").strip()
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "").strip()

MODEL = "glm-4.7-flash"

# ============================================================
# 收件人配置
#
# 每个人必须单独配置：
# name  = 昵称
# token = 这个人的 PushPlus 好友令牌
# city  = 这个人的城市
#
# 注意：
# token 前后不要有空格、Tab、换行。
# 程序本身也会自动 strip()。
# ============================================================

RECIPIENTS = [
    {
        "name": "我",
        "token": "67e80b97101d4b09b9e5651e32a1f765",
        "city": "烟台",
    },
    {
        "name": "LNY",
        "token": "210c090066b44036aa3b0e04ed58722a",
        "city": "威海",
    },
]


# ============================================================
# 工具函数
# ============================================================

def mask_token(token):
    """
    日志中只显示 Token 的首尾部分，避免完整 Token 出现在 GitHub Actions 日志。
    """
    token = token.strip()

    if not token:
        return "(空)"

    if len(token) <= 8:
        return "****"

    return f"{token[:4]}****{token[-4:]}"


# ============================================================
# 获取天气
# ============================================================

def get_weather(city):
    """
    根据城市名称获取 Open-Meteo 天气。

    返回：
    {
        "city": ...,
        "weather": ...,
        "temp": ...,
        "temp_max": ...,
        "temp_min": ...,
        "humidity": ...,
        "wind_speed": ...,
        "precip_prob": ...,
    }

    获取失败返回 None。
    """

    city = str(city).strip()

    if not city:
        print("❌ 天气查询失败：城市为空")
        return None

    try:
        # ----------------------------------------------------
        # 1. 地理编码
        # ----------------------------------------------------

        geo_url = "https://geocoding-api.open-meteo.com/v1/search"

        geo_params = {
            "name": city,
            "count": 5,
            "language": "zh",
            "format": "json",
        }

        print(f"🌍 正在查询城市：{city}")

        geo_resp = requests.get(
            geo_url,
            params=geo_params,
            timeout=15,
        )

        geo_resp.raise_for_status()

        geo_data = geo_resp.json()

        results = geo_data.get("results", [])

        if not results:
            print(f"❌ 未找到城市：{city}")
            return None

        # ----------------------------------------------------
        # 2. 找中国的匹配城市
        #
        # Open-Meteo 有时会返回多个同名地点。
        # 优先选择中国的结果。
        # ----------------------------------------------------

        result = None

        for item in results:
            if item.get("country_code") == "CN":
                result = item
                break

        if result is None:
            result = results[0]

        lat = result.get("latitude")
        lon = result.get("longitude")

        city_name = result.get("name", city)
        country = result.get("country", "")
        admin1 = result.get("admin1", "")

        if lat is None or lon is None:
            print(f"❌ 城市 {city} 没有有效经纬度")
            return None

        print(
            f"📍 地理编码：{city} → "
            f"{city_name} / {admin1} / {country} "
            f"({lat}, {lon})"
        )

        # ----------------------------------------------------
        # 3. 获取天气
        # ----------------------------------------------------

        weather_url = "https://api.open-meteo.com/v1/forecast"

        weather_params = {
            "latitude": lat,
            "longitude": lon,
            "current": (
                "temperature_2m,"
                "relative_humidity_2m,"
                "weather_code,"
                "wind_speed_10m"
            ),
            "daily": (
                "temperature_2m_max,"
                "temperature_2m_min,"
                "precipitation_probability_max"
            ),
            "timezone": "Asia/Shanghai",
            "forecast_days": 1,
        }

        print(f"🌤️ 正在获取 {city_name} 天气...")

        weather_resp = requests.get(
            weather_url,
            params=weather_params,
            timeout=15,
        )

        weather_resp.raise_for_status()

        weather_data = weather_resp.json()

        if "current" not in weather_data:
            print(f"❌ {city} 天气数据中没有 current")
            return None

        if "daily" not in weather_data:
            print(f"❌ {city} 天气数据中没有 daily")
            return None

        current = weather_data["current"]
        daily = weather_data["daily"]

        # ----------------------------------------------------
        # 4. 天气代码转换
        # ----------------------------------------------------

        code_map = {
            0: "晴",
            1: "大部晴朗",
            2: "多云",
            3: "阴",

            45: "雾",
            48: "雾凇",

            51: "毛毛雨",
            53: "小雨",
            55: "中雨",

            56: "冻毛毛雨",
            57: "冻雨",

            61: "小雨",
            63: "中雨",
            65: "大雨",

            66: "冻雨",
            67: "强冻雨",

            71: "小雪",
            73: "中雪",
            75: "大雪",
            77: "雪粒",

            80: "阵雨",
            81: "中阵雨",
            82: "强阵雨",

            85: "小阵雪",
            86: "大阵雪",

            95: "雷阵雨",
            96: "雷阵雨伴小冰雹",
            99: "雷阵雨伴大冰雹",
        }

        weather_code = current.get("weather_code")

        weather_desc = code_map.get(
            weather_code,
            f"未知天气({weather_code})",
        )

        # ----------------------------------------------------
        # 5. 提取数据
        # ----------------------------------------------------

        temp = current.get("temperature_2m")
        humidity = current.get("relative_humidity_2m")
        wind_speed = current.get("wind_speed_10m")

        temp_max_list = daily.get("temperature_2m_max", [])
        temp_min_list = daily.get("temperature_2m_min", [])
        precip_list = daily.get(
            "precipitation_probability_max",
            [],
        )

        if not temp_max_list or not temp_min_list:
            print(f"❌ {city} 缺少每日最高/最低温度")
            return None

        temp_max = temp_max_list[0]
        temp_min = temp_min_list[0]

        precip_prob = (
            precip_list[0]
            if precip_list
            else None
        )

        weather = {
            "city": city_name,
            "weather": weather_desc,
            "temp": temp,
            "temp_max": temp_max,
            "temp_min": temp_min,
            "humidity": humidity,
            "wind_speed": wind_speed,
            "precip_prob": precip_prob,
        }

        print(
            f"✅ {city} 天气获取成功："
            f"{city_name} | "
            f"{weather_desc} | "
            f"{temp_min}~{temp_max}°C | "
            f"当前 {temp}°C"
        )

        return weather

    except requests.RequestException as e:
        print(f"❌ {city} 网络请求失败：{e}")
        return None

    except Exception as e:
        print(f"❌ 获取 {city} 天气失败：{e}")
        return None


# ============================================================
# 调用智谱 GLM
# ============================================================

def call_zhipu_with_retry(
    payload,
    headers,
    max_retries=3,
):
    """
    调用智谱 API，遇到限流/平台过载时自动重试。
    """

    error_msg = ""

    for attempt in range(max_retries):

        try:
            response = requests.post(
                "https://open.bigmodel.cn/api/paas/v4/chat/completions",
                headers=headers,
                json=payload,
                timeout=120,
            )

        except requests.RequestException as e:

            error_msg = str(e)

            print(
                f"❌ 智谱请求网络错误：{e}"
            )

            if attempt < max_retries - 1:
                wait = 10 * (attempt + 1)

                print(
                    f"等待 {wait} 秒后重试..."
                )

                time.sleep(wait)
                continue

            raise

        # ----------------------------------------------------
        # 429
        # ----------------------------------------------------

        if response.status_code == 429:

            try:
                error_body = response.json()

                error_code = (
                    error_body
                    .get("error", {})
                    .get("code", "")
                )

                error_msg = (
                    error_body
                    .get("error", {})
                    .get("message", "")
                )

            except Exception:

                error_code = ""
                error_msg = response.text

            print(
                f"⚠️ 智谱 429："
                f"业务码={error_code}，"
                f"信息={error_msg}"
            )

            if attempt < max_retries - 1:

                if error_code == "1302":
                    wait = 10 * (attempt + 1)

                elif error_code == "1305":
                    wait = 15 * (attempt + 1)

                else:
                    wait = 10 * (attempt + 1)

                print(
                    f"等待 {wait} 秒后重试..."
                )

                time.sleep(wait)
                continue

        # ----------------------------------------------------
        # 非 200
        # ----------------------------------------------------

        if response.status_code != 200:

            print(
                "❌ 智谱 API 返回错误："
                f"{response.status_code}"
            )

            print(
                f"响应内容：{response.text}"
            )

        response.raise_for_status()

        return response

    raise Exception(
        f"智谱重试 {max_retries} 次后仍然失败："
        f"{error_msg}"
    )


# ============================================================
# 为某个城市生成早安内容
# ============================================================

def generate_message(city):
    """
    为指定城市生成早安消息。

    注意：
    这里每调用一次都会重新获取指定城市天气，
    不会复用其他收件人的天气。
    """

    city = str(city).strip()

    print("")
    print("----------------------------------------")
    print(f"📝 开始生成 {city} 的早安消息")
    print("----------------------------------------")

    # --------------------------------------------------------
    # 获取这个收件人对应城市的天气
    # --------------------------------------------------------

    weather = get_weather(city)

    if weather:

        precip_text = (
            f"{weather['precip_prob']}%"
            if weather["precip_prob"] is not None
            else "暂无数据"
        )

        weather_context = (
            f"{weather['city']}今日天气："
            f"{weather['weather']}，"
            f"气温 {weather['temp_min']}~"
            f"{weather['temp_max']}°C，"
            f"当前 {weather['temp']}°C，"
            f"湿度 {weather['humidity']}%，"
            f"风速 {weather['wind_speed']} km/h，"
            f"降水概率 {precip_text}。"
        )

        print(
            f"🌤️ AI 使用的天气："
            f"{weather_context}"
        )

    else:

        # ----------------------------------------------------
        # 天气获取失败
        #
        # 不要把其他人的天气拿过来。
        # 这里明确告诉 AI 天气不可用。
        # --------------------------------------------------------

        weather_context = (
            f"{city}今日天气数据暂时获取失败。"
            "不要猜测具体天气、温度、降雨或风速。"
        )

        print(
            f"⚠️ {city} 天气获取失败，"
            "不会使用其他城市天气代替。"
        )

    # --------------------------------------------------------
    # 当前日期
    # --------------------------------------------------------

    today = datetime.now().strftime(
        "%Y年%m月%d日"
    )

    # --------------------------------------------------------
    # System Prompt
    # --------------------------------------------------------

    system_prompt = (
        "你是一个温暖的晨间推送助手，"
        "用简洁、积极、自然的语言生成每日早安内容。"
    )

    # --------------------------------------------------------
    # User Prompt
    # --------------------------------------------------------

    user_prompt = f"""
今天是 {today}。

{weather_context}

请根据以上信息生成一条早安推送，包含：

1. 一句温暖的问候语
2. 一句励志或治愈的短句
3. 一个今日小贴士
4. 结合天气给出穿衣、出行和健康建议

要求：

- 总字数控制在 150 字以内
- 语言自然
- 不要使用 Markdown 标题
- 如果天气数据获取失败，不要自行猜测天气
- 不要编造温度、降水概率、风速等天气数据
"""

    headers = {
        "Authorization": f"Bearer {ZHIPU_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
        "temperature": 0.8,
        "max_tokens": 2048,
        "thinking": {
            "type": "disabled",
        },
    }

    # --------------------------------------------------------
    # 调用 GLM
    # --------------------------------------------------------

    response = call_zhipu_with_retry(
        payload,
        headers,
    )

    response_data = response.json()

    choices = response_data.get(
        "choices",
        [],
    )

    if not choices:
        raise Exception(
            "智谱 API 返回中没有 choices"
        )

    message = choices[0].get(
        "message",
        {},
    )

    ai_content = (
        message.get("content")
        or message.get("reasoning_content")
        or ""
    )

    ai_content = ai_content.strip()

    if not ai_content:
        raise Exception(
            "智谱 API 返回的消息内容为空"
        )

    print(
        f"🤖 AI 生成成功："
        f"{repr(ai_content[:80])}"
    )

    return ai_content


# ============================================================
# PushPlus 推送
# ============================================================

def send_to_friend(
    friend_token,
    content,
    recipient_name,
    city,
):
    """
    将指定内容发送给指定好友。
    """

    friend_token = str(
        friend_token
    ).strip()

    print("")
    print("----------------------------------------")
    print("📨 准备 PushPlus 推送")
    print(f"收件人：{recipient_name}")
    print(f"城市：{city}")
    print(
        f"好友 Token："
        f"{mask_token(friend_token)}"
    )
    print("----------------------------------------")

    payload = {
        "token": PUSHPLUS_TOKEN,
        "title": (
            f"☀️ 早安 · "
            f"{datetime.now().strftime('%m月%d日')}"
        ),
        "content": content,
        "template": "html",
        "to": friend_token,
    }

    try:

        response = requests.post(
            "http://www.pushplus.plus/send",
            json=payload,
            timeout=30,
        )

        print(
            f"📡 PushPlus HTTP 状态："
            f"{response.status_code}"
        )

        # 尝试解析 JSON
        try:
            result = response.json()
        except Exception:
            result = None

        if result is not None:

            print(
                f"📡 PushPlus 返回："
                f"{result}"
            )

            code = result.get("code")

            if code == 200:

                print(
                    f"✅ PushPlus 已接受 "
                    f"{recipient_name} 的发送请求"
                )

                print(
                    "ℹ️ 注意：PushPlus 接口返回 "
                    "200 主要表示请求已被接受，"
                    "不等于最终一定送达。"
                )

            else:

                print(
                    f"❌ PushPlus 返回业务错误："
                    f"{result}"
                )

        else:

            print(
                f"⚠️ PushPlus 返回非 JSON："
                f"{response.text}"
            )

        return response, result

    except requests.RequestException as e:

        print(
            f"❌ PushPlus 网络请求失败：{e}"
        )

        raise


# ============================================================
# 主流程
# ============================================================

def main():

    print("")
    print("========================================")
    print("☀️ Daily WeChat Push")
    print("========================================")

    # --------------------------------------------------------
    # 检查环境变量
    # --------------------------------------------------------

    if not ZHIPU_API_KEY:

        print(
            "❌ 缺少环境变量：ZHIPU_API_KEY"
        )

        return

    if not PUSHPLUS_TOKEN:

        print(
            "❌ 缺少环境变量：PUSHPLUS_TOKEN"
        )

        return

    # --------------------------------------------------------
    # 检查收件人
    # --------------------------------------------------------

    if not RECIPIENTS:

        print(
            "❌ RECIPIENTS 为空，"
            "请先配置收件人。"
        )

        return

    print(
        f"👥 本次计划处理："
        f"{len(RECIPIENTS)} 人"
    )

    print(
        f"⏰ 当前时间："
        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    print("")

    success = 0
    fail = 0

    # ========================================================
    # 一个一个处理收件人
    # ========================================================

    for index, recipient in enumerate(
        RECIPIENTS,
        start=1,
    ):

        name = str(
            recipient.get(
                "name",
                "未知",
            )
        ).strip()

        city = str(
            recipient.get(
                "city",
                "",
            )
        ).strip()

        token = str(
            recipient.get(
                "token",
                "",
            )
        ).strip()

        print("")
        print("")
        print("========================================")
        print(
            f"👤 收件人 {index}/{len(RECIPIENTS)}"
        )
        print("========================================")

        print(f"姓名：{name}")
        print(f"城市：{city}")
        print(
            f"Token：{mask_token(token)}"
        )

        # ----------------------------------------------------
        # 基础检查
        # ----------------------------------------------------

        if not token:

            print(
                f"❌ {name} 没有配置好友 Token"
            )

            fail += 1
            continue

        if not city:

            print(
                f"❌ {name} 没有配置城市"
            )

            fail += 1
            continue

        # ----------------------------------------------------
        # 生成这个人的天气 + AI 消息
        # ----------------------------------------------------

        try:

            content = generate_message(
                city
            )

        except Exception as e:

            print("")
            print(
                f"❌ {name} 的消息生成失败："
                f"{e}"
            )

            fail += 1

            # 一个好友失败不能影响其他好友
            continue

        if not content:

            print(
                f"❌ {name}："
                "生成内容为空"
            )

            fail += 1
            continue

        # ----------------------------------------------------
        # 推送给这个人的 Token
        # ----------------------------------------------------

        try:

            response, result = send_to_friend(
                friend_token=token,
                content=content,
                recipient_name=name,
                city=city,
            )

            # ------------------------------------------------
            # 判断 PushPlus 请求是否成功
            # ------------------------------------------------

            if (
                response.status_code == 200
                and isinstance(result, dict)
                and result.get("code") == 200
            ):

                success += 1

                print(
                    f"✅ {name}："
                    "PushPlus 请求提交成功"
                )

            else:

                fail += 1

                print(
                    f"❌ {name}："
                    "PushPlus 请求提交失败"
                )

        except Exception as e:

            print("")
            print(
                f"❌ {name} 推送失败：{e}"
            )

            fail += 1

        # ----------------------------------------------------
        # 收件人之间间隔
        # ----------------------------------------------------

        if index < len(RECIPIENTS):

            print(
                "⏳ 等待 2 秒后处理下一个收件人..."
            )

            time.sleep(2)

    # ========================================================
    # 最终统计
    # ========================================================

    print("")
    print("")
    print("========================================")
    print("🎉 全部处理完成")
    print("========================================")
    print(f"成功：{success} 人")
    print(f"失败：{fail} 人")
    print("========================================")


# ============================================================
# 程序入口
# ============================================================

if __name__ == "__main__":
    main()
```
