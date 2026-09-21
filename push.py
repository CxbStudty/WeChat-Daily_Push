import os
import json
import random
import re
import time
from datetime import datetime, timedelta, timezone
from html import escape

import requests


# ============================================================
# 版本标记
# ============================================================
#
# 这个字符串会打印在 Action 日志最开头。
# 换代码之后点一次 Run workflow，看到这行就说明新代码生效了。
# ============================================================

CODE_VERSION = "2026-09-21 全 AI 生成版"


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

# PushPlus 正文过长时容易被渠道截断，超过这个长度只提醒、不裁剪
CONTENT_LENGTH_HINT = 20000


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
# 随机创作种子（重要）
# ============================================================
#
# 下面这些列表**不是**最终文案，而是每次运行随机抽一条、
# 塞给 AI 当“今天的灵感方向”用的。
#
# 为什么不把文案写死在这里：
#   写死的话，兜底文案、模板句式每天长一个样，看着就枯燥。
#   这里用的是“随机灵感 + 高温度 + 禁止套话”三件套，
#   每次运行抽到的方向都不一样，AI 每次写出来的句子自然也不一样。
#
# 想让它更有变化，直接往下面的列表里加句子就行，加得越多越不重样。
# ============================================================

GREETING_SEEDS = [
    "像老朋友一样随口打个招呼",
    "顺着今天真实的天气说一句贴心话",
    "提醒对方先喝口水、吃口早饭再出门",
    "轻轻提一句今天是星期几",
    "用一句很短、很轻的话开头",
    "从窗外天色这样的小细节说起",
    "像家里人那样叮嘱一句",
    "从“今天打算做点什么”这样的期待说起",
    "顺着季节或节气说一句",
    "用一句能让人放松下来的话开头",
    "假装刚刚碰面，随口问候一声",
    "从关心对方昨晚睡得怎么样说起",
    "从“新的一天开始了”这个角度问候",
    "提一句今天适合做什么",
]

QUOTE_SEEDS = [
    "好好照顾自己的身体",
    "允许自己慢一点",
    "把注意力放回当下",
    "对自己少一点苛责",
    "坚持一件很小的事",
    "允许自己休息和发呆",
    "和在意的人保持联系",
    "接受不完美",
    "把难的事拆小",
    "给自己一点勇气",
    "心里留一点期待",
    "放下已经过去的事",
    "认真吃一顿饭",
    "抬头看看天",
    "不着急，慢慢来",
    "温柔地提醒自己一句",
    "把今天过好就够了",
    "少想一点，多做一点",
]

TONE_SEEDS = [
    "温柔平静",
    "轻松随口",
    "亲切，像家人说话",
    "淡淡的、克制的",
    "简短干脆",
    "带一点点俏皮",
]

ADVICE_SEEDS = [
    "重点提醒穿衣和体感温度",
    "重点提醒要不要带伞",
    "重点提醒风大和出行安全",
    "重点提醒早晚温差",
    "重点提醒晒不晒、要不要防晒",
    "重点提醒室内外温差",
]

TIP_SEEDS = [
    "关于喝水和作息",
    "关于久坐之后活动一下身体",
    "关于眼睛和屏幕",
    "关于睡前放松",
    "关于早饭吃什么",
    "关于情绪和呼吸",
    "关于收拾一小块桌面或房间",
]

# 明确禁止出现的套话：这些句子在朋友圈和小红书已经烂大街了，
# 免费模型特别爱写，直接在提示词里拉黑。
BANNED_PHRASES = [
    "让我们一起",
    "加油",
    "奥利给",
    "岁月静好",
    "未来可期",
    "人间值得",
    "不负韶华",
    "向阳而生",
    "心中有光",
    "做最好的自己",
    "最好的自己",
    "愿你历尽千帆",
    "山河远阔",
    "余生请多指教",
    "每一天都是崭新的一天",
    "生活不止眼前的苟且",
    "浅浅喜，静静爱",
    "一定要幸福呀",
]


def pick(pool):
    """从灵感池里随机抽一条。"""

    return random.choice(pool)


# ============================================================
# 中文日期
# ============================================================

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
# 新闻窗口
# ============================================================

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
# 清理 JSON 文本
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


def parse_json_block(text):
    """从模型返回里抠出 JSON，容忍前后夹带的说明文字。"""

    content = clean_json_text(text)

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start, end = content.find("{"), content.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(content[start:end + 1])
            except json.JSONDecodeError:
                pass

    return None


