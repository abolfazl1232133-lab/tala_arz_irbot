import os
import re
import sqlite3
import logging
from datetime import datetime, timedelta, time

import requests
import pytz
from bs4 import BeautifulSoup

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ============================================================
# SETTINGS
# ============================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@tala_arz_irr")
DATABASE_PATH = os.environ.get("DATABASE_PATH", "market.db")

IRAN_TZ = pytz.timezone("Asia/Tehran")
TGJU = "https://www.tgju.org"

NORMAL_INTERVAL = 300       # 5 دقیقه
FRIDAY_INTERVAL = 1800      # 30 دقیقه
HOLIDAY_INTERVAL = 3600     # 1 ساعت

MARKET_START_HOUR = 7
MARKET_END_HOUR = 23

CAR_UPDATE_HOURS = (14, 20)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


# ============================================================
# TIME
# ============================================================

def iran_now():
    return datetime.now(IRAN_TZ)


def now_ts():
    return int(datetime.now().timestamp())


def date_key():
    return iran_now().strftime("%Y-%m-%d")


# ============================================================
# OFFICIAL HOLIDAYS
# ============================================================

OFFICIAL_HOLIDAYS = {
    # 1405
    "2026-03-21",
    "2026-03-22",
    "2026-03-23",
    "2026-03-24",
    "2026-03-25",
    "2026-03-26",
    "2026-04-01",
    "2026-04-02",
    "2026-04-03",
    "2026-06-03",
    "2026-06-04",
    "2026-06-05",
    "2026-06-26",
    "2026-06-27",
    "2026-07-05",
    "2026-07-06",
    "2026-07-26",
    "2026-07-27",
    "2026-08-05",
    "2026-08-06",
    "2026-08-14",
    "2026-08-15",
}


def is_official_holiday():
    return date_key() in OFFICIAL_HOLIDAYS


def market_is_open():
    now = iran_now()

    return (
        MARKET_START_HOUR
        <= now.hour
        < MARKET_END_HOUR
    )


def current_update_interval():

    if is_official_holiday():
        return HOLIDAY_INTERVAL

    if iran_now().weekday() == 4:
        return FRIDAY_INTERVAL

    return NORMAL_INTERVAL


# ============================================================
# DATABASE
# ============================================================

def db():

    conn = sqlite3.connect(
        DATABASE_PATH,
        timeout=30
    )

    conn.row_factory = sqlite3.Row

    return conn


def init_db():

    with db() as c:

        c.execute("""
            CREATE TABLE IF NOT EXISTS prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                key TEXT NOT NULL,
                price REAL NOT NULL
            )
        """)

        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_prices_key_ts
            ON prices(key, ts)
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                key TEXT NOT NULL,
                direction TEXT NOT NULL,
                target REAL NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL
            )
        """)

        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_alerts_active
            ON alerts(active)
        """)


def set_setting(key, value):

    with db() as c:

        c.execute(
            """
            INSERT INTO settings(key,value)
            VALUES(?,?)
            ON CONFLICT(key)
            DO UPDATE SET value=excluded.value
            """,
            (key, str(value))
        )


def get_setting(key):

    with db() as c:

        row = c.execute(
            """
            SELECT value
            FROM settings
            WHERE key=?
            """,
            (key,)
        ).fetchone()

    return row["value"] if row else None


# ============================================================
# HISTORY
# ============================================================

def save_snapshot(prices):

    ts = now_ts()

    with db() as c:

        for key, value in prices.items():

            if value is not None and value > 0:

                c.execute(
                    """
                    INSERT INTO prices(ts,key,price)
                    VALUES(?,?,?)
                    """,
                    (ts, key, value)
                )

        cutoff = ts - (8 * 86400)

        c.execute(
            "DELETE FROM prices WHERE ts < ?",
            (cutoff,)
        )


def price_at_or_before(key, target_ts):

    with db() as c:

        row = c.execute(
            """
            SELECT price
            FROM prices
            WHERE key=?
            AND ts<=?
            ORDER BY ts DESC
            LIMIT 1
            """,
            (key, target_ts)
        ).fetchone()

    if row:
        return float(row["price"])

    return None


def pct_change(current, old):

    if current is None or old is None or old == 0:
        return None

    return ((current - old) / old) * 100


# ============================================================
# NUMBER HELPERS
# ============================================================

def normalize_digits(text):

    if not text:
        return ""

    trans = str.maketrans(
        "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
        "01234567890123456789"
    )

    return str(text).translate(trans)


def extract_first_number(text):

    if not text:
        return None

    text = normalize_digits(text)

    text = (
        text
        .replace(",", "")
        .replace("٬", "")
        .replace(" ", "")
    )

    match = re.search(
        r"\d+(?:\.\d+)?",
        text
    )

    if not match:
        return None

    try:
        return float(match.group())
    except Exception:
        return None


def fmt_num(value, decimals=0):

    if value is None:
        return "---"

    if decimals:
        return f"{value:,.{decimals}f}"

    return f"{value:,.0f}"


