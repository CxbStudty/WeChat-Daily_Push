import os
import json
import random
import re
import time
from datetime import datetime, timedelta, timezone
from html import escape

import requests


# ============================================================
# 配置
# ============================================================


def read_env(name, required=True):
    """
    读取环境变量。

    必填项缺失时给出清晰提示，而不是直接抛 KeyError，
    这样在 GitHub Actions 日志里一眼就能看出是哪个 Secret 没配。
    """

    value = os.environ.get(name, "").strip()

    if not value and required:
        raise SystemExit(
            f"❌ 缺少环境变量 {name}。请在 GitHub 仓库 "
            f"Settings → Secrets and variables → Actions 中配置。"
        )

    return value


ZHIPU_API_KEY = read_env("ZHIPU_API_KEY")
PUSHPLUS_TOKEN = read_env("PUSHPLUS_TOKEN")

# 新闻属于“可选能力”：即使没配 NEWS_API_KEY，天气 / 问候语 / 每日一句 / 金价照样能发
NEWS_API_KEY = read_env("NEWS_API_KEY", required=False)

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

# 自己：使用 PUSHPLUS_TOKEN 直接发送给自己
# 不要把自己的 Token 填到 RECIPIENTS 里，也不要给自己的消息传 "to"。
MY_RECIPIENT = {
    "name": "我",
    "city": "烟台",
}