# ============================================================
# GLM 调用
# ============================================================

def call_glm(messages, temperature=1.0, max_tokens=3000, retries=3):
    """
    统一的 GLM 调用。

    免费模型高峰期容易 429 / 5xx，这里做几次退避重试。
    """

    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "top_p": 0.95,
        "max_tokens": max_tokens,
        "stream": False,
    }

    last_error = None

    for attempt in range(1, retries + 1):
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

        except (requests.RequestException, ValueError) as e:
            last_error = e
            print(f"⚠️ GLM 第 {attempt}/{retries} 次请求失败：{e}")
            if attempt < retries:
                time.sleep(5 * attempt)
            continue

        try:
            return data["choices"][0]["message"]["content"]

        except (KeyError, IndexError, TypeError):
            last_error = RuntimeError(f"GLM 返回格式异常：{data}")
            print(f"⚠️ GLM 第 {attempt}/{retries} 次返回格式异常")
            if attempt < retries:
                time.sleep(3 * attempt)

    raise RuntimeError(f"GLM 调用失败：{last_error}")


# ============================================================
# GLM 总编辑
# ============================================================

SYSTEM_PROMPT = """你是一名每日早报总编辑，同时负责写这一天所有的问候和贴心话。
只能依据输入数据编辑，不能自行搜索或编造事实。

【硬性规则】
1. 天气、新闻、金价只能使用输入数据，不得虚构新闻、数字、来源。
2. 新闻不足就如实写“暂无足够新闻信息”，不要凑数。
3. 不写诗，不使用口号式表达，不加入政治立场、政治评价或煽动性语言。
4. 国际新闻输入可能为英文，请用中文准确概括，不得增加输入中没有的事实。
5. 国内最多 3 条，国际最多 3 条，每条保留原始 url 和 source。
6. gold_summary 只做简短事实说明，不预测涨跌。
7. 不要使用 emoji（版面上已经有图标了），不要出现“AI”“模型”“人工智能”这类词。
8. 必须输出合法 JSON，不要 Markdown 代码块。

【所有文字都要现写，禁止套话】
下面这些表达一律不许出现：
<<BAN>>

【各部分怎么写】
greeting：一句温暖、自然、口语化的早安问候语，12-30 字，只写一句。
  灵感方向：<<GREETING_SEED>>
  可以自然地带入今天的日期、星期或真实天气，但别硬塞。

daily_quote：一句原创、简短、克制、温暖的励志或治愈短句，15-35 字。
  灵感方向：<<QUOTE_SEED>>
  语气：<<TONE>>

weather_summary：用一句话把今天的天气说清楚，20-40 字，只说事实。

weather_advice：根据输入的真实天气给一条具体可执行的建议，20-45 字。
  重点方向：<<ADVICE_SEED>>
  要落到具体动作上（穿什么、带不带伞、什么时候出门），不要写“注意天气变化”这种空话。

daily_tip：一条和今天有关的生活小贴士，15-40 字。
  方向：<<TIP_SEED>>
  必须和 weather_advice 不同，不要重复说穿衣带伞的事。

news_status：用一句话说明今天的新闻情况，30 字以内。
  例如“新闻抓取正常，国内 8 条 / 国际 6 条”，或者“新闻接口暂时不可用，本次不展示新闻”。

【格式】
{
  "greeting":"...", "daily_quote":"...", "weather_summary":"...", "weather_advice":"...",
  "domestic_news":[{"title":"...","summary":"...","source":"...","url":"..."}],
  "international_news":[{"title":"...","summary":"...","source":"...","url":"..."}],
  "gold_summary":"...", "daily_tip":"...", "news_status":"..."
}"""


# AI 调用的 JSON 里会出现的字段，全部都要在 render_message 里有对应位置。
# 漏掉一个就会变成“日志里生成了，消息里却看不到”。
RENDERED_KEYS = {
    "greeting",
    "daily_quote",
    "weather_summary",
    "weather_advice",
    "domestic_news",
    "international_news",
    "gold_summary",
    "daily_tip",
    "news_status",
}


def warn_unrendered(edited):
    """
    检查 AI 返回了、但消息里没有地方展示的字段。

    这是之前踩过的坑：news_status 一直是生成了却没渲染。
    """

    extra = [
        key for key in edited.keys()
        if key not in RENDERED_KEYS
    ]

    if extra:
        print(f"⚠️ 以下字段 AI 生成了但消息里没有展示区域：{extra}")