# ============================================================
# HTTP
# ============================================================

def fetch_html(url):

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=25
    )

    response.raise_for_status()

    return response.text


# ============================================================
# TGJU PROFILE
# ============================================================

def profile_current(path):

    html = fetch_html(
        TGJU + path
    )

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    text = soup.get_text(
        " ",
        strip=True
    )

    patterns = [

        r"نرخ فعلی\s*[:：]?\s*([\d,٬.]+)",

        r"قیمت فعلی\s*[:：]?\s*([\d,٬.]+)",

    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text
        )

        if match:

            value = extract_first_number(
                match.group(1)
            )

            if value is not None:
                return value

    # fallback:
    # اگر متن با الگوی بالا جور نشد، از ساختار
    # صفحه TGJU مقدار بعد از «نرخ فعلی» را پیدا کن.

    marker = text.find("نرخ فعلی")

    if marker >= 0:

        fragment = text[
            marker:
            marker + 150
        ]

        value = extract_first_number(
            fragment
        )

        if value is not None:
            return value

    return None


def safe_profile(path, name):

    try:

        value = profile_current(
            path
        )

        logger.info(
            "%s = %s",
            name,
            value
        )

        return value

    except Exception as e:

        logger.error(
            "%s failed: %s",
            name,
            e
        )

        return None


# ============================================================
# MARKET DATA
# ============================================================

def fetch_prices():

    prices = {}

    sources = {

        "gold_18": (
            "/profile/geram18",
            10
        ),

        "gold_24": (
            "/profile/geram24",
            10
        ),

        "mesghal": (
            "/profile/mesghal",
            10
        ),

        "ounce": (
            "/profile/ons",
            1
        ),

        "usd": (
            "/profile/price_dollar_rl",
            10
        ),

        "eur": (
            "/profile/price_eur",
            10
        ),

        "gbp": (
            "/profile/price_gbp",
            10
        ),

        "coin_emami": (
            "/profile/sekee",
            10
        ),

        "coin_half": (
            "/profile/nim",
            10
        ),

        # نفت برنت
        "brent": (
            "/profile/energy-brent-oil",
            1
        ),
    }

    for key, (path, divisor) in sources.items():

        raw = safe_profile(
            path,
            key
        )

        if raw is not None:
            prices[key] = raw / divisor
        else:
            prices[key] = None

    # --------------------------------------------------------
    # AB SHODE
    # --------------------------------------------------------

    prices["abshode"] = None

    try:

        html = fetch_html(
            TGJU + "/gold-chart"
        )

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        wanted = (
            "آبشده نقدی",
            "آبشده نقدى",
        )

        for row in soup.find_all("tr"):

            cells = row.find_all(
                ["td", "th"]
            )

            if len(cells) < 2:
                continue

            label = cells[0].get_text(
                " ",
                strip=True
            )

            label = (
                label
                .replace("ي", "ی")
                .replace("ك", "ک")
            )

            if any(
                x in label
                for x in wanted
            ):

                for cell in cells[1:]:

                    value = extract_first_number(
                        cell.get_text(
                            " ",
                            strip=True
                        )
                    )

                    if value and value > 0:

                        prices["abshode"] = (
                            value / 10
                        )

                        break

            if prices["abshode"]:
                break

    except Exception as e:

        logger.error(
            "Abshode failed: %s",
            e
        )


    # --------------------------------------------------------
    # CRYPTO
    # --------------------------------------------------------

    crypto_map = {

        "btc": [
            "بیت کوین",
            "bitcoin"
        ],

        "eth": [
            "اتریوم",
            "ethereum"
        ],

        "sol": [
            "سولانا",
            "solana"
        ],

        "bnb": [
            "بایننس کوین",
            "bnb"
        ],

        "xrp": [
            "ریپل",
            "ripple"
        ],

        "usdt": [
            "تتر",
            "tether"
        ],
    }

    for key in crypto_map:
        prices[key] = None

    try:

        html = fetch_html(
            TGJU + "/crypto"
        )

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        for key, names in crypto_map.items():

            for row in soup.find_all("tr"):

                cells = row.find_all(
                    ["td", "th"]
                )

                if len(cells) < 2:
                    continue

                row_text = row.get_text(
                    " ",
                    strip=True
                ).lower()

                if not any(
                    name.lower() in row_text
                    for name in names
                ):
                    continue

                for cell in cells[1:]:

                    value = extract_first_number(
                        cell.get_text(
                            " ",
                            strip=True
                        )
                    )

                    if value and value > 0:

                        prices[key] = value
                        break

                if prices[key] is not None:
                    break

    except Exception as e:

        logger.error(
            "Crypto failed: %s",
            e
        )

    # تتر تومانی
    prices["usdt_toman"] = prices.get("usd")

    return prices


# ============================================================
# CARS
# ============================================================

