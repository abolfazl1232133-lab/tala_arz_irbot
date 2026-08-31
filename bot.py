import os
import re
import sqlite3
import logging
from datetime import datetime

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
CHANNEL_ID = os.environ.get(
    "CHANNEL_ID",
    "@tala_arz_irr"
)

DATABASE_PATH = os.environ.get(
    "DATABASE_PATH",
    "market.db"
)

TGJU = "https://www.tgju.org"

IRAN_TZ = pytz.timezone(
    "Asia/Tehran"
)

NORMAL_INTERVAL = 300      # 5 minutes
FRIDAY_INTERVAL = 900      # 15 minutes

MARKET_START_HOUR = 7
MARKET_END_HOUR = 23

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept-Language": (
        "fa-IR,fa;q=0.9,en;q=0.8"
    ),
}

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s - "
        "%(name)s - "
        "%(levelname)s - "
        "%(message)s"
    ),
)

logger = logging.getLogger(
    __name__
)


# ============================================================
# TIME
# ============================================================

def iran_now():
    return datetime.now(
        IRAN_TZ
    )


def unix_now():
    return int(
        datetime.now().timestamp()
    )


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
            CREATE INDEX IF NOT EXISTS
            idx_prices_key_ts
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
            CREATE INDEX IF NOT EXISTS
            idx_alerts_active
            ON alerts(active)
        """)


def set_setting(
    key,
    value
):

    with db() as c:

        c.execute(
            """
            INSERT INTO settings(key, value)
            VALUES(?, ?)
            ON CONFLICT(key)
            DO UPDATE SET value=excluded.value
            """,
            (
                key,
                str(value)
            )
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

    if row:
        return row["value"]

    return None


def save_snapshot(prices):

    ts = unix_now()

    with db() as c:

        for key, value in prices.items():

            if (
                value is not None
                and value > 0
            ):

                c.execute(
                    """
                    INSERT INTO prices(
                        ts,
                        key,
                        price
                    )
                    VALUES(?, ?, ?)
                    """,
                    (
                        ts,
                        key,
                        value
                    )
                )

        # نگهداری 8 روز تاریخچه
        cutoff = ts - (
            8 * 86400
        )

        c.execute(
            """
            DELETE FROM prices
            WHERE ts < ?
            """,
            (cutoff,)
        )


def price_at_or_before(
    key,
    target_ts
):

    with db() as c:

        row = c.execute(
            """
            SELECT price
            FROM prices
            WHERE key=?
            AND ts <= ?
            ORDER BY ts DESC
            LIMIT 1
            """,
            (
                key,
                target_ts
            )
        ).fetchone()

    if row:
        return float(
            row["price"]
        )

    return None


def pct_change(
    current,
    old
):

    if current is None:
        return None

    if old is None:
        return None

    if old == 0:
        return None

    return (
        (current - old)
        / old
    ) * 100


# ============================================================
# NUMBER HELPERS
# ============================================================

def fmt_num(
    value,
    decimals=0
):

    if value is None:
        return "---"

    return f"{value:,.{decimals}f}"


def extract_first_number(
    text
):

    if not text:
        return None

    text = str(text)

    text = text.replace(
        ",",
        ""
    )

    text = text.replace(
        "٬",
        ""
    )

    trans = str.maketrans(
        "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
        "01234567890123456789"
    )

    text = text.translate(
        trans
    )

    match = re.search(
        r"\d+(?:\.\d+)?",
        text
    )

    if not match:
        return None

    try:
        return float(
            match.group()
        )
    except Exception:
        return None


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

def profile_current(
    path
):

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

        r"نرخ فعلی:\s*([\d,٬.]+)",

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

            if (
                value is not None
                and value > 0
            ):
                return value

    # fallback:
    # پیدا کردن عبارت نرخ فعلی در HTML/text
    match = re.search(
        r"نرخ فعلی.{0,80}?([\d,٬.]+)",
        text
    )

    if match:

        value = extract_first_number(
            match.group(1)
        )

        if value:
            return value

    return None


def safe_profile(
    path,
    name
):

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

    # ========================================================
    # GOLD / COINS / FX / OIL
    # ========================================================

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

        # مسیر درست پروفایل نفت برنت
        "brent": (
            "/profile/energy-brent-oil",
            1
        ),
    }

    for key, (
        path,
        divisor
    ) in sources.items():

        raw = safe_profile(
            path,
            key
        )

        if raw is not None:

            prices[key] = (
                raw / divisor
            )

        else:

            prices[key] = None

    # ========================================================
    # MOLTEN GOLD
    # ========================================================

    prices["abshode"] = None

    try:

        html = fetch_html(
            TGJU + "/gold-chart"
        )

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        wanted = [
            "آبشده نقدی",
            "آبشده نقدى",
            "آبشده"
        ]

        for row in soup.find_all(
            "tr"
        ):

            cells = row.find_all(
                ["td", "th"]
            )

            if len(cells) < 2:
                continue

            row_text = row.get_text(
                " ",
                strip=True
            )

            normalized = (
                row_text
                .replace("ي", "ی")
                .replace("ك", "ک")
            )

            if any(
                name in normalized
                for name in wanted
            ):

                for cell in cells[1:]:

                    value = (
                        extract_first_number(
                            cell.get_text(
                                " ",
                                strip=True
                            )
                        )
                    )

                    if (
                        value is not None
                        and value > 0
                    ):

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

    # ========================================================
    # CRYPTO
    # ========================================================

    for key in (
        "btc",
        "eth",
        "sol",
        "bnb",
        "xrp"
    ):
        prices[key] = None

    crypto_sources = {

        "btc": (
            "/profile/crypto-bitcoin",
            1
        ),

        "eth": (
            "/profile/crypto-ethereum",
            1
        ),

        "sol": (
            "/profile/crypto-solana",
            1
        ),

        "bnb": (
            "/profile/crypto-bnb",
            1
        ),

        "xrp": (
            "/profile/crypto-xrp",
            1
        ),
    }

    for key, (
        path,
        divisor
    ) in crypto_sources.items():

        raw = safe_profile(
            path,
            key
        )

        if raw is not None:

            prices[key] = (
                raw / divisor
            )

    # ========================================================
    # USDT TOMAN
    # ========================================================

    # اگر نرخ تتر تومانی مستقیم در TGJU
    # قابل استخراج نبود، دلار بازار را استفاده می‌کنیم.
    prices["usdt_toman"] = prices.get(
        "usd"
    )

    return prices


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

def arrow_pct(
    value
):

    if value is None:
        return "▫️ ---"

    if value > 0:
        return (
            f"📈 +{value:.2f}%"
        )

    if value < 0:
        return (
            f"📉 {value:.2f}%"
        )

    return "➖ 0.00%"


# ============================================================
# LINE
# ============================================================

def line_for(
    key,
    prices,
    old5,
    old60
):

    label, unit, decimals = (
        NAMES[key]
    )

    value = prices.get(
        key
    )

    if value is None:

        return (
            f"• {label}: --- {unit}"
        )

    result = (
        f"• {label}: "
        f"`{fmt_num(value, decimals)}` "
        f"{unit}"
    )

    change5 = pct_change(
        value,
        old5
    )

    change60 = pct_change(
        value,
        old60
    )

    result += (
        f"\n  ├ ۵ دقیقه: "
        f"{arrow_pct(change5)}"
    )

    result += (
        f"\n  └ ۱ ساعت: "
        f"{arrow_pct(change60)}"
    )

    return result


# ============================================================
# LIVE MESSAGE
# ============================================================

def live_message(
    prices
):

    now = iran_now()
    ts = unix_now()

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
        "🤖 @tala\\_arz\\_irr"
    ]

    return "\n".join(
        lines
    )


# ============================================================
# HOURLY SUMMARY
# ============================================================

def hourly_summary(
    prices
):

    ts = unix_now()
    now = iran_now()

    lines = [

        (
            f"📌 *جمع‌بندی بازار | "
            f"{now.strftime('%Y/%m/%d - %H:%M')}*"
        ),

        "",
    ]

    groups = [

        (
            "🥇 *طلا و سکه*",
            (
                "gold_18",
                "gold_24",
                "abshode",
                "mesghal",
                "coin_emami",
                "coin_half"
            )
        ),

        (
            "💵 *ارز*",
            (
                "usd",
                "eur",
                "gbp"
            )
        ),

        (
            "💰 *ارز دیجیتال*",
            (
                "btc",
                "eth",
                "sol",
                "bnb",
                "xrp",
                "usdt_toman"
            )
        ),

        (
            "🛢️ *انرژی*",
            (
                "brent",
            )
        ),
    ]

    for title, keys in groups:

        lines.append(title)

        for key in keys:

            label, unit, decimals = (
                NAMES[key]
            )

            value = prices.get(
                key
            )

            if value is None:
                continue

            old = price_at_or_before(
                key,
                ts - 3600
            )

            change = pct_change(
                value,
                old
            )

            lines.append(
                f"• {label}: "
                f"`{fmt_num(value, decimals)}` "
                f"{unit} "
                f"{arrow_pct(change)}"
            )

        lines.append("")

    lines += [

        "━━━━━━━━━━━━━━━━━━",
        "🤖 @tala\\_arz\\_irr"
    ]

    return "\n".join(
        lines
    )


# ============================================================
# DAILY SUMMARY
# ============================================================

def daily_summary(
    prices
):

    ts = unix_now()

    now = iran_now()

    candidates = []

    for key in NAMES:

        current = prices.get(
            key
        )

        old = price_at_or_before(
            key,
            ts - 86400
        )

        change = pct_change(
            current,
            old
        )

        if change is not None:

            candidates.append(
                (
                    key,
                    change
                )
            )

    candidates.sort(
        key=lambda x: x[1],
        reverse=True
    )

    lines = [

        (
            f"📰 *خلاصه روزانه بازار | "
            f"{now.strftime('%Y/%m/%d')}*"
        ),

        "",
    ]

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
            "هنوز داده کافی برای "
            "مقایسه ۲۴ ساعته وجود ندارد."
        )

    lines += [

        "",
        "━━━━━━━━━━━━━━━━━━",
        "🤖 @tala\\_arz\\_irr"
    ]

    return "\n".join(
        lines
    )


# ============================================================
# MARKET SCHEDULE
# ============================================================

def market_is_open():

    now = iran_now()

    return (
        MARKET_START_HOUR
        <= now.hour
        < MARKET_END_HOUR
    )


def is_friday():

    return (
        iran_now().weekday()
        == 4
    )


def current_update_interval():

    if is_friday():
        return FRIDAY_INTERVAL

    return NORMAL_INTERVAL


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

    asset = parts[1].replace(
        " ",
        ""
    )

    direction_word = (
        parts[2].lower()
    )

    try:

        target = float(
            parts[3].replace(
                ",",
                ""
            )
        )

    except ValueError:

        return None

    key = KEY_ALIASES.get(
        asset
    )

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

    return (
        key,
        direction,
        target
    )


async def alert_command(
    update,
    context
):

    parsed = parse_alert(
        update.message.text or ""
    )

    if not parsed:

        await update.message.reply_text(
            "فرمت درست:\n\n"
            "/alert طلا بالای 22000000\n"
            "/alert دلار زیر 205000\n"
            "/alert بیتکوین بالای 80000"
        )

        return

    key, direction, target = (
        parsed
    )

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
                unix_now()
            )
        )

    word = (
        "بالاتر از"
        if direction == "above"
        else
        "پایین‌تر از"
    )

    await update.message.reply_text(

        f"🔔 هشدار ثبت شد.\n\n"
        f"{NAMES[key][0]} "
        f"{word} "
        f"`{fmt_num(target, NAMES[key][2])}`",

        parse_mode=ParseMode.MARKDOWN
    )


async def alerts_command(
    update,
    context
):

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
        ""
    ]

    for row in rows:

        word = (
            "بالای"
            if row["direction"]
            == "above"
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


async def cancel_alert_command(
    update,
    context
):

    parts = (
        update.message.text or ""
    ).split()

    if (
        len(parts) != 2
        or not parts[1].isdigit()
    ):

        await update.message.reply_text(
            "مثال:\n"
            "/cancelalert 12"
        )

        return

    alert_id = int(
        parts[1]
    )

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


async def check_alerts(
    context
):

    prices = context.application.bot_data.get(
        "latest_prices",
        {}
    )

    if not prices:
        return

    with db() as c:

        rows = c.execute(
            """
            SELECT
                id,
                user_id,
                key,
                direction,
                target
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

                hit = (
                    value >= row["target"]
                )

                word = "به بالای"

            else:

                hit = (
                    value <= row["target"]
                )

                word = "به زیر"

            if not hit:
                continue

            try:

                await context.bot.send_message(

                    chat_id=row["user_id"],

                    text=(
                        "🔔 *هشدار قیمت*\n\n"
                        f"{NAMES[row['key']][0]} "
                        f"{word} "
                        f"`{fmt_num(row['target'], NAMES[row['key']][2])}` "
                        "رسید.\n"
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
                    "Alert failed: %s",
                    e
                )


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
                "💵 ارز",
                callback_data="fx"
            )
        ],

        [
            InlineKeyboardButton(
                "💰 کریپتو",
                callback_data="crypto"
            ),

            InlineKeyboardButton(
                "🛢️ نفت",
                callback_data="oil"
            )
        ],

        [
            InlineKeyboardButton(
                "🔔 هشدار",
                callback_data="alert_help"
            )
        ]
    ])