def ai_editor(weather, news, gold):
    """调用 GLM 生成当天全部文案。"""

    print("🤖 GLM 正在进行每日早报总编辑...")

    date_text, weekday = today_cn()

    greeting_seed = pick(GREETING_SEEDS)
    quote_seed = pick(QUOTE_SEEDS)
    tone = pick(TONE_SEEDS)
    advice_seed = pick(ADVICE_SEEDS)
    tip_seed = pick(TIP_SEEDS)

    print(f"🎲 问候语灵感：{greeting_seed}")
    print(f"🎲 每日一句灵感：{quote_seed}（语气：{tone}）")
    print(f"🎲 天气建议方向：{advice_seed}")
    print(f"🎲 小贴士方向：{tip_seed}")

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
        "weather": weather_text,
        "news_window": news.get("window", {}),
        "domestic_news": news.get("domestic", []),
        "international_news": news.get("international", []),
        "news_errors": news.get("errors", []),
        "gold": gold,
    }

    # 注意：用 replace 而不是 str.format()
    # 提示词里含有 JSON 的 {} ，用 format() 会直接报错。
    system_prompt = SYSTEM_PROMPT

    for placeholder, value in [
        ("<<BAN>>", "、".join(BANNED_PHRASES)),
        ("<<GREETING_SEED>>", greeting_seed),
        ("<<QUOTE_SEED>>", quote_seed),
        ("<<TONE>>", tone),
        ("<<ADVICE_SEED>>", advice_seed),
        ("<<TIP_SEED>>", tip_seed),
    ]:
        system_prompt = system_prompt.replace(placeholder, value)

    # 温度每次随机：同样的灵感方向，写出来的句子也不一样
    temperature = round(random.uniform(0.8, 1.0), 2)
    print(f"🎲 采样温度：{temperature}")

    content = call_glm(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(editor_input, ensure_ascii=False, indent=2)},
        ],
        temperature=temperature,
        max_tokens=3000,
    )

    edited = parse_json_block(content)

    if edited is None:
        raise RuntimeError(f"GLM 没有返回合法 JSON：\n{content}")

    warn_unrendered(edited)

    return edited


def ai_warm_words_only(weather):
    """
    主编调用失败时的抢救方案：

    再单独要一次问候语和每日一句，费用极低，但能保证“温暖的话”
    仍然是 AI 现写的，而不是掉回固定文案。
    """

    print("🩺 尝试用轻量调用单独生成问候语和每日一句...")

    date_text, weekday = today_cn()

    warm_prompt = """你是专门写温暖短句的写作者。只输出 JSON，不要任何解释。

要求：
1. greeting：一句温暖、口语化的早安问候语，12-30 字。
2. daily_quote：一句原创、温暖的励志或治愈短句，15-35 字，像朋友随口说的一句话。
3. 两句话都必须全新创作，不要套话，不要 emoji，不要署名，不要提到 AI 或模型。
4. 不要出现这些表达：<<BAN>>

格式：{"greeting":"...", "daily_quote":"..."}"""

    system_prompt = warm_prompt.replace("<<BAN>>", "、".join(BANNED_PHRASES))

    user_prompt = json.dumps({
        "今天日期": f"{date_text} {weekday}",
        "城市": weather.get("city"),
        "天气": weather_code_to_text(weather.get("weather_code")),
        "问候语灵感": pick(GREETING_SEEDS),
        "每日一句灵感": pick(QUOTE_SEEDS),
    }, ensure_ascii=False)

    try:
        content = call_glm(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=round(random.uniform(0.85, 1.0), 2),
            max_tokens=400,
            retries=2,
        )

        data = parse_json_block(content)

        if data and str(data.get("greeting", "")).strip() and str(data.get("daily_quote", "")).strip():
            return {
                "greeting": str(data["greeting"]).strip(),
                "daily_quote": str(data["daily_quote"]).strip(),
            }

        print(f"⚠️ 轻量调用没有返回可用内容：{content}")

    except Exception as e:
        print(f"⚠️ 轻量调用失败：{e}")

    return None


# 两次 AI 都失败时的最后兜底（随机取，尽量不重样）
LAST_RESORT_GREETINGS = [
    "早上好，新的一天开始了。",
    "早安，今天也要好好吃饭。",
    "早上好，愿你今天顺顺利利。",
    "早安，先喝口热水，再慢慢开始。",
    "早上好，今天也辛苦了。",
    "早安，慢慢来就好。",
]