CAR_SOURCES = {

    "peugeot_206": (
        "پژو ۲۰۶",
        "/profile/%D9%BE%DA%98%D9%88-206-%D8%AA%DB%8C%D9%BE-2-%DA%A9%D8%AF-26028",
        10
    ),

    "peugeot_207": (
        "پژو ۲۰۷",
        "/profile/%D9%BE%DA%98%D9%88-207-%D8%AC%D8%AF%DB%8C%D8%AF",
        10
    ),

    "dena": (
        "دنا",
        "/profile/%D8%AF%D9%86%D8%A7-%D8%AA%DB%8C%D9%BE-1",
        10
    ),

}


CAR_NAMES = {

    "peugeot_206": "پژو ۲۰۶",

    "peugeot_207": "پژو ۲۰۷",

    "dena": "دنا",

}


def car_profile_price(path):

    try:

        html = fetch_html(
            TGJU + path
        )

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        text = soup.get_text(
            " ",
            strip=True
        )

        # نرخ فعلی
        patterns = [

            r"نرخ فعلی\s*[:：]?\s*([\d,٬.]+)",

            r"قیمت فعلی\s*[:：]?\s*([\d,٬.]+)",

        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                text
            )

            if match:

                value = extract_first_number(
                    match.group(1)
                )

                if value:
                    return value / 10

        # fallback
        marker = text.find("نرخ فعلی")

        if marker >= 0:

            fragment = text[
                marker:
                marker + 200
            ]

            value = extract_first_number(
                fragment
            )

            if value:
                return value / 10

    except Exception as e:

        logger.error(
            "Car profile failed: %s",
            e
        )

    return None


def fetch_car_prices():

    cars = {}

    for key, (
        name,
        path,
        divisor
    ) in CAR_SOURCES.items():

        try:

            html = fetch_html(
                TGJU + path
            )

            soup = BeautifulSoup(
                html,
                "html.parser"
            )

            text = soup.get_text(
                " ",
                strip=True
            )

            value = None

            patterns = [

                r"نرخ فعلی\s*[:：]?\s*([\d,٬.]+)",

                r"قیمت فعلی\s*[:：]?\s*([\d,٬.]+)",

            ]

            for pattern in patterns:

                match = re.search(
                    pattern,
                    text
                )

                if match:

                    value = extract_first_number(
                        match.group(1)
                    )

                    if value:
                        break

            if value:

                cars[key] = value / divisor

            else:

                cars[key] = None

            logger.info(
                "CAR %s = %s",
                name,
                cars[key]
            )

        except Exception as e:

            logger.error(
                "CAR %s failed: %s",
                name,
                e
            )

            cars[key] = None

    return cars


def cars_message(cars):

    now = iran_now()

    lines = [

        "🚗 *قیمت خودرو*",

        (
            f"🕐 آخرین به‌روزرسانی: "
            f"`{now.strftime('%Y/%m/%d - %H:%M')}`"
        ),

        "",

    ]

    for key in CAR_SOURCES:

        name = CAR_NAMES[key]

        value = cars.get(key)

        if value is None:

            lines.append(
                f"• {name}: `---` تومان"
            )

        else:

            lines.append(
                f"• {name}: "
                f"`{fmt_num(value)}` تومان"
            )

    lines += [

        "",

        "منبع: TGJU",

        "━━━━━━━━━━━━━━━━━━",

        "🤖 @tala\\_arz\\_irr",
    ]

    return "\n".join(lines)


# ============================================================
# DISPLAY NAMES
# ============================================================

NAMES = {

    "gold_18": (
        "طلای ۱۸ عیار",
        "تومان",
        0
    ),

    "gold_24": (
        "طلای ۲۴ عیار",
        "تومان",
        0
    ),

    "abshode": (
        "طلای آبشده",
        "تومان",
        0
    ),

    "mesghal": (
        "مثقال طلا",
        "تومان",
        0
    ),

    "ounce": (
        "اونس جهانی طلا",
        "دلار",
        2
    ),

    "coin_emami": (
        "سکه امامی",
        "تومان",
        0
    ),

    "coin_half": (
        "نیم‌سکه",
        "تومان",
        0
    ),

    "usd": (
        "دلار آمریکا",
        "تومان",
        0
    ),

    "eur": (
        "یورو",
        "تومان",
        0
    ),

    "gbp": (
        "پوند انگلیس",
        "تومان",
        0
    ),

    "btc": (
        "بیت‌کوین",
        "دلار",
        2
    ),

    "eth": (
        "اتریوم",
        "دلار",
        2
    ),

    "sol": (
        "سولانا",
        "دلار",
        2
    ),

    "bnb": (
        "BNB",
        "دلار",
        2
    ),

    "xrp": (
        "XRP",
        "دلار",
        4
    ),

    "usdt_toman": (
        "تتر",
        "تومان",
        0
    ),

    "brent": (
        "نفت برنت",
        "دلار",
        2
    ),
}


# ============================================================
# PERCENT
# ============================================================

def arrow_pct(value):

    if value is None:
        return "▫️ ---"

    if value > 0:
        return f"📈 +{value:.2f}%"

    if value < 0:
        return f"📉 {value:.2f}%"

    return "➖ 0.00%"


# ============================================================
# LIVE LINE
# ============================================================