# 好友：这里填写“我的好友”中的好友 Token
RECIPIENTS = [
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
# 每日问候语 / 每日一句：主题轮换
# ============================================================
#
# 为什么要有主题池？
#
# 免费模型在提示词完全一样时，容易连着几天写出很像的句子。
# 这里按「日期 + 收件人」算出一个稳定序号，每天固定换一个主题，
# 一个主题池 24 条 → 同一个人 24 天内不会重复同一个主题，
# 不同的人算出来的主题也会自然错开。
# ============================================================

QUOTE_THEMES = [
    "好好照顾自己",
    "慢慢来，比较快",
    "专注眼前这一件事",
    "给自己一点勇气",
    "把心放平",
    "允许自己休息",
    "和在意的人多说几句话",
    "坚持一件小事",
    "少一点自我苛责",
    "保持好奇",
    "认真吃饭，好好睡觉",
    "接受不完美",
    "给自己留一点空白",
    "把难的事拆小",
    "记得抬头看看天",
    "温柔地对待身边的人",
    "该放下的时候就放下",
    "今天也值得被期待",
    "把注意力放回自己身上",
    "慢一点，也算前进",
    "心里有光，路就不暗",
    "不着急，日子还长",
    "对自己耐心一点",
    "把今天过好就很好",
]

GREETING_ANGLES = [
    "顺着今天真实的天气说一句贴心话",
    "点出今天的日期或星期，配一句轻松的问候",
    "像老朋友一样随口打个招呼",
    "从“新的一天开始了”的角度问候",
    "提醒对方先喝口水、吃口早饭再出门",
    "用一句很短很轻的问候开头",
]


def china_today():
    """返回北京时间对应的 date 对象。"""

    return datetime.now(timezone(timedelta(hours=8))).date()


def today_cn():
    """返回 (日期文本, 星期文本)，例如 ("2026年9月21日", "星期一")。"""

    now = datetime.now(timezone(timedelta(hours=8)))

    weekdays = [
        "星期一", "星期二", "星期三", "星期四",
        "星期五", "星期六", "星期日",
    ]

    date_text = f"{now.year}年{now.month}月{now.day}日"

    return date_text, weekdays[now.weekday()]


def daily_index(seed_text, total):
    """
    按「今天日期 + 收件人标识」算一个稳定序号。

    同一天同一个人结果固定；换一天、换个人就会错开。
    """

    offset = sum(ord(ch) for ch in seed_text)

    return (china_today().toordinal() + offset) % total


def pick_quote_theme(seed_text):
    return QUOTE_THEMES[daily_index(seed_text, len(QUOTE_THEMES))]


def pick_greeting_angle(seed_text):
    return GREETING_ANGLES[
        daily_index(seed_text + "-greeting", len(GREETING_ANGLES))
    ]


def fallback_edited(weather, news):
    """
    AI 不可用时的兜底文案。

    问候语和短句从池子里随机取，避免“每次失败都发同一句话”。
    """

    return {
        "greeting": random.choice(FALLBACK_GREETINGS),

        "daily_quote": random.choice(FALLBACK_QUOTES),

        "weather_summary": (
            f"今天{weather['city']}天气"
            f"{weather_code_to_text(weather['weather_code'])}，"
            f"当前气温 {weather['temperature']}℃。"
        ),

        "weather_advice": (
            "请根据实际天气情况合理安排穿衣和出行。"
        ),

        "domestic_news": news.get("domestic", [])[:3],

        "international_news": news.get("international", [])[:3],

        "gold_summary": (
            "AI 编辑暂时不可用，以上为 API 获取的金价。"
        ),

        "daily_tip": "合理安排今天的工作和休息。",
    }


FALLBACK_GREETINGS = [
    "早上好，新的一天开始了。",
    "早安，今天也要好好吃饭。",
    "早上好，愿你今天顺顺利利。",
    "早安，先喝口热水，再慢慢开始。",
    "早上好，今天也辛苦了。",
]

FALLBACK_QUOTES = [
    "不用一下子走很远，往前挪一小步就很好。",
    "照顾好自己，是今天最重要的一件事。",
    "慢一点没关系，你还在往前走就够了。",
    "把眼前这一件事做好，今天就不算白过。",
    "累了就歇一会儿，路还长，不用急。",
    "别对自己太严格，你已经做得很好了。",
    "心情不太好的时候，先去窗边站一会儿。",
    "今天也会有好事情发生，值得期待一下。",
    "把该放下的放下，把该做的做了，就很了不起。",
    "日子是自己的，按自己的节奏来就好。",
]


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
    return (datetime.now(china_tz).date() - timedelta(days=1)).strftime("%Y-%m-%d")


def get_news_window():
    """Use a fully-aged rolling window because NewsAPI free/developer plans can delay recent articles."""
    now_utc = datetime.now(timezone.utc)
    return now_utc - timedelta(hours=72), now_utc - timedelta(hours=24)


def get_news(query, language="zh", page_size=10):
    if not NEWS_API_KEY:
        print("⚠️ 未配置 NEWS_API_KEY，跳过新闻获取。")
        return [], {"query": query, "error": "未配置 NEWS_API_KEY"}

    from_dt, to_dt = get_news_window()
    print(f"📰 获取新闻：{query} / {from_dt.isoformat()} ~ {to_dt.isoformat()}")

    params = {
        "q": query,
        "from": from_dt.isoformat(),
        "to": to_dt.isoformat(),
        "language": language,
        "sortBy": "publishedAt",
        "pageSize": page_size,
        "page": 1,
        "searchIn": "title,description",
    }

    try:
        data = http_get(NEWS_API_URL, params=params, headers={"X-Api-Key": NEWS_API_KEY})
    except Exception as e:
        print(f"❌ 新闻请求异常：{e}")
        return [], {"query": query, "error": str(e)}

    if data.get("status") != "ok":
        err = data.get("message", str(data))
        print(f"❌ News API 错误：{err}")
        return [], {"query": query, "error": err, "code": data.get("code")}

    raw = data.get("articles", []) or []
    print(f"   totalResults={data.get('totalResults', 0)}, returned={len(raw)}")
    articles = []
    for a in raw:
        title = (a.get("title") or "").strip()
        if not title:
            continue
        articles.append({
            "title": title,
            "description": (a.get("description") or "").strip(),
            "source": ((a.get("source") or {}).get("name") or "未知来源").strip(),
            "url": (a.get("url") or "").strip(),
            "published_at": a.get("publishedAt") or "",
        })
    return articles, None


def dedupe_news(items):
    seen = set()
    out = []
    for item in items:
        key = item.get("url") or item.get("title")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def get_all_news():
    if not NEWS_API_KEY:
        print("⚠️ 未配置 NEWS_API_KEY，本次跳过新闻模块。")
        return {
            "domestic": [],
            "international": [],
            "window": {},
            "errors": [{"error": "未配置 NEWS_API_KEY"}],
        }

    domestic_queries = ["中国", "中国经济", "中国科技", "中国社会"]
    international_queries = ["United States", "Europe", "Japan", "South Korea", "Middle East", "Russia"]
    domestic = []
    international = []
    errors = []

    for q in domestic_queries:
        items, err = get_news(q, "zh", 10)
        domestic.extend(items)
        if err:
            errors.append(err)
    for q in international_queries:
        items, err = get_news(q, "en", 10)
        international.extend(items)
        if err:
            errors.append(err)

    domestic = dedupe_news(domestic)
    international = dedupe_news(international)
    from_dt, to_dt = get_news_window()
    print(f"📰 新闻汇总：国内 {len(domestic)} 条，国际 {len(international)} 条，错误 {len(errors)} 个")
    return {"domestic": domestic, "international": international,
            "window": {"from": from_dt.isoformat(), "to": to_dt.isoformat(), "label": "近期新闻"},
            "errors": errors}


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

SYSTEM_PROMPT = """你是一名每日早报总编辑，只能依据输入数据编辑，不能自行搜索或编造事实。

硬性规则：
1. 天气、新闻、金价只能使用输入数据。
2. 不得虚构新闻、数字、来源。
3. 新闻不足就如实写“暂无足够新闻信息”，不要凑数。
4. 不写诗，不生成“人民日报金句”，不使用口号式表达。
5. 不加入政治立场、政治评价或煽动性语言。
6. greeting：一句温暖、自然、口语化的早安问候语，12-30 字，只写一句话。要按“问候语角度要求”来写，可以自然地带入今天的日期、星期或真实天气，不要提“人工智能/AI/模型”。
7. daily_quote：一句原创、简短、克制、温暖的励志或治愈短句，15-35 字，围绕“每日一句话的主题”来写，但句子里不要出现主题标签本身。不署名、不冒充名人名言，不用“让我们一起”“加油”“奥利给”这类口号，语气像朋友随口说的一句话。
8. greeting 和 daily_quote 都必须全新创作：同一个人每天不重样，不同的人彼此不重样，禁止套用固定模板。
9. 国际新闻输入可能为英文，请用中文准确概括，不得增加输入中没有的事实。
10. 国内最多 3 条，国际最多 3 条。
11. 每条新闻保留原始 url 和 source。
12. gold_summary 只做简短事实说明，不预测涨跌。
13. 必须输出合法 JSON，不要 Markdown 代码块。

JSON 格式：
{
  "greeting":"...", "daily_quote":"...", "weather_summary":"...", "weather_advice":"...",
  "domestic_news":[{"title":"...","summary":"...","source":"...","url":"..."}],
  "international_news":[{"title":"...","summary":"...","source":"...","url":"..."}],
  "gold_summary":"...", "daily_tip":"...", "news_status":"..."
}"""


def ai_editor(weather, news, gold, seed_text):
    """
    调用 GLM 生成当天内容。

    seed_text：收件人标识（例如 “我-烟台”），用来错开每天的问候语主题，
    保证同一个人不同天、不同人同一天都不会撞句子。
    """

    print("🤖 GLM 正在进行每日早报总编辑...")

    date_text, weekday = today_cn()

    theme = pick_quote_theme(seed_text)
    greeting_angle = pick_greeting_angle(seed_text)

    print(f"🎯 每日一句主题：{theme}")
    print(f"🎯 问候语角度：{greeting_angle}")

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
        "今天日期": f"{date_text} {weekday}",
        "收件人": seed_text,
        "问候语角度要求": greeting_angle,
        "每日一句话的主题": theme,
        "weather": weather_text,
        "news_window": news.get("window", {}),
        "domestic_news": news.get("domestic", []),
        "international_news": news.get("international", []),
        "news_errors": news.get("errors", []),
        "gold": gold,
    }

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(editor_input, ensure_ascii=False, indent=2)},
        ],
        # 温度调高一点，问候语和短句才不会天天长得一样
        "temperature": 0.9,
        "max_tokens": 3000,
        "stream": False,
    }

    # 免费模型高峰期偶发 429 / 5xx，重试 3 次，避免整天内容掉回兜底文案
    data = None
    last_error = None

    for attempt in range(1, 4):
        try:
            response = session.post(
                ZHIPU_URL,
                headers={
                    "Authorization": f"Bearer {ZHIPU_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=90,
            )
            response.raise_for_status()
            data = response.json()
            break

        except requests.RequestException as e:
            last_error = e
            print(f"⚠️ GLM 第 {attempt} 次请求失败：{e}")
            if attempt < 3:
                time.sleep(5 * attempt)

    if data is None:
        raise RuntimeError(f"GLM 请求连续失败：{last_error}")

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(f"GLM 返回格式异常：{data}")

    content = clean_json_text(content)

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start, end = content.find("{"), content.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(content[start:end + 1])
            except json.JSONDecodeError:
                pass
        raise RuntimeError(f"GLM 没有返回合法 JSON：\n{content}")


def render_news(news_list):
    if not news_list:
        return "<p>暂无足够新闻信息。</p>"
    out = []
    for item in news_list[:3]:
        title = escape(str(item.get("title", "")))
        summary = escape(str(item.get("summary", item.get("description", ""))))
        source = escape(str(item.get("source", "")))
        url = str(item.get("url", "")).strip()
        if url.startswith(("http://", "https://")):
            title = f'<a href="{escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">{title}</a>'
        out.append(f"""<div style="margin-bottom:12px;"><div style="font-weight:bold;">{title}</div><div style="margin-top:3px;">{summary}</div><div style="color:#888;font-size:12px;margin-top:2px;">来源：{source}</div></div>""")
    return "".join(out)


def render_message(weather, gold, edited):

    city = escape(weather["city"])

    date_text, weekday = today_cn()

    greeting = escape(
        str(edited.get("greeting", "早上好！"))
    )

    daily_quote = escape(
        str(
            edited.get(
                "daily_quote",
                "慢一点也没关系，照顾好自己，再继续向前。"
            )
        )
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
        color:#999;
        font-size:12px;
        margin-bottom:10px;
    ">
        📅 {date_text} {weekday}
    </div>


    <div style="
        font-size:20px;
        font-weight:bold;
        margin-bottom:8px;
    ">
        ☀️ {greeting}
    </div>


    <div style="
        background:#f0f7f3;
        padding:10px 12px;
        border-radius:10px;
        margin-bottom:15px;
    ">
        🌿 <b>每日一句：</b>{daily_quote}
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
        🇨🇳 近期国内新闻
    </div>

    {domestic_news}


    <div style="
        font-size:17px;
        font-weight:bold;
        margin-top:15px;
        margin-bottom:8px;
    ">
        🌍 近期国际新闻
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

def push_title():
    """推送标题带上日期，多条消息在微信里也好区分。"""

    now = datetime.now(timezone(timedelta(hours=8)))

    return f"☀️ 每日早报 · {now.month}月{now.day}日"


def send_to_self(content):
    """
    给自己发送：
    使用 PUSHPLUS_TOKEN 作为发送账号 Token，
    不传 "to"，这样 PushPlus 会发送给当前账号本人。
    """

    print("📨 正在发送给：我")

    payload = {
        "token": PUSHPLUS_TOKEN.strip(),
        "title": push_title(),
        "content": content,
        "template": "html",
        "channel": "wechat",
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
        print("✅ 我 PushPlus 请求成功")
        return True

    print(
        f"❌ 我 PushPlus 业务错误："
        f"{result.get('msg')} / {result.get('data')}"
    )

    if code == 903:
        print(
            "⚠️ PushPlus Token 无效，请检查 GitHub Secret "
            "PUSHPLUS_TOKEN 是否填写为自己的 PushPlus 用户 Token。"
        )

    elif code == 905:
        print(
            "⚠️ PushPlus 当前账号尚未完成实名认证。"
        )

    elif code == 999:
        print(
            "⚠️ PushPlus 返回 999。请检查自己的 PushPlus 账号、"
            "公众号关注关系以及 PUSHPLUS_TOKEN。"
        )

    return False


def send_to_friend(friend_token, content, name):

    # 防止复制 Token 时混入空格 / Tab / 换行
    friend_token = friend_token.strip()

    print(f"📨 正在发送给：{name}")
    print(f"🔑 Token 长度：{len(friend_token)}")

    payload = {
        "token": PUSHPLUS_TOKEN.strip(),
        "title": push_title(),
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

def build_and_send(name, city, send_func, news, gold):
    """
    单个收件人的完整流程：天气 -> AI 编辑 -> 渲染 -> 推送。

    news / gold：本次运行共享的公共数据（只拉一次，所有收件人复用）。
    send_func(content)：把渲染好的 HTML 发出去，返回是否成功。
    """

    print("\n" + "=" * 60)
    print(f"👤 正在处理：{name}")
    print(f"📍 城市：{city}")
    print("=" * 60)

    try:
        weather = get_weather(city)

        print(
            f"🌡 {weather['city']}："
            f"{weather['temperature']}℃"
        )

    except Exception as e:
        print(f"❌ {name} 天气获取失败：{e}")
        return False

    # 用来错开每个人的每日一句主题
    seed_text = f"{name}-{city}"

    try:
        edited = ai_editor(
            weather,
            news=news,
            gold=gold,
            seed_text=seed_text,
        )

        print("✅ GLM 总编辑完成")

    except Exception as e:
        print(f"❌ GLM 编辑失败：{e}")

        # AI 失败时仍然给出基础信息，问候语和短句从兜底池随机取
        edited = fallback_edited(weather, news)

    # AI 偶尔会漏字段 / 返回空串，这里补齐
    if not str(edited.get("greeting", "")).strip():
        edited["greeting"] = random.choice(FALLBACK_GREETINGS)

    if not str(edited.get("daily_quote", "")).strip():
        edited["daily_quote"] = random.choice(FALLBACK_QUOTES)

    content = render_message(
        weather=weather,
        gold=gold,
        edited=edited,
    )

    try:
        return send_func(content)
    except Exception as e:
        # 一个人推送失败不要影响后面的人
        print(f"❌ {name} 推送异常：{e}")
        return False


def main():

    print("=" * 60)
    print("☀️ 每日早报开始")
    print("=" * 60)

    date_text, weekday = today_cn()
    print(f"📅 今天：{date_text} {weekday}")

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
            "window": {},
            "errors": [{"error": str(e)}],
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
    # 2. 处理自己
    # --------------------------------------------------------

    ok = build_and_send(
        name=MY_RECIPIENT["name"],
        city=MY_RECIPIENT["city"],
        send_func=send_to_self,
        news=news,
        gold=gold,
    )

    if ok:
        print(f"🎉 {MY_RECIPIENT['name']} 推送完成")
    else:
        print(f"⚠️ {MY_RECIPIENT['name']} 推送失败")

    # --------------------------------------------------------
    # 3. 处理好友
    # --------------------------------------------------------

    for friend in RECIPIENTS:

        name = friend["name"]
        token = friend["token"].strip()
        city = friend["city"]

        ok = build_and_send(
            name=name,
            city=city,
            send_func=lambda content, _token=token, _name=name: send_to_friend(
                friend_token=_token,
                content=content,
                name=_name,
            ),
            news=news,
            gold=gold,
        )

        if ok:
            print(f"🎉 {name} 推送完成")
        else:
            print(f"⚠️ {name} 推送失败")

    print("\n" + "=" * 60)
    print("🏁 每日早报执行结束")
    print("=" * 60)


if __name__ == "__main__":
    main()
