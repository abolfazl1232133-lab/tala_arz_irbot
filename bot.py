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

UPDATE_INTERVAL = 300  # هر 5 دقیقه


# ==========================================
# لاگ
# ==========================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


# ==========================================
# منطقه زمانی ایران
# ==========================================

IRAN_TZ = pytz.timezone("Asia/Tehran")


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

    if value == "":
        return "---"

    try:

        text = str(value).strip()

        # حذف کاما
        text = text.replace(",", "")

        # تبدیل عدد
        number = float(text)

        # نمایش بدون اعشار
        return f"{number:,.0f}"

    except Exception:

        return str(value)


# ==========================================
# گرفتن قیمت از یک آیتم
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
    ]

    for key in possible_keys:

        value = item.get(key)

        if value is not None and value != "":
            return fmt(value)

    return "---"


# ==========================================
# پیدا کردن آیتم مورد نظر
# ==========================================

def find_market_item(data, keywords):

    keywords = [
        str(keyword).lower().strip()
        for keyword in keywords
    ]

    # اگر پاسخ لیست باشد
    if isinstance(data, list):

        items = data

    # اگر پاسخ دیکشنری باشد
    elif isinstance(data, dict):

        items = []

        # خود دیکشنری
        items.append(data)

        # بررسی همه مقادیر داخل آن
        for value in data.values():

            if isinstance(value, list):
                items.extend(value)

            elif isinstance(value, dict):
                items.append(value)

                # یک لایه عمیق‌تر
                for sub_value in value.values():

                    if isinstance(sub_value, list):
                        items.extend(sub_value)

                    elif isinstance(sub_value, dict):
                        items.append(sub_value)

    else:
        return None


    # بررسی آیتم‌ها
    for item in items:

        if not isinstance(item, dict):
            continue

        searchable_values = [

            item.get("name", ""),
            item.get("Name", ""),

            item.get("symbol", ""),
            item.get("Symbol", ""),

            item.get("key", ""),
            item.get("Key", ""),

            item.get("title", ""),
            item.get("Title", ""),

            item.get("label", ""),
            item.get("Label", ""),

            item.get("category", ""),
            item.get("Category", ""),

            item.get("code", ""),
            item.get("Code", ""),
        ]

        searchable_text = " ".join(
            str(value).lower()
            for value in searchable_values
        )

        for keyword in keywords:

            if keyword in searchable_text:
                return item

    return None


# ==========================================
# دریافت اطلاعات API
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

    logger.info(
        f"API Status: {response.status_code}"
    )

    # اگر خطای HTTP بود
    response.raise_for_status()

    logger.info(
        f"API Response Preview: {response.text[:1000]}"
    )

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
# دریافت همه قیمت‌ها
# ==========================================