def line_for(
    key,
    prices,
    old5,
    old60,
    show_changes=True
):

    label, unit, decimals = NAMES[key]

    value = prices.get(key)

    if value is None:

        return (
            f"• {label}: "
            f"`---` {unit}"
        )

    line = (
        f"• {label}: "
        f"`{fmt_num(value, decimals)}` "
        f"{unit}"
    )

    if show_changes:

        change5 = pct_change(
            value,
            old5
        )

        change60 = pct_change(
            value,
            old60
        )

        line += (
            f"\n  ├ ۵ دقیقه: "
            f"{arrow_pct(change5)}"
        )

        line += (
            f"\n  └ ۱ ساعت: "
            f"{arrow_pct(change60)}"
        )

    return line


# ============================================================
# LIVE MESSAGE
# ============================================================

def live_message(prices):

    now = iran_now()
    ts = now_ts()

    lines = [

        "📊 *قیمت‌های لحظه‌ای بازار*",

        (
            f"🕐 آخرین به‌روزرسانی: "
            f"`{now.strftime('%Y/%m/%d - %H:%M')}`"
        ),

        "",
        "━━━━━━━━━━━━━━━━━━",
        "🥇 *فلزات گرانبها*",
    ]

    for key in (
        "gold_18",
        "gold_24",
        "abshode",
        "mesghal",
        "ounce"
    ):

        lines.append(
            line_for(
                key,
                prices,
                price_at_or_before(
                    key,
                    ts - 300
                ),
                price_at_or_before(
                    key,
                    ts - 3600
                )
            )
        )

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━",
        "🪙 *سکه*",
    ]

    for key in (
        "coin_emami",
        "coin_half"
    ):

        lines.append(
            line_for(
                key,
                prices,
                price_at_or_before(
                    key,
                    ts - 300
                ),
                price_at_or_before(
                    key,
                    ts - 3600
                )
            )
        )

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━",
        "💵 *ارز*",
    ]

    for key in (
        "usd",
        "eur",
        "gbp"
    ):

        lines.append(
            line_for(
                key,
                prices,
                price_at_or_before(
                    key,
                    ts - 300
                ),
                price_at_or_before(
                    key,
                    ts - 3600
                )
            )
        )

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━",
        "💰 *ارز دیجیتال*",
    ]

    for key in (
        "btc",
        "eth",
        "sol",
        "bnb",
        "xrp",
        "usdt_toman"
    ):

        lines.append(
            line_for(
                key,
                prices,
                price_at_or_before(
                    key,
                    ts - 300
                ),
                price_at_or_before(
                    key,
                    ts - 3600
                )
            )
        )

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━",
        "🛢️ *انرژی*",
    ]

    lines.append(
        line_for(
            "brent",
            prices,
            price_at_or_before(
                "brent",
                ts - 300
            ),
            price_at_or_before(
                "brent",
                ts - 3600
            )
        )
    )

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━",
        "🤖 @tala\\_arz\\_irr",
    ]

    return "\n".join(lines)


# ============================================================
# HOURLY SUMMARY
# ============================================================

def hourly_summary(prices):

    now = iran_now()

    target_ts = now_ts() - 3600

    lines = [

        "📌 *جمع‌بندی یک ساعت گذشته بازار*",

        (
            f"🕐 "
            f"{(now - timedelta(hours=1)).strftime('%H:%M')}"
            f" تا "
            f"{now.strftime('%H:%M')}"
        ),

        "",
    ]

    groups = [

        (
            "🥇 طلا و سکه",
            (
                "gold_18",
                "gold_24",
                "abshode",
                "mesghal",
                "coin_emami",
                "coin_half",
            )
        ),

        (
            "💵 ارز",
            (
                "usd",
                "eur",
                "gbp",
            )
        ),

        (
            "💰 کریپتو",
            (
                "btc",
                "eth",
                "sol",
                "bnb",
                "xrp",
                "usdt_toman",
            )
        ),

        (
            "🛢️ انرژی",
            (
                "brent",
            )
        ),
    ]

    for title, group in groups:

        lines.append(
            f"*{title}*"
        )

        for key in group:

            label, unit, decimals = NAMES[key]

            current = prices.get(key)

            old = price_at_or_before(
                key,
                target_ts
            )

            if current is None:
                continue

            change = pct_change(
                current,
                old
            )

            lines.append(
                f"• {label}: "
                f"`{fmt_num(current, decimals)}` "
                f"{unit} "
                f"{arrow_pct(change)}"
            )

        lines.append("")

    lines += [
        "━━━━━━━━━━━━━━━━━━",
        "🤖 @tala\\_arz\\_irr",
    ]

    return "\n".join(lines)


# ============================================================
# DAILY SUMMARY
# ============================================================

