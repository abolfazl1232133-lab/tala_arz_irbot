import os
import logging
import requests

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


# ==========================================
# تنظیمات
# ==========================================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@tala_arz_irr")
BRSAPI_KEY = os.environ.get("BRSAPI_KEY")

# هر 5 دقیقه
UPDATE_INTERVAL = 300


# ==========================================
# لاگ‌ها
# ==========================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


# ==========================================
# ساعت ایران
# ==========================================

IRAN_TZ = pytz.timezone("Asia/Tehran")


def get_iran_time():
    return datetime.now(IRAN_TZ).strftime("%Y/%m/%d - %H:%M")


# ==========================================
# فرمت قیمت
# ==========================================

def fmt(value):

    if value is None:
        return "---"

    try:
        text = str(value).strip().replace(",", "")
        number = float(text)
        return f"{number:,.0f}"

    except Exception:
        return str(value) if value else "---"


# ==========================================
# دریافت اطلاعات از API
# ==========================================

def get_api_data(url):

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=20
    )

    logger.info(f"API URL: {url.split('?')[0]}")
    logger.info(f"API Status: {response.status_code}")
    logger.info(
        f"API Response Preview: {response.text[:1500]}"
    )

    response.raise_for_status()

    return response.json()


# ==========================================
# ساخت قیمت خالی
# ==========================================

def empty_price(label, unit):

    return {
        "label": label,
        "price": "---",
        "unit": unit
    }


# ==========================================
# جستجوی آیتم در پاسخ API
# ==========================================

def find_item(data, keywords):

    keywords = [
        str(keyword).lower().strip()
        for keyword in keywords
    ]

    items = []

    # اگر داده لیست باشد
    if isinstance(data, list):

        items.extend(data)

    # اگر دیکشنری باشد
    elif isinstance(data, dict):

        items.append(data)

        for value in data.values():

            if isinstance(value, list):

                items.extend(value)

            elif isinstance(value, dict):

                items.append(value)

                for sub_value in value.values():

                    if isinstance(sub_value, list):

                        items.extend(sub_value)

                    elif isinstance(sub_value, dict):

                        items.append(sub_value)


    # بررسی آیتم‌ها
    for item in items:

        if not isinstance(item, dict):
            continue

        searchable = " ".join([

            str(item.get("name", "")),
            str(item.get("Name", "")),

            str(item.get("symbol", "")),
            str(item.get("Symbol", "")),

            str(item.get("key", "")),
            str(item.get("Key", "")),

            str(item.get("title", "")),
            str(item.get("Title", "")),

            str(item.get("label", "")),
            str(item.get("Label", "")),

            str(item.get("code", "")),
            str(item.get("Code", "")),

            str(item.get("persian_name", "")),
            str(item.get("fa_name", "")),

        ]).lower()


        for keyword in keywords:

            if keyword in searchable:

                return item


    return None


# ==========================================
# استخراج قیمت از آیتم
# ==========================================

def extract_price(item):

    if not isinstance(item, dict):
        return "---"


    possible_keys = [

        "price",
        "Price",

        "value",
        "Value",

        "last",
        "Last",

        "current",
        "Current",

        "close",
        "Close",

        "p",

        "rate",
        "Rate",

        "buy",
        "Buy",

        "sell",
        "Sell",

    ]


    for key in possible_keys:

        value = item.get(key)

        if value is not None and value != "":

            return fmt(value)


    return "---"


# ==========================================
# گرفتن همه قیمت‌ها
# ==========================================

