import os
import json
import re
from datetime import datetime, timedelta, timezone
from html import escape

import requests


# ============================================================
# 配置
# ============================================================

ZHIPU_API_KEY = os.environ["ZHIPU_API_KEY"]
PUSHPLUS_TOKEN = os.environ["PUSHPLUS_TOKEN"]
NEWS_API_KEY = os.environ["NEWS_API_KEY"]

MODEL = "glm-4.7-flash"

ZHIPU_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
PUSHPLUS_URL = "https://www.pushplus.plus/send"

OPEN_METEO_GEOCODING = "https://geocoding-api.open-meteo.com/v1/search"
OPEN_METEO_WEATHER = "https://api.open-meteo.com/v1/forecast"

NEWS_API_URL = "https://newsapi.org/v2/everything"

GOLD_API_URL = "https://xaus.com/api/v1/spot"


# ============================================================
# 每个人的信息
# ============================================================
#
# token = PushPlus 好友 Token
# city  = 这个人的城市
#
# 注意：
# 不要把自己的 PUSHPLUS_TOKEN 填到这里。
#
# 如果好友 Token 重新生成过，要更新这里。
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
# HTTP Session
# ============================================================

session = requests.Session()

session.headers.update({
    "User-Agent": "DailyMorningPush/1.0"
})


# ============================================================
# 通用 GET
# ============================================================

def http_get(url, params=None, headers=None, timeout=20):
    response = session.get(
        url,
        params=params,
        headers=headers,
        timeout=timeout
    )

    response.raise_for_status()

    return response.json()


# ============================================================
# 获取天气
# ============================================================

def get_weather(city):
    """
    使用 Open-Meteo：

    1. 城市名 -> 经纬度
    2. 经纬度 -> 当前天气 + 今日天气
    """

    print(f"🌤 正在获取 {city} 天气...")

    geo = http_get(
        OPEN_METEO_GEOCODING,
        params={
            "name": city,
            "count": 1,
            "language": "zh",
            "format": "json",
            "countryCode": "CN",
        }
    )

    results = geo.get("results", [])

    if not results:
        raise RuntimeError(f"找不到城市：{city}")

    location = results[0]

    latitude = location["latitude"]
    longitude = location["longitude"]

    real_city = location.get("name", city)

    weather = http_get(
        OPEN_METEO_WEATHER,
        params={
            "latitude": latitude,
            "longitude": longitude,

            "current": ",".join([
                "temperature_2m",
                "apparent_temperature",
                "relative_humidity_2m",
                "precipitation",
                "weather_code",
                "wind_speed_10m",
            ]),

            "daily": ",".join([
                "weather_code",
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_probability_max",
                "sunrise",
                "sunset",
            ]),

            "timezone": "Asia/Shanghai",
            "forecast_days": 1,
        }
    )

    current = weather.get("current", {})
    daily = weather.get("daily", {})

    return {
        "city": real_city,

        "latitude": latitude,
        "longitude": longitude,

        "temperature": current.get("temperature_2m"),
        "apparent_temperature": current.get("apparent_temperature"),
        "humidity": current.get("relative_humidity_2m"),
        "precipitation": current.get("precipitation"),
        "weather_code": current.get("weather_code"),
        "wind_speed": current.get("wind_speed_10m"),

        "today_max": (
            daily.get("temperature_2m_max", [None])[0]
            if daily.get("temperature_2m_max")
            else None
        ),

        "today_min": (
            daily.get("temperature_2m_min", [None])[0]
            if daily.get("temperature_2m_min")
            else None
        ),

        "rain_probability": (
            daily.get("precipitation_probability_max", [None])[0]
            if daily.get("precipitation_probability_max")
            else None
        ),

        "sunrise": (
            daily.get("sunrise", [None])[0]
            if daily.get("sunrise")
            else None
        ),

        "sunset": (
            daily.get("sunset", [None])[0]
            if daily.get("sunset")
            else None
        ),
    }


# ============================================================
# 天气代码转中文
# ============================================================