def fetch_all_prices():

    prices = {}


    # ======================================
    # لینک طلا، ارز و سکه
    # ======================================

    gold_url = (
        "https://BrsApi.ir/Api/Market/"
        f"Gold_Currency.php?key={BRSAPI_KEY}"
    )


    try:

        logger.info(
            "Getting gold and currency prices..."
        )

        data = get_api_data(gold_url)


        # ----------------------------------
        # طلای 18 عیار
        # ----------------------------------

        item = find_market_item(
            data,
            [
                "geram18",
                "طلای ۱۸ عیار",
                "طلای 18 عیار",
                "طلای ۱۸",
                "طلای 18",
                "gold 18",
            ]
        )

        prices["gold_18"] = {
            "label": "طلای ۱۸ عیار (گرم)",
            "price": extract_price(item),
            "unit": "تومان"
        }


        # ----------------------------------
        # طلای 24 عیار
        # ----------------------------------

        item = find_market_item(
            data,
            [
                "geram24",
                "طلای ۲۴ عیار",
                "طلای 24 عیار",
                "طلای ۲۴",
                "طلای 24",
                "gold 24",
            ]
        )

        prices["gold_24"] = {
            "label": "طلای ۲۴ عیار (گرم)",
            "price": extract_price(item),
            "unit": "تومان"
        }


        # ----------------------------------
        # آبشده
        # ----------------------------------

        item = find_market_item(
            data,
            [
                "abshode",
                "abshodeh",
                "آبشده",
                "آب شده",
            ]
        )

        prices["gold_abshode"] = {
            "label": "طلای آبشده",
            "price": extract_price(item),
            "unit": "تومان"
        }


        # ----------------------------------
        # مثقال
        # ----------------------------------

        item = find_market_item(
            data,
            [
                "mesghal",
                "مثقال",
            ]
        )

        prices["gold_mesghal"] = {
            "label": "مثقال طلا",
            "price": extract_price(item),
            "unit": "تومان"
        }


        # ----------------------------------
        # اونس جهانی طلا
        # ----------------------------------

        item = find_market_item(
            data,
            [
                "ons",
                "ounce",
                "gold ounce",
                "اونس جهانی",
                "انس جهانی",
                "اونس طلا",
            ]
        )

        prices["gold_ounce"] = {
            "label": "اونس جهانی طلا",
            "price": extract_price(item),
            "unit": "دلار"
        }


        # ----------------------------------
        # دلار
        # ----------------------------------

        item = find_market_item(
            data,
            [
                "usd",
                "دلار آمریکا",
                "دلار",
            ]
        )

        prices["usd"] = {
            "label": "دلار آمریکا",
            "price": extract_price(item),
            "unit": "تومان"
        }


        # ----------------------------------
        # یورو
        # ----------------------------------

        item = find_market_item(
            data,
            [
                "eur",
                "یورو",
                "euro",
            ]
        )

        prices["eur"] = {
            "label": "یورو",
            "price": extract_price(item),
            "unit": "تومان"
        }


        # ----------------------------------
        # سکه امامی
        # ----------------------------------

        item = find_market_item(
            data,
            [
                "sekee_emami",
                "sekke_emami",
                "coin_emami",
                "سکه امامی",
                "امامی",
            ]
        )

        prices["sekke_emami"] = {
            "label": "سکه امامی",
            "price": extract_price(item),
            "unit": "تومان"
        }


        # ----------------------------------
        # نیم سکه
        # ----------------------------------

        item = find_market_item(
            data,
            [
                "nim",
                "نیم سکه",
                "نیم‌سکه",
                "half coin",
            ]
        )

        prices["sekke_nim"] = {
            "label": "نیم سکه",
            "price": extract_price(item),
            "unit": "تومان"
        }


        logger.info(
            "Gold and currency prices received successfully"
        )


    except Exception as error:

        logger.exception(
            f"Gold/Currency API ERROR: {error}"
        )

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

        prices["usd"] = empty_price(
            "دلار آمریکا",
            "تومان"
        )

        prices["eur"] = empty_price(
            "یورو",
            "تومان"
        )

        prices["sekke_emami"] = empty_price(
            "سکه امامی",
            "تومان"
        )

        prices["sekke_nim"] = empty_price(
            "نیم سکه",
            "تومان"
        )


    # ======================================
    # کریپتو
    # ======================================

    crypto_url = (
        "https://BrsApi.ir/Api/Market/"
        f"Cryptocurrency.php?key={BRSAPI_KEY}"
    )


    try:

        logger.info(
            "Getting cryptocurrency prices..."
        )

        data = get_api_data(crypto_url)


        # ----------------------------------
        # بیت کوین
        # ----------------------------------

        item = find_market_item(
            data,
            [
                "bitcoin",
                "btc",
                "بیت کوین",
                "بیت‌کوین",
            ]
        )

        prices["bitcoin"] = {
            "label": "بیت‌کوین",
            "price": extract_price(item),
            "unit": "دلار"
        }


        # ----------------------------------
        # اتریوم
        # ----------------------------------

        item = find_market_item(
            data,
            [
                "ethereum",
                "eth",
                "اتریوم",
            ]
        )

        prices["ethereum"] = {
            "label": "اتریوم",
            "price": extract_price(item),
            "unit": "دلار"
        }


        # ----------------------------------
        # تتر
        # ----------------------------------

        item = find_market_item(
            data,
            [
                "tether",
                "usdt",
                "تتر",
            ]
        )

        prices["tether"] = {
            "label": "تتر",
            "price": extract_price(item),
            "unit": "تومان"
        }


        logger.info(
            "Cryptocurrency prices received successfully"
        )


    except Exception as error:

        logger.exception(
            f"Crypto API ERROR: {error}"
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

        price = prices.get(key, {})

        lines.append(
            f"• {price.get('label', '')}: "
            f"`{price.get('price', '---')}` "
            f"{price.get('unit', '')}"
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

        price = prices.get(key, {})

        lines.append(
            f"• {price.get('label', '')}: "
            f"`{price.get('price', '---')}` "
            f"{price.get('unit', '')}"
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

        price = prices.get(key, {})

        lines.append(
            f"• {price.get('label', '')}: "
            f"`{price.get('price', '---')}` "
            f"{price.get('unit', '')}"
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

        price = prices.get(key, {})

        lines.append(
            f"• {price.get('label', '')}: "
            f"`{price.get('price', '---')}` "
            f"{price.get('unit', '')}"
        )


    lines += [

        "",

        "━━━━━━━━━━━━━━━━━━",

        "🤖 @tala\\_arz\\_irr"

    ]


    return "\n".join(lines)


# ==========================================
# شروع ربات
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

        message = format_message(
            prices
        )


    elif query.data == "gold":

        lines = [

            "🥇 *طلا و سکه*",
            ""

        ]


        for key in [

            "gold_18",
            "gold_24",
            "gold_abshode",
            "gold_mesghal",
            "gold_ounce",
            "sekke_emami",
            "sekke_nim",

        ]:

            price = prices.get(key, {})

            lines.append(

                f"• {price.get('label', '')}: "
                f"`{price.get('price', '---')}` "
                f"{price.get('unit', '')}"

            )


        message = "\n".join(lines)


    elif query.data == "crypto":

        lines = [

            "💰 *ارزهای دیجیتال*",
            ""

        ]


        for key in [

            "bitcoin",
            "ethereum",
            "tether",

        ]:

            price = prices.get(key, {})

            lines.append(

                f"• {price.get('label', '')}: "
                f"`{price.get('price', '---')}` "
                f"{price.get('unit', '')}"

            )


        message = "\n".join(lines)


    elif query.data == "fiat":

        lines = [

            "💵 *ارزهای خارجی*",
            ""

        ]


        for key in [

            "usd",
            "eur",

        ]:

            price = prices.get(key, {})

            lines.append(

                f"• {price.get('label', '')}: "
                f"`{price.get('price', '---')}` "
                f"{price.get('unit', '')}"

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

    message = format_message(
        prices
    )


    await update.message.reply_text(

        message,

        parse_mode=ParseMode.MARKDOWN

    )


# ==========================================
# ارسال قیمت به کانال
# ==========================================

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
            f"Channel ERROR: {error}"
        )


# ==========================================
# اجرای اصلی
# ==========================================

def main():

    if not BOT_TOKEN:

        raise ValueError(
            "BOT_TOKEN تنظیم نشده است!"
        )


    if not BRSAPI_KEY:

        raise ValueError(
            "BRSAPI_KEY تنظیم نشده است!"
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


    # هر 5 دقیقه یک بار
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
# اجرا
# ==========================================

if __name__ == "__main__":

    main()