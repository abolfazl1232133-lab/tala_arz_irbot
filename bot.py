import os
import logging
import requests
import json
import re

from datetime import datetime
import pytz

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


# ==================================================
# تنظیمات
# ==================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@tala_arz_irr")

UPDATE_INTERVAL = 300

IRAN_TZ = pytz.timezone("Asia/Tehran")


# ==================================================
# لاگ
# ==================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


# ==================================================
# زمان ایران
# ==================================================

def get_iran_time():

    return datetime.now(IRAN_TZ).strftime(
        "%Y/%m/%d - %H:%M"
    )


# ==================================================
# فرمت قیمت
# ==================================================

def fmt(value):

    if value is None:
        return "---"

    try:

        value = str(value)

        value = value.replace(",", "")
        value = value.replace("٬", "")

        number = float(value)

        return f"{number:,.0f}"

    except Exception:

        return str(value)


# ==================================================
# ساخت آیتم قیمت
# ==================================================

def price_item(label, price, unit):

    return {
        "label": label,
        "price": fmt(price) if price is not None else "---",
        "unit": unit
    }


# ==================================================
# پیدا کردن تمام دیکشنری‌ها
# ==================================================

def find_all_dicts(data):

    result = []

    if isinstance(data, dict):

        result.append(data)

        for value in data.values():

            result.extend(
                find_all_dicts(value)
            )

    elif isinstance(data, list):

        for item in data:

            result.extend(
                find_all_dicts(item)
            )

    return result


# ==================================================
# استخراج عدد
# ==================================================

def extract_number(value):

    if value is None:
        return None

    try:

        if isinstance(value, (int, float)):
            return float(value)

        text = str(value)

        text = text.replace(",", "")
        text = text.replace("٬", "")

        match = re.search(
            r"[-+]?\d*\.?\d+",
            text
        )

        if match:

            return float(
                match.group()
            )

    except Exception:

        return None

    return None


# ==================================================
# تبدیل ریال به تومان
# ==================================================

def rial_to_toman(value):

    number = extract_number(value)

    if number is None:
        return None

    return number / 10


# ==================================================
# دریافت داده بازار از TGJU
# ==================================================

def get_tgju_data():

    urls = [

        "https://www.tgju.org/economics/api/swaggerui/swagger.json",

        "https://www.tgju.org/news/api/v1/openapi.json",

        "https://www.tgju.org/global-markets/swagger.json",

    ]

    headers = {

        "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",

        "Accept":
            "application/json,text/html,*/*",

        "Accept-Language":
            "fa-IR,fa;q=0.9,en;q=0.8",

    }


    for url in urls:

        try:

            logger.info(
                f"Trying TGJU: {url}"
            )

            response = requests.get(

                url,

                headers=headers,

                timeout=20

            )

            logger.info(
                f"TGJU Status: {response.status_code}"
            )


            if response.status_code == 200:

                logger.info(
                    f"TGJU Response Preview: "
                    f"{response.text[:500]}"
                )

                return response.json()


        except Exception as error:

            logger.error(
                f"TGJU request error: {error}"
            )


    return None


# ==================================================
# پیدا کردن قیمت
# ==================================================

def search_price(data, keywords):

    if not data:
        return None


    keywords = [

        str(keyword).lower()

        for keyword in keywords

    ]


    all_dicts = find_all_dicts(data)


    for item in all_dicts:

        searchable_parts = []


        for key in [

            "key",
            "name",
            "title",
            "symbol",
            "label",
            "title_fa",
            "name_fa",
            "slug",
            "code",

        ]:

            value = item.get(key)

            if value:

                searchable_parts.append(
                    str(value).lower()
                )


        searchable_text = " ".join(
            searchable_parts
        )


        found = False


        for keyword in keywords:

            if keyword in searchable_text:

                found = True

                break


        if not found:

            continue


        for price_key in [

            "price",
            "current",
            "value",
            "last",
            "close",
            "p",

        ]:

            value = item.get(price_key)

            if value is not None:

                number = extract_number(value)

                if number is not None:

                    return number


    return None


# ==================================================
# دریافت همه قیمت‌ها
# ==================================================