LAST_RESORT_QUOTES = [
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


def fallback_edited(weather, news, gold):
    """
    AI 完全不可用时的兜底。

    仍然先试着用轻量调用单独写问候语和每日一句；
    真的两次都失败，才退回随机兜底句。
    """

    warm = ai_warm_words_only(weather)

    if warm:
        greeting = warm["greeting"]
        daily_quote = warm["daily_quote"]
    else:
        greeting = random.choice(LAST_RESORT_GREETINGS)
        daily_quote = random.choice(LAST_RESORT_QUOTES)

    news_status = (
        f"新闻抓取：国内 {len(news.get('domestic', []))} 条 / "
        f"国际 {len(news.get('international', []))} 条"
    )

    if news.get("errors"):
        news_status += "（部分查询失败）"

    return {
        "greeting": greeting,
        "daily_quote": daily_quote,

        "weather_summary": (
            f"今天{weather['city']}天气"
            f"{weather_code_to_text(weather['weather_code'])}，"
            f"当前气温 {weather['temperature']}℃，"
            f"今日 {weather['today_min']}℃ ～ {weather['today_max']}℃。"
        ),

        "weather_advice": (
            "请根据实际天气情况合理安排穿衣和出行。"
        ),

        "domestic_news": news.get("domestic", [])[:3],
        "international_news": news.get("international", [])[:3],

        "gold_summary": "以上为接口获取到的金价，仅供参考。",

        "daily_tip": "合理安排今天的工作和休息。",

        "news_status": news_status,
    }


# ============================================================
# 渲染
# ============================================================

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


def render_news_section(edited):
    """
    新闻区块。

    没有任何新闻时，不再留两个空的“国内/国际”空格子，
    而是合成一块，并把 AI 写的 news_status 显示出来。
    """

    domestic = edited.get("domestic_news", []) or []
    international = edited.get("international_news", []) or []

    news_status = str(edited.get("news_status", "") or "").strip()

    status_html = (
        f'<div style="margin-top:10px;color:#999;font-size:12px;">'
        f'📌 {escape(news_status)}</div>'
        if news_status else ""
    )

    if not domestic and not international:
        return f"""
    <div style="
        background:#f5f7fa;
        padding:12px;
        border-radius:10px;
        margin-bottom:15px;
    ">
        <div style="font-size:17px;font-weight:bold;">
            📰 新闻
        </div>
        <div style="margin-top:5px;">
            暂无足够新闻信息。
        </div>
        {status_html}
    </div>
"""

    return f"""
    <div style="
        font-size:17px;
        font-weight:bold;
        margin-bottom:8px;
    ">
        🇨🇳 近期国内新闻
    </div>

    {render_news(domestic)}


    <div style="
        font-size:17px;
        font-weight:bold;
        margin-top:15px;
        margin-bottom:8px;
    ">
        🌍 近期国际新闻
    </div>

    {render_news(international)}

    {status_html}
"""


def render_message(weather, gold, edited):
    """
    把 AI 生成的内容渲染成 HTML。

    注意：edited 里每个字段都必须在这里有位置，
    否则就会出现“日志里生成了、消息里却看不到”。
    """

    city = escape(weather["city"])

    date_text, weekday = today_cn()

    greeting = escape(
        str(edited.get("greeting", "") or "早上好")
    )

    daily_quote = escape(
        str(edited.get("daily_quote", "") or "照顾好自己，慢慢来。")
    )

    weather_summary = escape(
        str(edited.get("weather_summary", "") or "")
    )

    weather_advice = escape(
        str(edited.get("weather_advice", "") or "")
    )

    gold_summary = escape(
        str(edited.get("gold_summary", "") or "")
    )

    daily_tip = escape(
        str(edited.get("daily_tip", "") or "")
    )

    news_block = render_news_section(edited)

    temperature = weather.get("temperature")
    today_min = weather.get("today_min")
    today_max = weather.get("today_max")
    apparent = weather.get("apparent_temperature")
    rain = weather.get("rain_probability")
    wind = weather.get("wind_speed")
    humidity = weather.get("humidity")

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
            当前：{temperature}℃（体感 {apparent}℃）
        </div>

        <div>
            今日：{today_min}℃ ～ {today_max}℃
        </div>

        <div>
            降水概率：{rain}% ｜ 湿度：{humidity}% ｜ 风速：{wind}km/h
        </div>

        <div style="margin-top:6px;">
            {weather_summary}
        </div>

        <div style="
            margin-top:6px;
            color:#555;
        ">
            💡 {weather_advice}
        </div>

    </div>

{news_block}

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
        background:#fdf3f7;
        padding:12px;
        border-radius:10px;
        margin-top:15px;
    ">
        🌱 <b>今日小贴士：</b>{daily_tip}
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


def check_content(content):
    """检查正文长度，过长时提醒（PushPlus 部分渠道会截断）。"""

    print(f"📏 正文长度：{len(content)} 字符")

    if len(content) > CONTENT_LENGTH_HINT:
        print(
            f"⚠️ 正文超过 {CONTENT_LENGTH_HINT} 字符，"
            f"部分推送渠道可能截断，考虑减少新闻条数。"
        )


def send_push(content, friend_token=None, name="我"):
    """
    统一的 PushPlus 发送。

    friend_token 为 None 时发给自己（不传 "to"）。
    """

    payload = {
        "token": PUSHPLUS_TOKEN.strip(),
        "title": push_title(),
        "content": content,
        "template": "html",
        "channel": "wechat",
    }

    if friend_token:
        payload["to"] = friend_token.strip()

    print(f"📨 正在发送给：{name}")

    if friend_token:
        print(f"🔑 好友 Token 长度：{len(friend_token.strip())}")

    response = session.post(
        PUSHPLUS_URL,
        json=payload,
        timeout=30
    )

    print(f"PushPlus HTTP 状态：{response.status_code}")

    try:
        result = response.json()
    except Exception:
        print("❌ PushPlus 返回不是 JSON：")
        print(response.text)
        return False

    print(f"📡 PushPlus 返回：{result}")

    code = result.get("code")

    if code == 200:
        # data 一般是消息流水号，有它才算真的投递出去了
        message_id = result.get("data")
        print(f"✅ {name} PushPlus 接收成功，消息ID：{message_id}")
        return True

    print(
        f"❌ {name} PushPlus 业务错误："
        f"{result.get('msg')} / {result.get('data')}"
    )

    if code == 903:
        print(
            "⚠️ PushPlus Token 无效，请检查 PUSHPLUS_TOKEN "
            "是否填写为自己的 PushPlus 用户 Token。"
        )

    elif code == 905:
        print("⚠️ PushPlus 当前账号尚未完成实名认证。")

    elif code == 999:
        print(
            "⚠️ PushPlus 返回 999。请检查账号、好友 Token "
            "是否仍在“我的好友”列表中，以及公众号关注关系是否还在。"
        )

    # 推送失败时把正文打进日志，方便直接看到“生成了什么、有没有渲染出来”
    print("\n----- 未能推送的正文（HTML 源码）开始 -----")
    print(content)
    print("----- 未能推送的正文结束 -----\n")

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

    try:
        edited = ai_editor(weather, news, gold)
        print("✅ GLM 总编辑完成")

    except Exception as e:
        print(f"❌ GLM 编辑失败：{e}")
        edited = fallback_edited(weather, news, gold)

    # AI 偶尔会漏字段 / 返回空串，这里补齐
    if not str(edited.get("greeting", "") or "").strip():
        edited["greeting"] = random.choice(LAST_RESORT_GREETINGS)

    if not str(edited.get("daily_quote", "") or "").strip():
        edited["daily_quote"] = random.choice(LAST_RESORT_QUOTES)

    content = render_message(
        weather=weather,
        gold=gold,
        edited=edited,
    )

    check_content(content)

    try:
        return send_func(content)
    except Exception as e:
        # 一个人推送失败不要影响后面的人
        print(f"❌ {name} 推送异常：{e}")
        return False


def main():

    print("=" * 60)
    print(f"☀️ 每日早报开始（{CODE_VERSION}）")
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

    print(f"国内新闻：{len(news['domestic'])} 条")
    print(f"国际新闻：{len(news['international'])} 条")
    print(f"国际金价：{gold['price_usd_oz']}")

    # --------------------------------------------------------
    # 2. 处理自己
    # --------------------------------------------------------

    ok = build_and_send(
        name=MY_RECIPIENT["name"],
        city=MY_RECIPIENT["city"],
        send_func=lambda content: send_push(content, name=MY_RECIPIENT["name"]),
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
            send_func=lambda content, _token=token, _name=name: send_push(
                content,
                friend_token=_token,
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