def daily_summary(prices):

    now = iran_now()

    target_ts = now_ts() - 86400

    lines = [

        (
            f"📰 *خلاصه روزانه بازار | "
            f"{now.strftime('%Y/%m/%d')}*"
        ),

        "",
    ]

    candidates = []

    for key in NAMES:

        value = prices.get(key)

        old = price_at_or_before(
            key,
            target_ts
        )

        if value is not None and old is not None:

            change = pct_change(
                value,
                old
            )

            if change is not None:

                candidates.append(
                    (key, change)
                )

    candidates.sort(
        key=lambda x: x[1],
        reverse=True
    )

    if candidates:

        lines.append(
            "📈 *بیشترین رشد ۲۴ ساعت اخیر*"
        )

        for key, change in candidates[:3]:

            lines.append(
                f"• {NAMES[key][0]}: "
                f"{arrow_pct(change)}"
            )

        lines.append("")

        lines.append(
            "📉 *بیشترین افت ۲۴ ساعت اخیر*"
        )

        for key, change in candidates[-3:]:

            lines.append(
                f"• {NAMES[key][0]}: "
                f"{arrow_pct(change)}"
            )

    else:

        lines.append(
            "هنوز داده کافی برای مقایسه "
            "۲۴ ساعته وجود ندارد."
        )

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━",
        "🤖 @tala\\_arz\\_irr",
    ]

    return "\n".join(lines)


# ============================================================
# ALERTS
# ============================================================

KEY_ALIASES = {

    "طلا": "gold_18",
    "طلای18": "gold_18",
    "طلای۱۸": "gold_18",

    "دلار": "usd",
    "یورو": "eur",
    "پوند": "gbp",

    "بیتکوین": "btc",
    "بیت‌کوین": "btc",

    "اتریوم": "eth",
    "سولانا": "sol",

    "bnb": "bnb",
    "xrp": "xrp",

    "تتر": "usdt_toman",

    "نفت": "brent",
    "برنت": "brent",
}


def parse_alert(text):

    parts = text.strip().split()

    if len(parts) < 4:
        return None

    asset = parts[1].replace(" ", "")

    direction_word = parts[2].lower()

    try:

        target = float(
            parts[3]
            .replace(",", "")
            .replace("٬", "")
        )

    except ValueError:

        return None

    key = KEY_ALIASES.get(asset)

    if not key:
        return None

    if direction_word in (
        "بالای",
        "بیشتر"
    ):

        direction = "above"

    elif direction_word in (
        "زیر",
        "کمتر"
    ):

        direction = "below"

    else:

        return None

    return key, direction, target


async def alert_command(update, context):

    parsed = parse_alert(
        update.message.text or ""
    )

    if not parsed:

        await update.message.reply_text(
            "فرمت درست:\n\n"
            "/alert طلا بالای 22000000\n"
            "/alert دلار زیر 205000\n"
            "/alert نفت بالای 100"
        )

        return

    key, direction, target = parsed

    with db() as c:

        c.execute(
            """
            INSERT INTO alerts(
                user_id,
                key,
                direction,
                target,
                created_at
            )
            VALUES(?,?,?,?,?)
            """,
            (
                update.effective_user.id,
                key,
                direction,
                target,
                now_ts()
            )
        )

    direction_text = (
        "بالاتر از"
        if direction == "above"
        else
        "پایین‌تر از"
    )

    await update.message.reply_text(

        f"🔔 هشدار ثبت شد.\n\n"
        f"{NAMES[key][0]} "
        f"{direction_text} "
        f"`{fmt_num(target, NAMES[key][2])}`",

        parse_mode=ParseMode.MARKDOWN
    )


async def alerts_command(update, context):

    with db() as c:

        rows = c.execute(
            """
            SELECT id,key,direction,target
            FROM alerts
            WHERE user_id=?
            AND active=1
            ORDER BY id DESC
            """,
            (
                update.effective_user.id,
            )
        ).fetchall()

    if not rows:

        await update.message.reply_text(
            "🔔 هشدار فعالی نداری."
        )

        return

    lines = [
        "🔔 *هشدارهای فعال:*",
        "",
    ]

    for row in rows:

        word = (
            "بالای"
            if row["direction"] == "above"
            else
            "زیر"
        )

        lines.append(
            f"#{row['id']} • "
            f"{NAMES[row['key']][0]} "
            f"{word} "
            f"`{fmt_num(row['target'], NAMES[row['key']][2])}`"
        )

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN
    )


async def cancel_alert_command(update, context):

    parts = (
        update.message.text or ""
    ).split()

    if (
        len(parts) != 2
        or not parts[1].isdigit()
    ):

        await update.message.reply_text(
            "مثال:\n/cancelalert 12"
        )

        return

    alert_id = int(parts[1])

    with db() as c:

        c.execute(
            """
            UPDATE alerts
            SET active=0
            WHERE id=?
            AND user_id=?
            """,
            (
                alert_id,
                update.effective_user.id
            )
        )

    await update.message.reply_text(
        "✅ هشدار غیرفعال شد."
    )