# ============================================================
# START
# ============================================================

async def start(
    update,
    context
):

    await update.message.reply_text(

        "سلام 👋\n\n"
        "به ربات قیمت طلا، ارز و بازار خوش اومدی.\n\n"
        "قیمت‌ها از منابع بازار دریافت می‌شوند "
        "و سابقه قیمت برای محاسبه تغییرات ذخیره می‌شود.",

        reply_markup=keyboard()
    )


# ============================================================
# PRICE COMMAND
# ============================================================

async def price_command(
    update,
    context
):

    prices = (
        context.application.bot_data.get(
            "latest_prices"
        )
    )

    if not prices:

        prices = fetch_prices()

    await update.message.reply_text(

        live_message(prices),

        parse_mode=ParseMode.MARKDOWN
    )


# ============================================================
# BUTTON
# ============================================================

async def button_handler(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    prices = (
        context.application.bot_data.get(
            "latest_prices"
        )
    )

    if not prices:
        prices = fetch_prices()

    if query.data == "all":

        text = live_message(
            prices
        )

    elif query.data == "gold":

        keys = (
            "gold_18",
            "gold_24",
            "abshode",
            "mesghal",
            "ounce",
            "coin_emami",
            "coin_half"
        )

        lines = [
            "🥇 *طلا و سکه*",
            ""
        ]

        for key in keys:

            label, unit, decimals = (
                NAMES[key]
            )

            lines.append(
                f"• {label}: "
                f"`{fmt_num(prices.get(key), decimals)}` "
                f"{unit}"
            )

        text = "\n".join(
            lines
        )

    elif query.data == "crypto":

        keys = (
            "btc",
            "eth",
            "sol",
            "bnb",
            "xrp",
            "usdt_toman"
        )

        lines = [
            "💰 *ارز دیجیتال*",
            ""
        ]

        for key in keys:

            label, unit, decimals = (
                NAMES[key]
            )

            lines.append(
                f"• {label}: "
                f"`{fmt_num(prices.get(key), decimals)}` "
                f"{unit}"
            )

        text = "\n".join(
            lines
        )

    elif query.data == "fx":

        keys = (
            "usd",
            "eur",
            "gbp"
        )

        lines = [
            "💵 *ارزهای خارجی*",
            ""
        ]

        for key in keys:

            label, unit, decimals = (
                NAMES[key]
            )

            lines.append(
                f"• {label}: "
                f"`{fmt_num(prices.get(key), decimals)}` "
                f"{unit}"
            )

        text = "\n".join(
            lines
        )

    elif query.data == "oil":

        value = prices.get(
            "brent"
        )

        text = (
            "🛢️ *نفت برنت*\n\n"
            f"`{fmt_num(value, 2)}` دلار "
            "به‌ازای هر بشکه"
        )

    else:

        text = (
            "🔔 *هشدار قیمت*\n\n"
            "`/alert طلا بالای 22000000`\n"
            "`/alert دلار زیر 205000`\n\n"
            "`/alerts` دیدن هشدارها\n"
            "`/cancelalert 12` حذف هشدار"
        )

    await query.edit_message_text(

        text,

        parse_mode=ParseMode.MARKDOWN,

        reply_markup=keyboard()
    )


# ============================================================
# LIVE CHANNEL
# ============================================================

async def update_live_channel(
    context
):

    if not market_is_open():

        logger.info(
            "Market closed."
        )

        return

    try:

        prices = fetch_prices()

        valid_count = sum(
            1
            for value in prices.values()
            if value is not None
            and value > 0
        )

        # حداقل چند داده معتبر لازم داریم
        # تا اطلاعات خراب روی پیام قبلی ننشیند.
        if valid_count < 5:

            logger.warning(
                "Not enough market data: %s",
                valid_count
            )

            return

        context.application.bot_data[
            "latest_prices"
        ] = prices

        save_snapshot(
            prices
        )

        text = live_message(
            prices
        )

        message_id = get_setting(
            "live_message_id"
        )

        # ----------------------------------------------------
        # EDIT EXISTING MESSAGE
        # ----------------------------------------------------

        if message_id:

            try:

                await context.bot.edit_message_text(

                    chat_id=CHANNEL_ID,

                    message_id=int(
                        message_id
                    ),

                    text=text,

                    parse_mode=ParseMode.MARKDOWN
                )

                logger.info(
                    "Live message edited."
                )

            except Exception as e:

                logger.warning(
                    "Live edit failed: %s",
                    e
                )

                # اگر پیام حذف شده یا ID خراب شده
                # یک پیام جدید می‌سازیم.
                sent = await context.bot.send_message(

                    chat_id=CHANNEL_ID,

                    text=text,

                    parse_mode=ParseMode.MARKDOWN
                )

                set_setting(
                    "live_message_id",
                    sent.message_id
                )

        else:

            sent = await context.bot.send_message(

                chat_id=CHANNEL_ID,

                text=text,

                parse_mode=ParseMode.MARKDOWN
            )

            set_setting(
                "live_message_id",
                sent.message_id
            )

        await check_alerts(
            context
        )

    except Exception as e:

        logger.exception(
            "Live update failed."
        )


# ============================================================
# MARKET UPDATE JOB
# ============================================================

async def scheduled_market_update(
    context
):

    if not market_is_open():
        return

    now_ts = unix_now()

    interval = (
        current_update_interval()
    )

    last_ts = context.application.bot_data.get(
        "last_market_update_ts",
        0
    )

    if (
        now_ts - last_ts
        < interval
    ):
        return

    # فقط وقتی واقعاً قرار است
    # آپدیت انجام شود timestamp را تغییر می‌دهیم.
    await update_live_channel(
        context
    )

    context.application.bot_data[
        "last_market_update_ts"
    ] = now_ts


# ============================================================
# HOURLY NEW MESSAGE
# ============================================================

async def hourly_job(
    context
):

    # جمع‌بندی فقط در ساعات فعال
    if not market_is_open():
        return

    try:

        prices = (
            context.application.bot_data.get(
                "latest_prices"
            )
        )

        if not prices:

            prices = fetch_prices()

        valid_count = sum(
            1
            for value in prices.values()
            if value is not None
            and value > 0
        )

        if valid_count < 5:
            return

        # مهم:
        # اینجا SEND MESSAGE داریم،
        # نه EDIT.
        await context.bot.send_message(

            chat_id=CHANNEL_ID,

            text=hourly_summary(
                prices
            ),

            parse_mode=ParseMode.MARKDOWN
        )

        logger.info(
            "Hourly summary sent as NEW message."
        )

    except Exception:

        logger.exception(
            "Hourly summary failed."
        )


# ============================================================
# DAILY SUMMARY
# ============================================================

async def daily_job(
    context
):

    # ساعت 22:30 اجرا می‌شود،
    # قبل از بسته شدن آپدیت شبانه.
    if not market_is_open():
        return

    try:

        prices = (
            context.application.bot_data.get(
                "latest_prices"
            )
        )

        if not prices:
            prices = fetch_prices()

        await context.bot.send_message(

            chat_id=CHANNEL_ID,

            text=daily_summary(
                prices
            ),

            parse_mode=ParseMode.MARKDOWN
        )

        logger.info(
            "Daily summary sent."
        )

    except Exception:

        logger.exception(
            "Daily summary failed."
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

    # ========================================================
    # COMMANDS
    # ========================================================

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
        CallbackQueryHandler(
            button_handler
        )
    )

    # ========================================================
    # LIVE MARKET
    # ========================================================
    #
    # هر 60 ثانیه بررسی می‌کند.
    #
    # روز عادی:
    #     هر 5 دقیقه
    #
    # جمعه:
    #     هر 15 دقیقه
    #
    # 23 تا 07:
    #     هیچ کاری
    #
    # ========================================================

    app.job_queue.run_repeating(

        scheduled_market_update,

        interval=60,

        first=10,

        name="market_update"
    )

    # ========================================================
    # HOURLY SUMMARY
    # ========================================================
    #
    # هر ساعت یک پیام کاملاً جدید.
    #
    # ========================================================

    app.job_queue.run_repeating(

        hourly_job,

        interval=3600,

        first=60,

        name="hourly_summary"
    )

    # ========================================================
    # DAILY SUMMARY
    # ========================================================
    #
    # هر روز ساعت 22:30 تهران
    #
    # ========================================================

    app.job_queue.run_daily(

        daily_job,

        time=datetime.strptime(
            "22:30",
            "%H:%M"
        ).time().replace(
            tzinfo=IRAN_TZ
        ),

        days=tuple(
            range(7)
        ),

        name="daily_summary"
    )

    logger.info(
        "================================="
    )

    logger.info(
        "Tala Arz Bot started."
    )

    logger.info(
        "Live: 5 min / Friday: 15 min"
    )

    logger.info(
        "Hourly summary: NEW message"
    )

    logger.info(
        "Market hours: 07:00-23:00"
    )

    logger.info(
        "================================="
    )

    app.run_polling()


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()