def weather_code_to_text(code):

    mapping = {
        0: "晴",
        1: "基本晴",
        2: "部分多云",
        3: "阴",
        45: "雾",
        48: "雾凇",
        51: "小毛毛雨",
        53: "毛毛雨",
        55: "较强毛毛雨",
        56: "冻毛毛雨",
        57: "较强冻毛毛雨",
        61: "小雨",
        63: "中雨",
        65: "大雨",
        66: "冻雨",
        67: "较强冻雨",
        71: "小雪",
        73: "中雪",
        75: "大雪",
        77: "雪粒",
        80: "阵雨",
        81: "较强阵雨",
        82: "强阵雨",
        85: "阵雪",
        86: "较强阵雪",
        95: "雷暴",
        96: "雷暴伴冰雹",
        99: "强雷暴伴冰雹",
    }

    return mapping.get(code, "天气情况未知")


# ============================================================
# 获取昨日日期
# ============================================================

def get_yesterday():

    china_tz = timezone(timedelta(hours=8))

    now = datetime.now(china_tz)

    yesterday = now.date() - timedelta(days=1)

    return yesterday.strftime("%Y-%m-%d")


# ============================================================
# News API
# ============================================================

def get_news(query, language="zh", page_size=8):

    yesterday = get_yesterday()

    print(f"📰 获取新闻：{query} / {yesterday}")

    params = {
        "q": query,
        "from": yesterday,
        "to": yesterday,
        "language": language,
        "sortBy": "popularity",
        "pageSize": page_size,
        "page": 1,
    }

    headers = {
        "X-Api-Key": NEWS_API_KEY
    }

    data = http_get(
        NEWS_API_URL,
        params=params,
        headers=headers
    )

    if data.get("status") != "ok":
        raise RuntimeError(
            f"News API 错误：{data}"
        )

    articles = []

    for article in data.get("articles", []):

        title = article.get("title")

        if not title:
            continue

        description = article.get("description") or ""

        source = (
            article.get("source", {}).get("name")
            or "未知来源"
        )

        url = article.get("url") or ""

        published_at = article.get("publishedAt") or ""

        articles.append({
            "title": title,
            "description": description,
            "source": source,
            "url": url,
            "published_at": published_at,
        })

    return articles


# ============================================================
# 获取国内 / 国际新闻
# ============================================================

def get_all_news():

    domestic = get_news(
        '"中国" OR "中国经济" OR "中国社会" OR "中国科技"',
        language="zh",
        page_size=8
    )

    international = get_news(
        '"国际" OR "美国" OR "欧洲" OR "日本" OR "中东"',
        language="zh",
        page_size=8
    )

    return {
        "domestic": domestic,
        "international": international,
    }


# ============================================================
# 获取国际金价
# ============================================================

def get_gold_price():

    print("🥇 获取国际金价...")

    data = http_get(
        GOLD_API_URL,
        timeout=20
    )

    price = data.get("spot_usd_oz")

    if price is None:
        xau = data.get("xau", {})
        price = xau.get("price")

    if price is None:
        raise RuntimeError(
            f"金价 API 返回中没有找到价格：{data}"
        )

    data_state = data.get("data_state", {})

    return {
        "price_usd_oz": price,
        "updated_at": data.get("updated_at"),
        "as_of": data_state.get("as_of"),
        "status": data_state.get("status"),
        "source": data_state.get("source"),
    }


# ============================================================
# 清理 GLM 返回
# ============================================================

def clean_json_text(text):

    if not text:
        return ""

    text = text.strip()

    # 去掉 ```json ... ```
    text = re.sub(
        r"^```json\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"^```\s*",
        "",
        text
    )

    text = re.sub(
        r"\s*```$",
        "",
        text
    )

    return text.strip()


# ============================================================
# GLM 总编辑
# ============================================================