async def check_alerts(context):

    prices = context.application.bot_data.get(
        "latest_prices",
        {}
    )

    if not prices:
        return

    with db() as c:

        rows = c.execute(
            """
            SELECT id,user_id,key,direction,target
            FROM alerts
            WHERE active=1
            """
        ).fetchall()

        for row in rows:

            value = prices.get(
                row["key"]
            )

            if value is None:
                continue

            if row["direction"] == "above":
                hit = value >= row["target"]
            else:
                hit = value <= row["target"]

            if not hit:
                continue

            try:

                await context.bot.send_message(

                    chat_id=row["user_id"],

                    text=(
                        "🔔 *هشدار قیمت*\n\n"
                        f"{NAMES[row['key']][0]} "
                        f"به محدوده تعیین‌شده رسید.\n\n"
                        f"قیمت فعلی: "
                        f"`{fmt_num(value, NAMES[row['key']][2])}` "
                        f"{NAMES[row['key']][1]}"
                    ),

                    parse_mode=ParseMode.MARKDOWN
                )

                c.execute(
                    """
                    UPDATE alerts
                    SET active=0
                    WHERE id=?
                    """,
                    (row["id"],)
                )

            except Exception as e:

                logger.error(
                    "Alert send failed: %s",
                    e
                )


# ============================================================
# CHART
# ============================================================

def chart_data(key, hours=24):

    since = now_ts() - (
        hours * 3600
    )

    with db() as c:

        rows = c.execute(
            """
            SELECT ts,price
            FROM prices
            WHERE key=?
            AND ts>=?
            ORDER BY ts ASC
            """,
            (key, since)
        ).fetchall()

    return [
        (
            datetime.fromtimestamp(
                row["ts"],
                IRAN_TZ
            ),
            row["price"]
        )
        for row in rows
    ]


def create_chart(key, hours=24):

    import matplotlib

    matplotlib.use("Agg")

    import matplotlib.pyplot as plt

    data = chart_data(
        key,
        hours
    )

    if len(data) < 2:
        return None

    x = [item[0] for item in data]
    y = [item[1] for item in data]

    label = NAMES[key][0]

    fig = plt.figure(
        figsize=(10, 5)
    )

    ax = fig.add_subplot(111)

    ax.plot(x, y)

    ax.set_title(
        f"{label} - {hours} ساعت گذشته"
    )

    ax.set_xlabel(
        "Time"
    )

    ax.set_ylabel(
        NAMES[key][1]
    )

    ax.grid(
        True,
        alpha=0.25
    )

    fig.autofmt_xdate()

    filename = (
        f"chart_{key}_{hours}.png"
    )

    path = os.path.join(
        "/tmp",
        filename
    )

    fig.tight_layout()

    fig.savefig(
        path,
        dpi=150
    )

    plt.close(fig)

    return path


# ============================================================
# KEYBOARD
# ============================================================

def keyboard():

    return InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "📊 همه قیمت‌ها",
                callback_data="all"
            )
        ],

        [
            InlineKeyboardButton(
                "🥇 طلا و سکه",
                callback_data="gold"
            ),

            InlineKeyboardButton(
                "💰 کریپتو",
                callback_data="crypto"
            ),
        ],

        [
            InlineKeyboardButton(
                "💵 ارز",
                callback_data="fx"
            ),

            InlineKeyboardButton(
                "🛢️ نفت",
                callback_data="oil"
            ),
        ],

        [
            InlineKeyboardButton(
                "🚗 خودرو",
                callback_data="cars"
            ),

            InlineKeyboardButton(
                "📈 نمودار",
                callback_data="chart_help"
            ),
        ],

        [
            InlineKeyboardButton(
                "🔔 هشدارها",
                callback_data="alert_help"
            ),
        ],
    ])


# ============================================================
# START
# ============================================================

async def start(update, context):

    await update.message.reply_text(

        "سلام 👋\n\n"

        "به ربات قیمت طلا، ارز و بازار خوش اومدی.\n\n"

        "📊 قیمت‌های بازار\n"
        "🥇 طلا و سکه\n"
        "💵 ارزهای خارجی\n"
        "💰 ارز دیجیتال\n"
        "🛢️ نفت\n"
        "🚗 خودرو\n"
        "📈 نمودار\n"
        "🔔 هشدار قیمت",

        reply_markup=keyboard()
    )


# ============================================================
# PRICE COMMAND
# ============================================================

async def price_command(update, context):

    prices = (
        context.application.bot_data.get(
            "latest_prices"
        )
        or fetch_prices()
    )

    await update.message.reply_text(

        live_message(prices),

        parse_mode=ParseMode.MARKDOWN
    )


# ============================================================
# BUTTON HANDLER
# ============================================================