def fetch_all_prices():

    logger.info(
        "Getting market prices..."
    )


    data = get_tgju_data()


    if not data:

        logger.error(
            "Could not get market data"
        )

        return get_empty_prices()


    # ------------------------------------------------
    # طلا 18
    # ------------------------------------------------

    gold_18 = search_price(

        data,

        [

            "geram18",

            "طلای 18",

            "طلای ۱۸",

            "gold18",

        ]

    )


    # ------------------------------------------------
    # طلا 24
    # ------------------------------------------------

    gold_24 = search_price(

        data,

        [

            "geram24",

            "طلای 24",

            "طلای ۲۴",

            "gold24",

        ]

    )


    # ------------------------------------------------
    # آبشده
    # ------------------------------------------------

    abshode = search_price(

        data,

        [

            "abshode",

            "آبشده",

        ]

    )


    # ------------------------------------------------
    # مثقال
    # ------------------------------------------------

    mesghal = search_price(

        data,

        [

            "mesghal",

            "مثقال",

        ]

    )


    # ------------------------------------------------
    # اونس جهانی طلا
    # ------------------------------------------------

    gold_ounce = search_price(

        data,

        [

            "ons",

            "ounce",

            "اونس طلا",

            "انس طلا",

        ]

    )


    # ------------------------------------------------
    # دلار
    # ------------------------------------------------

    usd = search_price(

        data,

        [

            "usd",

            "دلار",

        ]

    )


    # ------------------------------------------------
    # یورو
    # ------------------------------------------------

    eur = search_price(

        data,

        [

            "eur",

            "یورو",

            "euro",

        ]

    )


    # ------------------------------------------------
    # سکه امامی
    # ------------------------------------------------

    sekke_emami = search_price(

        data,

        [

            "sekee",

            "sekke",

            "امامی",

            "سکه امامی",

        ]

    )


    # ------------------------------------------------
    # نیم سکه
    # ------------------------------------------------

    sekke_nim = search_price(

        data,

        [

            "nim",

            "نیم سکه",

        ]

    )


    # ------------------------------------------------
    # بیت کوین
    # ------------------------------------------------

    bitcoin = search_price(

        data,

        [

            "bitcoin",

            "btc",

            "بیت کوین",

            "بیت‌کوین",

        ]

    )


    # ------------------------------------------------
    # اتریوم
    # ------------------------------------------------

    ethereum = search_price(

        data,

        [

            "ethereum",

            "eth",

            "اتریوم",

        ]

    )


    # ------------------------------------------------
    # تتر
    # ------------------------------------------------

    tether = search_price(

        data,

        [

            "tether",

            "usdt",

            "تتر",

        ]

    )


    prices = {


        "gold_18": price_item(

            "طلای ۱۸ عیار (گرم)",

            rial_to_toman(gold_18),

            "تومان"

        ),


        "gold_24": price_item(

            "طلای ۲۴ عیار (گرم)",

            rial_to_toman(gold_24),

            "تومان"

        ),


        "gold_abshode": price_item(

            "طلای آبشده",

            rial_to_toman(abshode),

            "تومان"

        ),


        "gold_mesghal": price_item(

            "مثقال طلا",

            rial_to_toman(mesghal),

            "تومان"

        ),


        "gold_ounce": price_item(

            "اونس جهانی طلا",

            gold_ounce,

            "دلار"

        ),


        "sekke_emami": price_item(

            "سکه امامی",

            rial_to_toman(sekke_emami),

            "تومان"

        ),


        "sekke_nim": price_item(

            "نیم سکه",

            rial_to_toman(sekke_nim),

            "تومان"

        ),


        "bitcoin": price_item(

            "بیت‌کوین",

            bitcoin,

            "دلار"

        ),


        "ethereum": price_item(

            "اتریوم",

            ethereum,

            "دلار"

        ),


        "tether": price_item(

            "تتر",

            rial_to_toman(tether),

            "تومان"

        ),


        "usd": price_item(

            "دلار آمریکا",

            rial_to_toman(usd),

            "تومان"

        ),


        "eur": price_item(

            "یورو",

            rial_to_toman(eur),

            "تومان"

        ),

    }


    logger.info(
        f"Prices received: {prices}"
    )


    return prices


# ==================================================
# قیمت‌های خالی
# ==================================================

def get_empty_prices():

    return {

        "gold_18":
            price_item("طلای ۱۸ عیار (گرم)", None, "تومان"),

        "gold_24":
            price_item("طلای ۲۴ عیار (گرم)", None, "تومان"),

        "gold_abshode":
            price_item("طلای آبشده", None, "تومان"),

        "gold_mesghal":
            price_item("مثقال طلا", None, "تومان"),

        "gold_ounce":
            price_item("اونس جهانی طلا", None, "دلار"),

        "sekke_emami":
            price_item("سکه امامی", None, "تومان"),

        "sekke_nim":
            price_item("نیم سکه", None, "تومان"),

        "bitcoin":
            price_item("بیت‌کوین", None, "دلار"),

        "ethereum":
            price_item("اتریوم", None, "دلار"),

        "tether":
            price_item("تتر", None, "تومان"),

        "usd":
            price_item("دلار آمریکا", None, "تومان"),

        "eur":
            price_item("یورو", None, "تومان"),

    }


# ==================================================
# ساخت پیام کامل
# ==================================================

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


# ==================================================
# شروع
# ==================================================

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

        reply_markup=InlineKeyboardMarkup(
            keyboard
        )

    )


# ==================================================
# دکمه‌ها
# ==================================================

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

        message = format_message(
            prices
        )


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


# ==================================================
# دستور /price
# ==================================================

async def price_command(

    update: Update,

    context: ContextTypes.DEFAULT_TYPE

):

    prices = fetch_all_prices()

    message = format_message(
        prices
    )

    await update.message.reply_text(

        message,

        parse_mode=ParseMode.MARKDOWN

    )


# ==================================================
# ارسال به کانال
# ==================================================

async def send_to_channel(

    context: ContextTypes.DEFAULT_TYPE

):

    try:

        logger.info(
            "Updating channel..."
        )

        prices = fetch_all_prices()

        message = format_message(
            prices
        )

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
            f"Channel error: {error}"
        )


# ==================================================
# اجرای اصلی
# ==================================================

def main():

    if not BOT_TOKEN:

        raise ValueError(
            "BOT_TOKEN تنظیم نشده است"
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


# ==================================================
# شروع برنامه
# ==================================================

if __name__ == "__main__":

    main()