def fetch_all_prices():

    prices = {}


    # --------------------------------------
    # مقادیر پیش‌فرض
    # --------------------------------------

    prices["gold_18"] = empty_price(
        "طلای ۱۸ عیار (گرم)",
        "تومان"
    )

    prices["gold_24"] = empty_price(
        "طلای ۲۴ عیار (گرم)",
        "تومان"
    )

    prices["gold_abshode"] = empty_price(
        "طلای آبشده",
        "تومان"
    )

    prices["gold_mesghal"] = empty_price(
        "مثقال طلا",
        "تومان"
    )

    prices["gold_ounce"] = empty_price(
        "اونس جهانی طلا",
        "دلار"
    )

    prices["sekke_emami"] = empty_price(
        "سکه امامی",
        "تومان"
    )

    prices["sekke_nim"] = empty_price(
        "نیم سکه",
        "تومان"
    )

    prices["usd"] = empty_price(
        "دلار آمریکا",
        "تومان"
    )

    prices["eur"] = empty_price(
        "یورو",
        "تومان"
    )

    prices["bitcoin"] = empty_price(
        "بیت‌کوین",
        "دلار"
    )

    prices["ethereum"] = empty_price(
        "اتریوم",
        "دلار"
    )

    prices["tether"] = empty_price(
        "تتر",
        "تومان"
    )


    # ======================================
    # طلا، ارز و سکه
    # ======================================

    try:

        gold_url = (
            "https://api.brsapi.ir/Market/"
            f"Gold_Currency.php?key={BRSAPI_KEY}"
        )

        logger.info(
            "Getting Gold / Currency data..."
        )

        data = get_api_data(gold_url)


        # طلای 18
        item = find_item(
            data,
            [
                "geram18",
                "18 عیار",
                "۱۸ عیار",
                "gold18",
                "gold 18",
            ]
        )

        prices["gold_18"]["price"] = (
            extract_price(item)
        )


        # طلای 24
        item = find_item(
            data,
            [
                "geram24",
                "24 عیار",
                "۲۴ عیار",
                "gold24",
                "gold 24",
            ]
        )

        prices["gold_24"]["price"] = (
            extract_price(item)
        )


        # آبشده
        item = find_item(
            data,
            [
                "abshode",
                "abshodeh",
                "آبشده",
                "آب شده",
            ]
        )

        prices["gold_abshode"]["price"] = (
            extract_price(item)
        )


        # مثقال
        item = find_item(
            data,
            [
                "mesghal",
                "مثقال",
            ]
        )

        prices["gold_mesghal"]["price"] = (
            extract_price(item)
        )


        # اونس جهانی طلا
        item = find_item(
            data,
            [
                "ons",
                "ounce",
                "اونس",
                "انس",
                "gold ounce",
            ]
        )

        prices["gold_ounce"]["price"] = (
            extract_price(item)
        )


        # دلار
        item = find_item(
            data,
            [
                "usd",
                "دلار آمریکا",
                "دلار",
            ]
        )

        prices["usd"]["price"] = (
            extract_price(item)
        )


        # یورو
        item = find_item(
            data,
            [
                "eur",
                "euro",
                "یورو",
            ]
        )

        prices["eur"]["price"] = (
            extract_price(item)
        )


        # سکه امامی
        item = find_item(
            data,
            [
                "sekee_emami",
                "sekke_emami",
                "امامی",
            ]
        )

        prices["sekke_emami"]["price"] = (
            extract_price(item)
        )


        # نیم سکه
        item = find_item(
            data,
            [
                "nim",
                "نیم سکه",
                "نیم‌سکه",
            ]
        )

        prices["sekke_nim"]["price"] = (
            extract_price(item)
        )


        logger.info(
            "Gold / Currency data processed successfully"
        )


    except Exception as error:

        logger.exception(
            f"Gold/Currency API ERROR: {error}"
        )


    # ======================================
    # کریپتو
    # ======================================

    try:

        crypto_url = (
            "https://api.brsapi.ir/Market/"
            f"Cryptocurrency.php?key={BRSAPI_KEY}"
        )

        logger.info(
            "Getting Cryptocurrency data..."
        )

        data = get_api_data(crypto_url)


        # بیت‌کوین
        item = find_item(
            data,
            [
                "bitcoin",
                "btc",
                "بیت کوین",
                "بیت‌کوین",
            ]
        )

        prices["bitcoin"]["price"] = (
            extract_price(item)
        )


        # اتریوم
        item = find_item(
            data,
            [
                "ethereum",
                "eth",
                "اتریوم",
            ]
        )

        prices["ethereum"]["price"] = (
            extract_price(item)
        )


        # تتر
        item = find_item(
            data,
            [
                "tether",
                "usdt",
                "تتر",
            ]
        )

        prices["tether"]["price"] = (
            extract_price(item)
        )


        logger.info(
            "Cryptocurrency data processed successfully"
        )


    except Exception as error:

        logger.exception(
            f"Crypto API ERROR: {error}"
        )


    return prices


# ==========================================
# ساخت متن قیمت‌ها
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

        price = prices[key]

        lines.append(

            f"• {price['label']}: "
            f"`{price['price']}` "
            f"{price['unit']}"

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

        price = prices[key]

        lines.append(

            f"• {price['label']}: "
            f"`{price['price']}` "
            f"{price['unit']}"

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

        price = prices[key]

        lines.append(

            f"• {price['label']}: "
            f"`{price['price']}` "
            f"{price['unit']}"

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

        price = prices[key]

        lines.append(

            f"• {price['label']}: "
            f"`{price['price']}` "
            f"{price['unit']}"

        )


    lines += [

        "",

        "━━━━━━━━━━━━━━━━━━",

        "🤖 @tala\\_arz\\_irr"

    ]


    return "\n".join(lines)


# ==========================================
# دستور شروع
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
        ]

    ]


    await update.message.reply_text(

        "سلام! 👋\n\n"
        "به ربات قیمت طلا و ارز خوش اومدی.\n"
        "از منوی زیر انتخاب کن:",

        reply_markup=InlineKeyboardMarkup(
            keyboard
        )

    )


# ==========================================
# کنترل دکمه‌ها
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

            price = prices[key]

            lines.append(

                f"• {price['label']}: "
                f"`{price['price']}` "
                f"{price['unit']}"

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

            price = prices[key]

            lines.append(

                f"• {price['label']}: "
                f"`{price['price']}` "
                f"{price['unit']}"

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

            price = prices[key]

            lines.append(

                f"• {price['label']}: "
                f"`{price['price']}` "
                f"{price['unit']}"

            )


        message = "\n".join(lines)


    else:

        message = "❌ خطایی رخ داد."


    await query.edit_message_text(

        message,

        parse_mode=ParseMode.MARKDOWN

    )


# ==========================================
# دستور /price
# ==========================================

async def price_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "⏳ در حال دریافت قیمت‌ها..."
    )

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

        logger.info(
            "Updating channel..."
        )

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
            "BOT_TOKEN در Environment Variables تنظیم نشده است!"
        )


    if not BRSAPI_KEY:

        raise ValueError(
            "BRSAPI_KEY در Environment Variables تنظیم نشده است!"
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


    # هر 5 دقیقه
    app.job_queue.run_repeating(

        send_to_channel,

        interval=UPDATE_INTERVAL,

        first=10

    )


    logger.info(
        "Bot started successfully!"
    )


    app.run_polling()


# ==========================================
# شروع برنامه
# ==========================================

if __name__ == "__main__":
    main()