async def button_handler(update, context):

    query = update.callback_query

    await query.answer()

    prices = (
        context.application.bot_data.get(
            "latest_prices"
        )
        or fetch_prices()
    )

    if query.data == "all":

        text = live_message(prices)

    elif query.data == "gold":

        keys = (
            "gold_18",
            "gold_24",
            "abshode",
            "mesghal",
            "ounce",
            "coin_emami",
            "coin_half",
        )

        lines = [
            "🥇 *طلا و سکه*",
            "",
        ]

        for key in keys:

            label, unit, decimals = NAMES[key]

            lines.append(
                f"• {label}: "
                f"`{fmt_num(prices.get(key), decimals)}` "
                f"{unit}"
            )

        text = "\n".join(lines)

    elif query.data == "crypto":

        keys = (
            "btc",
            "eth",
            "sol",
            "bnb",
            "xrp",
            "usdt_toman",
        )

        lines = [
            "💰 *ارز دیجیتال*",
            "",
        ]

        for key in keys:

            label, unit, decimals = NAMES[key]

            lines.append(
                f"• {label}: "
                f"`{fmt_num(prices.get(key), decimals)}` "
                f"{unit}"
            )

        text = "\n".join(lines)

    elif query.data == "fx":

        keys = (
            "usd",
            "eur",
            "gbp",
        )

        lines = [
            "💵 *ارزهای خارجی*",
            "",
        ]

        for key in keys:

            label, unit, decimals = NAMES[key]

            lines.append(
                f"• {label}: "
                f"`{fmt_num(prices.get(key), decimals)}` "
                f"{unit}"
            )

        text = "\n".join(lines)

    elif query.data == "oil":

        value = prices.get("brent")

        text = (
            "🛢️ *نفت برنت*\n\n"
            f"`{fmt_num(value, 2)}` دلار"
        )

    elif query.data == "cars":

        cars = fetch_car_prices()

        text = cars_message(
            cars
        )

    elif query.data == "alert_help":

        text = (

            "🔔 *ساخت هشدار*\n\n"

            "`/alert طلا بالای 22000000`\n"
            "`/alert دلار زیر 205000`\n"
            "`/alert نفت بالای 100`\n\n"

            "`/alerts` = هشدارهای فعال\n"
            "`/cancelalert 12` = حذف هشدار"

        )

    else:

        text = (

            "📈 *نمودار قیمت*\n\n"

            "برای رسم نمودار، مثلاً:\n\n"

            "`/chart طلا`\n"
            "`/chart دلار`\n"
            "`/chart نفت`\n\n"

            "نمودار بر اساس تاریخچه‌ای که "
            "ربات در دیتابیس ذخیره کرده ساخته می‌شود."

        )

    await query.edit_message_text(

        text,

        parse_mode=ParseMode.MARKDOWN,

        reply_markup=keyboard()
    )


# ============================================================
# CHART COMMAND
# ============================================================

async def chart_command(update, context):

    text = (
        update.message.text or ""
    )

    parts = text.split()

    if len(parts) < 2:

        await update.message.reply_text(
            "مثال:\n"
            "/chart طلا\n"
            "/chart دلار\n"
            "/chart نفت"
        )

        return

    asset = parts[1].replace(
        " ",
        ""
    )

    key = KEY_ALIASES.get(
        asset
    )

    if key is None:

        await update.message.reply_text(
            "دارایی شناخته نشد."
        )

        return

    path = create_chart(
        key,
        24
    )

    if not path:

        await update.message.reply_text(
            "هنوز داده کافی برای رسم نمودار وجود ندارد."
        )

        return

    with open(path, "rb") as photo:

        await update.message.reply_photo(
            photo=photo,
            caption=(
                f"📈 نمودار {NAMES[key][0]} "
                f"در ۲۴ ساعت گذشته"
            )
        )

    try:
        os.remove(path)
    except Exception:
        pass


# ============================================================
# LIVE MESSAGE CREATION
# ============================================================

async def create_new_live_message(
    context,
    prices
):

    sent = await context.bot.send_message(

        chat_id=CHANNEL_ID,

        text=live_message(prices),

        parse_mode=ParseMode.MARKDOWN
    )

    set_setting(
        "live_message_id",
        sent.message_id
    )

    context.application.bot_data[
        "live_message_id"
    ] = sent.message_id

    return sent.message_id


# ============================================================
# UPDATE LIVE
# ============================================================

async def update_live_channel(
    context,
    force_new=False
):

    if not market_is_open():
        return False

    try:

        prices = fetch_prices()

        valid_prices = [
            x
            for x in prices.values()
            if x is not None
            and x > 0
        ]

        if not valid_prices:

            logger.warning(
                "No valid prices."
            )

            return False

        context.application.bot_data[
            "latest_prices"
        ] = prices

        save_snapshot(
            prices
        )

        text = live_message(
            prices
        )

        if force_new:

            await create_new_live_message(
                context,
                prices
            )

        else:

            message_id = (
                context.application.bot_data.get(
                    "live_message_id"
                )
                or
                get_setting(
                    "live_message_id"
                )
            )

            if message_id:

                try:

                    await context.bot.edit_message_text(

                        chat_id=CHANNEL_ID,

                        message_id=int(message_id),

                        text=text,

                        parse_mode=ParseMode.MARKDOWN

                    )

                except Exception as e:

                    logger.warning(
                        "Edit failed: %s",
                        e
                    )

                    await create_new_live_message(
                        context,
                        prices
                    )

            else:

                await create_new_live_message(
                    context,
                    prices
                )

        await check_alerts(
            context
        )

        return True

    except Exception as e:

        logger.exception(
            "Live update failed"
        )

        return False


