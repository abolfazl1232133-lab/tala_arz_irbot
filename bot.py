import os
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import pytz

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)


# ==========================================
# تنظیمات
# ==========================================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@tala_arz_irr")

# هر 5 دقیقه
UPDATE_INTERVAL = 300

IRAN_TZ = pytz.timezone("Asia/Tehran")


# ==========================================
# لاگ
# ==========================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


# ==========================================
# تنظیمات درخواست
# ==========================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
}


# ==========================================
# زمان ایران
# ==========================================

def get_iran_time():
    return datetime.now(IRAN_TZ).strftime("%Y/%m/%d - %H:%M")


# ==========================================
# فرمت قیمت
# ==========================================

def fmt(value):

    if value is None:
        return "---"

    try:
        value = str(value)
        value = value.replace(",", "")
        value = value.replace("٬", "")
        value = value.strip()

        number = float(value)

        return f"{number:,.0f}"

    except Exception:
        return str(value)


# ==========================================
# ریال به تومان
# ==========================================

def rial_to_toman(value):

    try:
        value = float(
            str(value)
            .replace(",", "")
            .replace("٬", "")
        )

        return value / 10

    except Exception:
        return None


# ==========================================
# ساخت آیتم قیمت
# ==========================================

def make_price(label, price, unit):

    return {
        "label": label,
        "price": fmt(price) if price is not None else "---",
        "unit": unit,
    }


# ==========================================
# قیمت‌های خالی
# ==========================================

def empty_prices():

    return {

        "gold_18": make_price(
            "طلای ۱۸ عیار (گرم)",
            None,
            "تومان"
        ),

        "gold_24": make_price(
            "طلای ۲۴ عیار (گرم)",
            None,
            "تومان"
        ),

        "gold_abshode": make_price(
            "طلای آبشده",
            None,
            "تومان"
        ),

        "gold_mesghal": make_price(
            "مثقال طلا",
            None,
            "تومان"
        ),

        "gold_ounce": make_price(
            "اونس جهانی طلا",
            None,
            "دلار"
        ),

        "sekke_emami": make_price(
            "سکه امامی",
            None,
            "تومان"
        ),

        "sekke_nim": make_price(
            "نیم سکه",
            None,
            "تومان"
        ),

        "bitcoin": make_price(
            "بیت‌کوین",
            None,
            "دلار"
        ),

        "ethereum": make_price(
            "اتریوم",
            None,
            "دلار"
        ),

        "tether": make_price(
            "تتر",
            None,
            "تومان"
        ),

        "usd": make_price(
            "دلار آمریکا",
            None,
            "تومان"
        ),

        "eur": make_price(
            "یورو",
            None,
            "تومان"
        ),
    }


# ==========================================
# استخراج قیمت از صفحه TGJU
# ==========================================

def fetch_tgju_page(url):

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=25
    )

    logger.info(
        f"TGJU Request: {url} | Status: {response.status_code}"
    )

    response.raise_for_status()

    return response.text


def find_price_in_html(html, keywords):

    soup = BeautifulSoup(html, "html.parser")

    text_keywords = [
        str(x).lower()
        for x in keywords
    ]

    # تمام ردیف‌های جدول
    rows = soup.find_all("tr")

    for row in rows:

        row_text = row.get_text(
            " ",
            strip=True
        ).lower()

        found = False

        for keyword in text_keywords:

            if keyword in row_text:

                found = True
                break

        if not found:
            continue

        # جستجو در td ها
        cells = row.find_all(["td", "th"])

        for cell in reversed(cells):

            value = cell.get_text(
                " ",
                strip=True
            )

            cleaned = (
                value
                .replace(",", "")
                .replace("٬", "")
                .replace(" ", "")
            )

            try:

                number = float(cleaned)

                if number > 0:
                    return number

            except Exception:
                continue

    return None


# ==========================================
# دریافت بازار طلا
# ==========================================

def get_gold_market():

    html = fetch_tgju_page(
        "https://www.tgju.org/gold-chart"
    )

    return {

        "gold_18": find_price_in_html(
            html,
            [
                "طلای 18",
                "طلای ۱۸",
                "geram18",
            ]
        ),

        "gold_24": find_price_in_html(
            html,
            [
                "طلای 24",
                "طلای ۲۴",
                "geram24",
            ]
        ),

        "gold_abshode": find_price_in_html(
            html,
            [
                "آبشده",
            ]
        ),

        "gold_mesghal": find_price_in_html(
            html,
            [
                "مثقال",
            ]
        ),

        "gold_ounce": find_price_in_html(
            html,
            [
                "انس طلا",
                "اونس طلا",
                "انس",
            ]
        ),
    }


# ==========================================
# دریافت ارز
# ==========================================