def ai_editor(weather, news, gold):

    print("🤖 GLM 正在进行每日早报总编辑...")

    weather_text = {
        "城市": weather["city"],
        "当前温度": weather["temperature"],
        "体感温度": weather["apparent_temperature"],
        "天气": weather_code_to_text(weather["weather_code"]),
        "湿度": weather["humidity"],
        "降水量": weather["precipitation"],
        "风速": weather["wind_speed"],
        "今日最高温": weather["today_max"],
        "今日最低温": weather["today_min"],
        "降水概率": weather["rain_probability"],
        "日出": weather["sunrise"],
        "日落": weather["sunset"],
    }

    editor_input = {
        "weather": weather_text,
        "yesterday": get_yesterday(),
        "domestic_news": news["domestic"],
        "international_news": news["international"],
        "gold": gold,
    }

    system_prompt = """
你是一名高质量的「每日早报总编辑」。

你的任务不是自己搜索事实，也不是凭空创作新闻。

你只能根据用户提供的数据进行编辑。

必须遵守：

1. 天气数据只能使用输入中的天气数据。
2. 新闻只能根据输入的新闻标题、摘要、来源进行总结。
3. 不得添加输入中没有的新闻事实。
4. 不得虚构新闻。
5. 国际金价只能使用输入中的金价。
6. 不得自己猜测金价。
7. 不得生成人民日报金句。
8. 不得生成诗句。
9. 不要加入政治立场、政治评价或煽动性语言。
10. 新闻尽量客观、简洁。
11. 如果新闻信息不足，就明确说「暂无足够信息」，不要编造。
12. 可以重新组织新闻标题，使早报更自然。
13. 可以给天气生成生活建议，但建议必须符合天气数据。
14. 可以给金价做非常简短的市场信息解读，但不要预测涨跌。
15. 输出必须是合法 JSON。
16. 不要使用 Markdown 代码块。

你需要输出：

{
  "greeting": "简短自然的早安开场",
  "weather_summary": "天气总结",
  "weather_advice": "穿衣和出行建议",
  "domestic_news": [
    {
      "title": "新闻标题",
      "summary": "一句话总结",
      "source": "来源"
    }
  ],
  "international_news": [
    {
      "title": "新闻标题",
      "summary": "一句话总结",
      "source": "来源"
    }
  ],
  "gold_summary": "国际金价信息",
  "daily_tip": "一句实用的小建议"
}

要求：

国内新闻最多3条。
国际新闻最多3条。

不要为了凑数量而编造新闻。

整体风格：
简洁、自然、有一点温度。
适合早晨通过微信阅读。
不要写得像新闻联播。
不要过度使用 emoji。
"""

    user_prompt = json.dumps(
        editor_input,
        ensure_ascii=False,
        indent=2
    )

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_prompt
            }
        ],
        "temperature": 0.5,
        "max_tokens": 2500,
        "stream": False,
    }

    headers = {
        "Authorization": f"Bearer {ZHIPU_API_KEY}",
        "Content-Type": "application/json",
    }

    response = session.post(
        ZHIPU_URL,
        headers=headers,
        json=payload,
        timeout=60
    )

    response.raise_for_status()

    data = response.json()

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(
            f"GLM 返回格式异常：{data}"
        )

    content = clean_json_text(content)

    try:
        result = json.loads(content)
    except json.JSONDecodeError:

        # 尝试从文本中截取 JSON
        start = content.find("{")
        end = content.rfind("}")

        if start >= 0 and end > start:

            try:
                result = json.loads(
                    content[start:end + 1]
                )
            except json.JSONDecodeError:
                raise RuntimeError(
                    f"GLM 没有返回合法 JSON：\n{content}"
                )

        else:
            raise RuntimeError(
                f"GLM 没有返回合法 JSON：\n{content}"
            )

    return result


# ============================================================
# HTML 渲染
# ============================================================

def render_news(news_list):

    if not news_list:
        return "<p>暂无足够新闻信息。</p>"

    html = ""

    for item in news_list:

        title = escape(
            str(item.get("title", ""))
        )

        summary = escape(
            str(item.get("summary", ""))
        )

        source = escape(
            str(item.get("source", ""))
        )

        html += f"""
        <div style="margin-bottom:12px;">
            <div style="font-weight:bold;">
                {title}
            </div>

            <div style="margin-top:3px;">
                {summary}
            </div>

            <div style="color:#888;font-size:12px;margin-top:2px;">
                来源：{source}
            </div>
        </div>
        """

    return html