# ============================================================
# SCHEDULED MARKET UPDATE
# ============================================================

async def scheduled_market_update(context):

    if not market_is_open():
        return

    interval = current_update_interval()

    current_ts = now_ts()

    last_ts = context.application.bot_data.get(
        "last_market_update_ts",
        0
    )

    if current_ts - last_ts < interval:
        return

    success = await update_live_channel(
        context
    )

    if success:

        context.application.bot_data[
            "last_market_update_ts"
        ] = current_ts


# ============================================================
# HOURLY SUMMARY
# ============================================================

async def hourly_job(context):

    if not market_is_open():
        return

    try:

        prices = (
            context.application.bot_data.get(
                "latest_prices"
            )
            or fetch_prices()
        )

        # اول جمع‌بندی
        await context.bot.send_message(

            chat_id=CHANNEL_ID,

            text=hourly_summary(
                prices
            ),

            parse_mode=ParseMode.MARKDOWN
        )

        # سپس پیام قیمت جدید
        success = await update_live_channel(
            context,
            force_new=True
        )

        if success:

            context.application.bot_data[
                "last_market_update_ts"
            ] = now_ts()

    except Exception:

        logger.exception(
            "Hourly job failed"
        )


# ============================================================
# CAR JOB
# ============================================================

async def car_job(context):

    now = iran_now()

    if now.hour not in CAR_UPDATE_HOURS:
        return

    if now.minute != 0:
        return

    if is_official_holiday():
        return

    if now.weekday() == 4:
        return

    date_hour_key = (
        f"{now.strftime('%Y-%m-%d')}_"
        f"{now.hour}"
    )

    last_car_job = context.application.bot_data.get(
        "last_car_job"
    )

    if last_car_job == date_hour_key:
        return

    cars = fetch_car_prices()

    valid = [
        value
        for value in cars.values()
        if value is not None
        and value > 0
    ]

    if not valid:
        logger.warning(
            "Car update returned no valid data."
        )
        return

    context.application.bot_data[
        "latest_cars"
    ] = cars

    await context.bot.send_message(

        chat_id=CHANNEL_ID,

        text=cars_message(cars),

        parse_mode=ParseMode.MARKDOWN
    )

    context.application.bot_data[
        "last_car_job"
    ] = date_hour_key

    logger.info(
        "Car prices updated at %s",
        now.strftime("%H:%M")
    )


# ============================================================
# DAILY SUMMARY
# ============================================================

async def daily_job(context):

    if not market_is_open():
        return

    try:

        prices = (
            context.application.bot_data.get(
                "latest_prices"
            )
            or fetch_prices()
        )

        await context.bot.send_message(

            chat_id=CHANNEL_ID,

            text=daily_summary(prices),

            parse_mode=ParseMode.MARKDOWN
        )

        await update_live_channel(
            context,
            force_new=True
        )

    except Exception:

        logger.exception(
            "Daily job failed"
        )


# ============================================================
# MAIN
# ============================================================

def main():

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN environment variable is missing."
        )

    init_db()

    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    # Commands

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        CommandHandler(
            "price",
            price_command
        )
    )

    app.add_handler(
        CommandHandler(
            "alert",
            alert_command
        )
    )

    app.add_handler(
        CommandHandler(
            "alerts",
            alerts_command
        )
    )

    app.add_handler(
        CommandHandler(
            "cancelalert",
            cancel_alert_command
        )
    )

    app.add_handler(
        CommandHandler(
            "chart",
            chart_command
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            button_handler
        )
    )

    # --------------------------------------------------------
    # MARKET
    # --------------------------------------------------------

    app.job_queue.run_repeating(
        scheduled_market_update,
        interval=60,
        first=5
    )

    # --------------------------------------------------------
    # HOURLY SUMMARY
    # --------------------------------------------------------

    app.job_queue.run_repeating(
        hourly_job,
        interval=3600,
        first=3600
    )

    # --------------------------------------------------------
    # CAR
    # هر دقیقه بررسی می‌کند،
    # اما فقط در 14:00 و 20:00 اجرا می‌شود.
    # --------------------------------------------------------

    app.job_queue.run_repeating(
        car_job,
        interval=60,
        first=10
    )

    # --------------------------------------------------------
    # DAILY
    # --------------------------------------------------------

    app.job_queue.run_daily(
        daily_job,
        time=time(
            hour=22,
            minute=55,
            tzinfo=IRAN_TZ
        ),
        days=tuple(range(7))
    )

    logger.info(
        "Tala Arz Bot started."
    )

    logger.info(
        "Normal update = 5 minutes"
    )

    logger.info(
        "Friday update = 30 minutes"
    )

    logger.info(
        "Holiday update = 60 minutes"
    )

    logger.info(
        "Car updates = 14:00 and 20:00"
    )

    logger.info(
        "Market hours = 07:00 - 23:00"
    )

    app.run_polling()


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()