def get_currency_market():

    html = fetch_tgju_page(
        "https://www.tgju.org/currency"
    )

    return {

        "usd": find_price_in_html(
            html,
            [
                "دلار",
                "USD",
            ]
        ),

        "eur": find_price_in_html(
            html,
            [
                "یورو",
                "EUR",
            ]
        ),
    }


# ==========================================
# دریافت سکه
# ==========================================

def get_coin_market():

    html = fetch_tgju_page(
        "https://www.tgju.org/coin"
    )

    return {

        "sekke_emami": find_price_in_html(
            html,
            [
                "سکه امامی",
                "سکه طرح جدید",
            ]
        ),

        "sekke_nim": find_price_in_html(
            html,
            [
                "نیم سکه",
            ]
        ),
    }


# ==========================================
# دریافت کریپتو
# ==========================================

def get_crypto_prices():

    url = (
        "https://api.coingecko.com/api/v3/"
        "simple/price"
        "?ids=bitcoin,ethereum,tether"
        "&vs_currencies=usd"
    )

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=20
    )

    logger.info(
        f"CoinGecko Status: {response.status_code}"
    )

    response.raise_for_status()

    data = response.json()

    return {

        "bitcoin": (
            data
            .get("bitcoin", {})
            .get("usd")
        ),

        "ethereum": (
            data
            .get("ethereum", {})
            .get("usd")
        ),

        "tether_usd": (
            data
            .get("tether", {})
            .get("usd")
        ),
    }


# ==========================================
# دریافت همه قیمت‌ها
# ==========================================

def fetch_all_prices():

    prices = empty_prices()


    # -------------------------------
    # طلا
    # -------------------------------

    try:

        logger.info("Getting gold prices...")

        gold = get_gold_market()

        prices["gold_18"] = make_price(
            "طلای ۱۸ عیار (گرم)",
            rial_to_toman(
                gold.get("gold_18")
            ),
            "تومان"
        )

        prices["gold_24"] = make_price(
            "طلای ۲۴ عیار (گرم)",
            rial_to_toman(
                gold.get("gold_24")
            ),
            "تومان"
        )

        prices["gold_abshode"] = make_price(
            "طلای آبشده",
            rial_to_toman(
                gold.get("gold_abshode")
            ),
            "تومان"
        )

        prices["gold_mesghal"] = make_price(
            "مثقال طلا",
            rial_to_toman(
                gold.get("gold_mesghal")
            ),
            "تومان"
        )

        prices["gold_ounce"] = make_price(
            "اونس جهانی طلا",
            gold.get("gold_ounce"),
            "دلار"
        )

    except Exception as error:

        logger.exception(
            f"Gold ERROR: {error}"
        )


    # -------------------------------
    # ارز
    # -------------------------------

    try:

        logger.info("Getting currency prices...")

        currency = get_currency_market()

        prices["usd"] = make_price(
            "دلار آمریکا",
            rial_to_toman(
                currency.get("usd")
            ),
            "تومان"
        )

        prices["eur"] = make_price(
            "یورو",
            rial_to_toman(
                currency.get("eur")
            ),
            "تومان"
        )

    except Exception as error:

        logger.exception(
            f"Currency ERROR: {error}"
        )


    # -------------------------------
    # سکه
    # -------------------------------

    try:

        logger.info("Getting coin prices...")

        coins = get_coin_market()

        prices["sekke_emami"] = make_price(
            "سکه امامی",
            rial_to_toman(
                coins.get("sekke_emami")
            ),
            "تومان"
        )

        prices["sekke_nim"] = make_price(
            "نیم سکه",
            rial_to_toman(
                coins.get("sekke_nim")
            ),
            "تومان"
        )

    except Exception as error:

        logger.exception(
            f"Coin ERROR: {error}"
        )


    # -------------------------------
    # کریپتو
    # -------------------------------

    try:

        logger.info("Getting crypto prices...")

        crypto = get_crypto_prices()

        prices["bitcoin"] = make_price(
            "بیت‌کوین",
            crypto.get("bitcoin"),
            "دلار"
        )

        prices["ethereum"] = make_price(
            "اتریوم",
            crypto.get("ethereum"),
            "دلار"
        )

        # برای قیمت تتر به تومان
        # از قیمت دلار آزاد استفاده می‌کنیم

        usd_price = prices["usd"]["price"]

        if usd_price != "---":

            tether_toman = float(
                usd_price.replace(",", "")
            )

            prices["tether"] = make_price(
                "تتر",
                tether_toman,
                "تومان"
            )

    except Exception as error:

        logger.exception(
            f"Crypto ERROR: {error}"
        )


    logger.info(
        f"FINAL PRICES: {prices}"
    )

    return prices


# ==========================================
# ساخت پیام
# ==========================================