def render_message(name, weather, gold, edited):

    city = escape(weather["city"])

    greeting = escape(
        str(edited.get("greeting", "早上好！"))
    )

    weather_summary = escape(
        str(
            edited.get(
                "weather_summary",
                ""
            )
        )
    )

    weather_advice = escape(
        str(
            edited.get(
                "weather_advice",
                ""
            )
        )
    )

    gold_summary = escape(
        str(
            edited.get(
                "gold_summary",
                ""
            )
        )
    )

    daily_tip = escape(
        str(
            edited.get(
                "daily_tip",
                ""
            )
        )
    )

    domestic_news = render_news(
        edited.get("domestic_news", [])
    )

    international_news = render_news(
        edited.get("international_news", [])
    )

    temperature = weather.get("temperature")
    today_min = weather.get("today_min")
    today_max = weather.get("today_max")

    gold_price = gold.get("price_usd_oz")

    if isinstance(gold_price, (int, float)):
        gold_price_text = f"${gold_price:,.2f}/盎司"
    else:
        gold_price_text = str(gold_price)

    return f"""
<div style="
    font-family:-apple-system,BlinkMacSystemFont,
    'Segoe UI','Microsoft YaHei',sans-serif;
    line-height:1.7;
    color:#222;
">

    <div style="
        font-size:20px;
        font-weight:bold;
        margin-bottom:8px;
    ">
        ☀️ {greeting}
    </div>


    <div style="
        background:#f5f7fa;
        padding:12px;
        border-radius:10px;
        margin-bottom:15px;
    ">

        <div style="font-size:17px;font-weight:bold;">
            🌤 {city} 今日天气
        </div>

        <div style="margin-top:6px;">
            当前：{temperature}℃
        </div>

        <div>
            今日：{today_min}℃ ～ {today_max}℃
        </div>

        <div style="margin-top:5px;">
            {weather_summary}
        </div>

        <div style="
            margin-top:6px;
            color:#555;
        ">
            💡 {weather_advice}
        </div>

    </div>


    <div style="
        font-size:17px;
        font-weight:bold;
        margin-bottom:8px;
    ">
        🇨🇳 昨日国内新闻
    </div>

    {domestic_news}


    <div style="
        font-size:17px;
        font-weight:bold;
        margin-top:15px;
        margin-bottom:8px;
    ">
        🌍 昨日国际新闻
    </div>

    {international_news}


    <div style="
        background:#fff8e6;
        padding:12px;
        border-radius:10px;
        margin-top:15px;
    ">

        <div style="font-size:17px;font-weight:bold;">
            🥇 国际金价
        </div>

        <div style="margin-top:5px;">
            XAU/USD：{gold_price_text}
        </div>

        <div style="margin-top:5px;">
            {gold_summary}
        </div>

    </div>


    <div style="
        margin-top:15px;
        padding-top:10px;
        border-top:1px solid #eee;
    ">
        💡 <b>今日小贴士：</b>{daily_tip}
    </div>


    <div style="
        margin-top:18px;
        color:#999;
        font-size:11px;
    ">
        数据来源：Open-Meteo / News API / XAU Gold Data API
    </div>

</div>
"""


# ============================================================
# PushPlus
# ============================================================

def send_to_friend(friend_token, content, name):

    # 防止复制 Token 时混入空格 / Tab / 换行
    friend_token = friend_token.strip()

    print(f"📨 正在发送给：{name}")
    print(f"🔑 Token 长度：{len(friend_token)}")

    payload = {
        "token": PUSHPLUS_TOKEN.strip(),
        "title": "☀️ 每日早报",
        "content": content,
        "template": "html",
        "channel": "wechat",
        "to": friend_token,
    }

    response = session.post(
        PUSHPLUS_URL,
        json=payload,
        timeout=30
    )

    print(
        f"PushPlus HTTP 状态：{response.status_code}"
    )

    try:
        result = response.json()
    except Exception:
        print("❌ PushPlus 返回不是 JSON：")
        print(response.text)
        return False

    print(f"📡 PushPlus 返回：{result}")

    code = result.get("code")

    if code == 200:
        print(f"✅ {name} PushPlus 请求成功")
        return True

    print(
        f"❌ {name} PushPlus 业务错误："
        f"{result.get('msg')} / {result.get('data')}"
    )

    if code == 999:

        print(
            "⚠️ PushPlus 返回 999。"
            "请检查好友 Token 是否仍是“我的好友”列表中的有效 Token，"
            "以及好友是否仍保持公众号关注关系。"
        )

    elif code == 903:

        print(
            "⚠️ PushPlus Token 无效，请检查 PUSHPLUS_TOKEN。"
        )

    elif code == 905:

        print(
            "⚠️ PushPlus 当前账号尚未完成实名认证。"
        )

    return False


