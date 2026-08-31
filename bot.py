import os
import re
import sqlite3
import logging
from datetime import datetime, timedelta

import requests
import pytz
from bs4 import BeautifulSoup

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

UPDATE_INTERVAL = 300

IRAN_TZ = pytz.timezone("Asia/Tehran")
TGJU = "https://www.tgju.org"

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


# ============================================================
# DATABASE
# ============================================================

def db():
    conn = sqlite3.connect(
        DATABASE_PATH,
        timeout=20
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


def save_snapshot(prices):

    ts = int(datetime.now().timestamp())

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

        # حدود ۸ روز تاریخچه
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

    return float(row["price"]) if row else None


def pct_change(current, old):

    if current is None:
        return None

    if old is None:
        return None

    if old == 0:
        return None

    return ((current - old) / old) * 100


# ============================================================
# NUMBER HELPERS
# ============================================================

def fmt_num(value, decimals=0):

    if value is None:
        return "---"

    if decimals:
        return f"{value:,.{decimals}f}"

    return f"{value:,.0f}"


def extract_first_number(text):

    if not text:
        return None

    text = str(text)

    text = text.replace(",", "")
    text = text.replace("٬", "")

    trans = str.maketrans(
        "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
        "01234567890123456789"
    )

    text = text.translate(trans)

    match = re.search(
        r"\d+(?:\.\d+)?",
        text
    )

    if match:
        try:
            return float(match.group())
        except:
            return None

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

        r"نرخ فعلی\s*[:：]+\s*([\d,٬.]+)",

        r"نرخ فعلی\s*[:：]?\s*([\d,٬.]+)",

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

    return None


def safe_profile(path, name):

    try:

        value = profile_current(path)

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
# TABLE PRICE
# ============================================================

def table_price(html, names):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    normalized_names = []

    for name in names:

        name = name.replace(
            "ي",
            "ی"
        )

        name = name.replace(
            "ك",
            "ک"
        )

        normalized_names.append(
            name.lower()
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

        normalized = label.replace(
            "ي",
            "ی"
        )

        normalized = normalized.replace(
            "ك",
            "ک"
        )

        normalized = normalized.lower()

        if any(
            name == normalized or
            name in normalized
            for name in normalized_names
        ):

            for cell in cells[1:]:

                value = extract_first_number(
                    cell.get_text(
                        " ",
                        strip=True
                    )
                )

                if value is not None and value > 0:
                    return value

    return None


# ============================================================
# MARKET DATA
# ============================================================

def fetch_prices():

    prices = {}

    # --------------------------------------------------------
    # GOLD / COINS / CURRENCY / OIL
    # --------------------------------------------------------

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

        "brent": (
            "/profile/brent",
            1
        ),
    }

    for key, source in sources.items():

        path, divisor = source

        raw = safe_profile(
            path,
            key
        )

        if raw is not None:

            prices[key] = raw / divisor

        else:

            prices[key] = None

    # --------------------------------------------------------
    # MELTED GOLD
    # --------------------------------------------------------

    try:

        html = fetch_html(
            TGJU + "/gold-chart"
        )

        value = table_price(
            html,
            [
                "آبشده نقدی",
                "آبشده نقدى"
            ]
        )

        if value is not None:

            prices["abshode"] = value / 10

        else:

            prices["abshode"] = None

    except Exception as e:

        logger.error(
            "Abshode failed: %s",
            e
        )

        prices["abshode"] = None

    # --------------------------------------------------------
    # CRYPTO
    # --------------------------------------------------------

    crypto_keys = (
        "btc",
        "eth",
        "sol",
        "bnb",
        "xrp",
        "usdt"
    )

    for key in crypto_keys:
        prices[key] = None

    try:

        html = fetch_html(
            TGJU + "/crypto"
        )

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

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

        for key, names in crypto_map.items():

            found = None

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

                if any(
                    name.lower() in row_text
                    for name in names
                ):

                    for cell in cells[1:]:

                        value = extract_first_number(
                            cell.get_text(
                                " ",
                                strip=True
                            )
                        )

                        if value is not None and value > 0:

                            found = value

                            break

                if found is not None:
                    break

            prices[key] = found

    except Exception as e:

        logger.error(
            "Crypto failed: %s",
            e
        )

    # --------------------------------------------------------
    # TETHER TOMAN
    # --------------------------------------------------------

    # برای نمایش قیمت تتر به تومان
    # از نرخ دلار بازار استفاده می‌کنیم.

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
# PERCENT DISPLAY
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

    ts = int(
        datetime.now().timestamp()
    )

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

    return "\n".join(lines)


# ============================================================
# HOURLY SUMMARY
# ============================================================

def hourly_summary(prices):

    ts = int(
        datetime.now().timestamp()
    )

    now = iran_now()

    lines = [

        f"📌 *جمع‌بندی بازار | "
        f"{now.strftime('%H:%M')}*",

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
                "coin_emami"
            )
        ),

        (
            "💵 ارز",
            (
                "usd",
                "eur",
                "gbp"
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
                "usdt_toman"
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

        lines.append(title)

        for key in group:

            label, unit, decimals = NAMES[key]

            value = prices.get(key)

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

    return "\n".join(lines)


# ============================================================
# DAILY SUMMARY
# ============================================================

def daily_summary(prices):

    ts = int(
        datetime.now().timestamp()
    )

    now = iran_now()

    lines = [

        (
            f"📰 *خلاصه روزانه بازار | "
            f"{now.strftime('%Y/%m/%d')}*"
        ),

        "",
    ]

    candidates = []

    for key, info in NAMES.items():

        label, unit, decimals = info

        value = prices.get(key)

        old = price_at_or_before(
            key,
            ts - 86400
        )

        if (
            value is not None
            and old is not None
        ):

            change = pct_change(
                value,
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
            "هنوز برای مقایسه ۲۴ ساعته "
            "داده کافی جمع نشده است."
        )

    lines += [

        "",

        "🤖 @tala\\_arz\\_irr"
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
}


def parse_alert(text):

    parts = text.strip().split()

    if len(parts) < 4:
        return None

    asset = parts[1].replace(
        " ",
        ""
    )

    direction_word = parts[2].lower()

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
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    parsed = parse_alert(
        update.message.text or ""
    )

    if not parsed:

        await update.message.reply_text(
            "فرمت درست:\n\n"
            "/alert طلا بالای 22000000\n"
            "/alert دلار زیر 205000\n\n"
            "دارایی‌ها:\n"
            "طلا، دلار، یورو، پوند، "
            "بیت‌کوین، اتریوم، سولانا، "
            "BNB، XRP و تتر"
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
                int(
                    datetime.now().timestamp()
                )
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
        f"`{fmt_num(target, NAMES[key][2])}`"

    )


async def alerts_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    with db() as c:

        rows = c.execute(
            """
            SELECT
                id,
                key,
                direction,
                target
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


async def cancel_alert_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
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
        "✅ اگر هشدار متعلق به شما بود، "
        "غیرفعال شد."
    )


async def check_alerts(context):

    if not market_is_open():
        return

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

            else:

                hit = (
                    value <= row["target"]
                )

            if not hit:
                continue

            if row["direction"] == "above":

                word = "به بالای"

            else:

                word = "به زیر"

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
                    "Alert send failed: %s",
                    e
                )


# ============================================================
# MARKET SCHEDULE
# ============================================================

def market_is_open():

    """
    بازار از 07:00 تا 23:00 فعال است.

    در خارج از این ساعت هیچ آپدیت خودکاری
    به کانال ارسال نمی‌شود.
    """

    now = iran_now()

    return (
        7 <= now.hour < 23
    )


def is_slow_day():

    """
    جمعه با فاصله ۱۵ دقیقه آپدیت می‌شود.
    """

    now = iran_now()

    # Friday = 4
    return now.weekday() == 4


def current_update_interval():

    """
    روزهای عادی: ۵ دقیقه
    جمعه: ۱۵ دقیقه
    """

    if is_slow_day():

        return 900

    return 300


# ============================================================
# BOT KEYBOARD
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
                "📈 نمودار",
                callback_data="chart_help"
            ),

            InlineKeyboardButton(
                "🔔 هشدارها",
                callback_data="alert_help"
            ),

        ],
    ])


# ============================================================
# START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(

        "سلام 👋\n\n"

        "به ربات قیمت طلا، ارز و بازار خوش اومدی.\n\n"

        "قیمت‌ها از منابع بازار دریافت می‌شن.\n"
        "همچنین تاریخچه قیمت برای محاسبه "
        "تغییرات ذخیره می‌شود.",

        reply_markup=keyboard()
    )


# ============================================================
# PRICE COMMAND
# ============================================================

async def price_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    prices = (
        context.application.bot_data.get(
            "latest_prices"
        )
        or
        fetch_prices()
    )

    await update.message.reply_text(

        live_message(prices),

        parse_mode=ParseMode.MARKDOWN
    )


# ============================================================
# BUTTON HANDLER
# ============================================================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    prices = (
        context.application.bot_data.get(
            "latest_prices"
        )
        or
        fetch_prices()
    )

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

            "",
        ]

        for key in keys:

            label, unit, decimals = NAMES[key]

            lines.append(

                f"• {label}: "
                f"`{fmt_num(prices.get(key), decimals)}` "
                f"{unit}"

            )

        text = "\n".join(
            lines
        )

    elif query.data == "oil":

        text = (

            "🛢️ *نفت برنت*\n\n"

            f"`{fmt_num(prices.get('brent'), 2)}` "
            "دلار"

        )

    elif query.data == "alert_help":

        text = (

            "🔔 *ساخت هشدار*\n\n"

            "مثال:\n\n"

            "`/alert طلا بالای 22000000`\n"

            "`/alert دلار زیر 205000`\n\n"

            "`/alerts` = دیدن هشدارها\n\n"

            "`/cancelalert 12` = حذف هشدار شماره ۱۲"

        )

    else:

        text = (

            "📈 *نمودار*\n\n"

            "تاریخچه قیمت‌ها در دیتابیس ذخیره می‌شود.\n\n"

            "در مرحله بعد می‌توانیم نمودار "
            "۲۴ ساعت و ۷ روزه را هم به ربات اضافه کنیم."

        )

    await query.edit_message_text(

        text,

        parse_mode=ParseMode.MARKDOWN,

        reply_markup=keyboard()
    )


# ============================================================
# LIVE CHANNEL UPDATE
# ============================================================

async def update_live_channel(context):

    if not market_is_open():

        logger.info(
            "Market closed. Live update skipped."
        )

        return

    try:

        prices = fetch_prices()

        if not any(
            value is not None
            for value in prices.values()
        ):

            logger.warning(
                "No market data received. "
                "Old channel message kept."
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
                    "Live channel message edited."
                )

            except Exception as e:

                logger.warning(
                    "Edit failed. "
                    "Sending new live message: %s",
                    e
                )

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
            "Live update failed: %s",
            e
        )


# ============================================================
# SMART SCHEDULER
# ============================================================

async def scheduled_market_update(context):

    """
    این تابع هر یک دقیقه بررسی می‌شود.

    روز عادی:
        هر ۵ دقیقه

    جمعه:
        هر ۱۵ دقیقه

    23:00 تا 07:00:
        هیچ کاری انجام نمی‌شود.
    """

    if not market_is_open():
        return

    now_ts = int(
        datetime.now().timestamp()
    )

    interval = current_update_interval()

    last_ts = context.application.bot_data.get(
        "last_market_update_ts",
        0
    )

    if (
        now_ts - last_ts
        < interval
    ):
        return

    context.application.bot_data[
        "last_market_update_ts"
    ] = now_ts

    await update_live_channel(
        context
    )


# ============================================================
# HOURLY JOB
# ============================================================

async def hourly_job(context):

    if not market_is_open():

        logger.info(
            "Market closed. "
            "Hourly summary skipped."
        )

        return

    try:

        prices = (
            context.application.bot_data.get(
                "latest_prices"
            )
            or
            fetch_prices()
        )

        await context.bot.send_message(

            chat_id=CHANNEL_ID,

            text=hourly_summary(
                prices
            ),

            parse_mode=ParseMode.MARKDOWN
        )

    except Exception as e:

        logger.exception(
            "Hourly summary failed: %s",
            e
        )


# ============================================================
# DAILY JOB
# ============================================================

async def daily_job(context):

    if not market_is_open():

        logger.info(
            "Market closed. "
            "Daily summary skipped."
        )

        return

    try:

        prices = (
            context.application.bot_data.get(
                "latest_prices"
            )
            or
            fetch_prices()
        )

        await context.bot.send_message(

            chat_id=CHANNEL_ID,

            text=daily_summary(
                prices
            ),

            parse_mode=ParseMode.MARKDOWN
        )

    except Exception as e:

        logger.exception(
            "Daily summary failed: %s",
            e
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

    # --------------------------------------------------------
    # COMMANDS
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # MARKET UPDATE
    # --------------------------------------------------------
    #
    # هر دقیقه بیدار می‌شود ولی خودش تصمیم می‌گیرد
    # که الان زمان آپدیت ۵ دقیقه‌ای است یا ۱۵ دقیقه‌ای.
    #

    app.job_queue.run_repeating(

        scheduled_market_update,

        interval=60,

        first=5
    )

    # --------------------------------------------------------
    # HOURLY SUMMARY
    # --------------------------------------------------------

    app.job_queue.run_daily(

        hourly_job,

        time=datetime.strptime(
            "00:00",
            "%H:%M"
        ).time().replace(
            tzinfo=IRAN_TZ
        ),

        days=tuple(
            range(7)
        )
    )

    # --------------------------------------------------------
    # DAILY SUMMARY
    # --------------------------------------------------------

    app.job_queue.run_daily(

        daily_job,

        time=datetime.strptime(
            "23:55",
            "%H:%M"
        ).time().replace(
            tzinfo=IRAN_TZ
        ),

        days=tuple(
            range(7)
        )
    )

    logger.info(
        "Tala Arz Bot V2 started."
    )

    app.run_polling()


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()