def format_message(prices):

    now = get_iran_time()

    lines = [

        "📊 *قیمت‌های لحظه‌ای بازار*",
        f"🕐 آخرین به‌روزرسانی: `{now}`",
        "",
        "━━━━━━━━━━━━━━━━━━",
        "🥇 *فلزات گرانبها*",

    ]


    for key in [
        "gold_18",
        "gold_24",
        "gold_abshode",
        "gold_mesghal",
        "gold_ounce",
    ]:

        p = prices[key]

        lines.append(
            f"• {p['label']}: "
            f"`{p['price']}` "
            f"{p['unit']}"
        )


    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━",
        "🪙 *سکه*",
    ]


    for key in [
        "sekke_emami",
        "sekke_nim",
    ]:

        p = prices[key]

        lines.append(
            f"• {p['label']}: "
            f"`{p['price']}` "
            f"{p['unit']}"
        )


    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━",
        "💰 *ارز دیجیتال*",
    ]


    for key in [
        "bitcoin",
        "ethereum",
        "tether",
    ]:

        p = prices[key]

        lines.append(
            f"• {p['label']}: "
            f"`{p['price']}` "
            f"{p['unit']}"
        )


    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━",
        "💵 *ارزهای خارجی*",
    ]


    for key in [
        "usd",
        "eur",
    ]:

        p = prices[key]

        lines.append(
            f"• {p['label']}: "
            f"`{p['price']}` "
            f"{p['unit']}"
        )


    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━",
        "🤖 @tala\\_arz\\_irr"
    ]


    return "\n".join(lines)


# ==========================================
# /start
# ==========================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    keyboard = [

        [
            InlineKeyboardButton(
                "📊 همه قیمت‌ها",
                callback_data="prices"
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
                callback_data="fiat"
            )
        ],
    ]


    await update.message.reply_text(
        "سلام! 👋\n\n"
        "به ربات قیمت طلا و ارز خوش اومدی.\n"
        "از منوی زیر انتخاب کن:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==========================================
# دکمه‌ها
# ==========================================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    await query.edit_message_text(
        "⏳ در حال دریافت قیمت‌ها..."
    )

    prices = fetch_all_prices()


    if query.data == "prices":

        message = format_message(prices)


    elif query.data == "gold":

        keys = [
            "gold_18",
            "gold_24",
            "gold_abshode",
            "gold_mesghal",
            "gold_ounce",
            "sekke_emami",
            "sekke_nim",
        ]

        lines = [
            "🥇 *طلا و سکه*",
            ""
        ]

        for key in keys:

            p = prices[key]

            lines.append(
                f"• {p['label']}: "
                f"`{p['price']}` "
                f"{p['unit']}"
            )

        message = "\n".join(lines)


    elif query.data == "crypto":

        keys = [
            "bitcoin",
            "ethereum",
            "tether",
        ]

        lines = [
            "💰 *ارزهای دیجیتال*",
            ""
        ]

        for key in keys:

            p = prices[key]

            lines.append(
                f"• {p['label']}: "
                f"`{p['price']}` "
                f"{p['unit']}"
            )

        message = "\n".join(lines)


    elif query.data == "fiat":

        keys = [
            "usd",
            "eur",
        ]

        lines = [
            "💵 *ارزهای خارجی*",
            ""
        ]

        for key in keys:

            p = prices[key]

            lines.append(
                f"• {p['label']}: "
                f"`{p['price']}` "
                f"{p['unit']}"
            )

        message = "\n".join(lines)


    else:

        message = "❌ خطایی رخ داد."


    await query.edit_message_text(
        message,
        parse_mode=ParseMode.MARKDOWN
    )


# ==========================================
# /price
# ==========================================

async def price_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    prices = fetch_all_prices()

    message = format_message(prices)

    await update.message.reply_text(
        message,
        parse_mode=ParseMode.MARKDOWN
    )


# ==========================================
# ارسال به کانال
# ==========================================

async def send_to_channel(
    context: ContextTypes.DEFAULT_TYPE
):

    try:

        prices = fetch_all_prices()

        message = format_message(prices)

        await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=message,
            parse_mode=ParseMode.MARKDOWN
        )

        logger.info(
            "Channel updated successfully"
        )

    except Exception as error:

        logger.exception(
            f"Channel ERROR: {error}"
        )


# ==========================================
# اجرای ربات
# ==========================================

def main():

    if not BOT_TOKEN:

        raise ValueError(
            "BOT_TOKEN تنظیم نشده است!"
        )


    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )


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
        CallbackQueryHandler(
            button_handler
        )
    )


    app.job_queue.run_repeating(
        send_to_channel,
        interval=UPDATE_INTERVAL,
        first=10
    )


    logger.info(
        "Bot started successfully!"
    )

    app.run_polling()


if __name__ == "__main__":
    main()