# ============================================================
# 主程序
# ============================================================

def main():

    print("=" * 60)
    print("☀️ 每日早报开始")
    print("=" * 60)

    # --------------------------------------------------------
    # 1. 公共数据
    # --------------------------------------------------------

    print("\n📚 第一步：获取公共数据")

    try:
        news = get_all_news()
    except Exception as e:

        print(f"❌ 新闻获取失败：{e}")

        news = {
            "domestic": [],
            "international": [],
        }


    try:
        gold = get_gold_price()
    except Exception as e:

        print(f"❌ 金价获取失败：{e}")

        gold = {
            "price_usd_oz": "暂时无法获取",
            "updated_at": None,
            "as_of": None,
            "status": "error",
            "source": None,
        }


    print("\n📊 公共数据获取完成")

    print(
        f"国内新闻：{len(news['domestic'])} 条"
    )

    print(
        f"国际新闻：{len(news['international'])} 条"
    )

    print(
        f"国际金价：{gold['price_usd_oz']}"
    )


    # --------------------------------------------------------
    # 2. 每个人分别处理
    # --------------------------------------------------------

    for friend in RECIPIENTS:

        name = friend["name"]
        token = friend["token"].strip()
        city = friend["city"]

        print("\n" + "=" * 60)
        print(f"👤 正在处理：{name}")
        print(f"📍 城市：{city}")
        print("=" * 60)


        # ----------------------------------------------------
        # 天气
        # ----------------------------------------------------

        try:

            weather = get_weather(city)

            print(
                f"🌡 {weather['city']}："
                f"{weather['temperature']}℃"
            )

        except Exception as e:

            print(
                f"❌ {name} 天气获取失败：{e}"
            )

            continue


        # ----------------------------------------------------
        # AI 总编辑
        # ----------------------------------------------------

        try:

            edited = ai_editor(
                weather,
                news,
                gold
            )

            print("✅ GLM 总编辑完成")

        except Exception as e:

            print(
                f"❌ GLM 编辑失败：{e}"
            )

            # AI 失败时仍然给出基础天气信息
            edited = {
                "greeting": "早上好，祝你今天顺利！",

                "weather_summary": (
                    f"今天{weather['city']}天气"
                    f"{weather_code_to_text(weather['weather_code'])}，"
                    f"当前气温 {weather['temperature']}℃。"
                ),

                "weather_advice": (
                    "请根据实际天气情况合理安排穿衣和出行。"
                ),

                "domestic_news": [],

                "international_news": [],

                "gold_summary": (
                    "AI 编辑暂时不可用，以上为 API 获取的金价。"
                ),

                "daily_tip": "合理安排今天的工作和休息。",
            }


        # ----------------------------------------------------
        # 生成 HTML
        # ----------------------------------------------------

        content = render_message(
            name=name,
            weather=weather,
            gold=gold,
            edited=edited
        )


        # ----------------------------------------------------
        # PushPlus
        # ----------------------------------------------------

        success = send_to_friend(
            friend_token=token,
            content=content,
            name=name
        )

        if success:
            print(f"🎉 {name} 推送完成")
        else:
            print(f"⚠️ {name} 推送失败")


    print("\n" + "=" * 60)
    print("🏁 每日早报执行结束")
    print("=" * 60)


if __name__ == "__main__":
    main()
