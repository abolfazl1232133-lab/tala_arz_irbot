import os
import asyncio
import logging
import requests
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from datetime import datetime

# ==================== تنظیمات ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8864763894:AAE6eYrof1hvVFVfzZxbJXMnwl-aq_Opow0")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@tala_arz_irr")
UPDATE_INTERVAL = 300  # هر ۵ دقیقه یه بار به‌روزرسانی کانال

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== دریافت قیمت‌ها از tgju.org ====================
TGJU_ITEMS = {
    "gold_18":    ("طلای ۱۸ عیار",   "price_gram_18k",   "تومان"),
    "gold_24":    ("طلای ۲۴ عیار",   "price_gram_24k",   "تومان"),
    "gold_ounce": ("اونس جهانی طلا", "ounce",            "دلار"),
    "silver_ounce":("اونس نقره",      "silver",           "دلار"),
    "silver_gram":("نقره گرمی",       "price_gram_silver","تومان"),
    "bitcoin":    ("بیت‌کوین",        "bitcoin",          "دلار"),
    "tether":     ("تتر",             "tether",           "دلار"),
    "usd":        ("دلار",            "price_dollar_rl",  "ریال"),
    "eur":        ("یورو",            "price_eur",        "ریال"),
}

def fetch_prices():
    prices = {}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    for key, (label, slug, unit) in TGJU_ITEMS.items():
        try:
            url = f"https://api.tgju.org/v1/market/indicator/summary-table-data/{slug}"
            r = requests.get(url, headers=headers, timeout=10)
            data = r.json()
            price = data.get("current", {}).get("p", "---")
            # تبدیل عدد به فرمت خوانا
            try:
                price_num = float(str(price).replace(",", ""))
                if price_num > 1000:
                    price = f"{price_num:,.0f}"
                else:
                    price = f"{price_num:,.2f}"
            except:
                pass
            prices[key] = {"label": label, "price": price, "unit": unit}
        except Exception as e:
            prices[key] = {"label": label, "price": "---", "unit": unit}
            logger.error(f"Error fetching {key}: {e}")
    return prices

def format_message(prices):
    now = datetime.now().strftime("%Y/%m/%d - %H:%M")
    lines = [
        "📊 *قیمت‌های لحظه‌ای بازار*",
        f"🕐 آخرین به‌روزرسانی: `{now}`",
        "",
        "━━━━━━━━━━━━━━━━━━",
        "🥇 *فلزات گرانبها*",
    ]
    gold_keys = ["gold_18", "gold_24", "gold_ounce", "silver_ounce", "silver_gram"]
    for k in gold_keys:
        p = prices.get(k, {})
        lines.append(f"• {p.get('label','')}: `{p.get('price','---')}` {p.get('unit','')}")

    lines += ["", "━━━━━━━━━━━━━━━━━━", "💰 *ارز دیجیتال*"]
    crypto_keys = ["bitcoin", "tether"]
    for k in crypto_keys:
        p = prices.get(k, {})
        lines.append(f"• {p.get('label','')}: `{p.get('price','---')}` {p.get('unit','')}")

    lines += ["", "━━━━━━━━━━━━━━━━━━", "💵 *ارزهای خارجی*"]
    fiat_keys = ["usd", "eur"]
    for k in fiat_keys:
        p = prices.get(k, {})
        lines.append(f"• {p.get('label','')}: `{p.get('price','---')}` {p.get('unit','')}")

    lines += ["", "━━━━━━━━━━━━━━━━━━", "🤖 @tala\\_arz\\_irr"]
    return "\n".join(lines)

# ==================== هندلرهای ربات ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📊 دریافت قیمت‌ها", callback_data="prices")],
        [InlineKeyboardButton("🥇 طلا", callback_data="gold"),
         InlineKeyboardButton("💰 کریپتو", callback_data="crypto")],
        [InlineKeyboardButton("💵 ارز", callback_data="fiat")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "سلام! 👋\nبه ربات قیمت طلا و ارز خوش اومدی.\nاز منوی زیر انتخاب کن:",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    prices = fetch_prices()

    if query.data == "prices":
        msg = format_message(prices)
        await query.edit_message_text(msg, parse_mode="Markdown")

    elif query.data == "gold":
        lines = ["🥇 *قیمت فلزات گرانبها*\n"]
        for k in ["gold_18", "gold_24", "gold_ounce", "silver_ounce", "silver_gram"]:
            p = prices.get(k, {})
            lines.append(f"• {p.get('label','')}: `{p.get('price','---')}` {p.get('unit','')}")
        await query.edit_message_text("\n".join(lines), parse_mode="Markdown")

    elif query.data == "crypto":
        lines = ["💰 *قیمت ارزهای دیجیتال*\n"]
        for k in ["bitcoin", "tether"]:
            p = prices.get(k, {})
            lines.append(f"• {p.get('label','')}: `{p.get('price','---')}` {p.get('unit','')}")
        await query.edit_message_text("\n".join(lines), parse_mode="Markdown")

    elif query.data == "fiat":
        lines = ["💵 *قیمت ارزهای خارجی*\n"]
        for k in ["usd", "eur"]:
            p = prices.get(k, {})
            lines.append(f"• {p.get('label','')}: `{p.get('price','---')}` {p.get('unit','')}")
        await query.edit_message_text("\n".join(lines), parse_mode="Markdown")

async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ در حال دریافت قیمت‌ها...")
    prices = fetch_prices()
    msg = format_message(prices)
    await update.message.reply_text(msg, parse_mode="Markdown")

# ==================== ارسال خودکار به کانال ====================
async def send_to_channel(context: ContextTypes.DEFAULT_TYPE):
    try:
        prices = fetch_prices()
        msg = format_message(prices)
        await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=msg,
            parse_mode="Markdown"
        )
        logger.info("Channel updated successfully")
    except Exception as e:
        logger.error(f"Error sending to channel: {e}")

# ==================== اجرای ربات ====================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("price", price_command))
    app.add_handler(CallbackQueryHandler(button_handler))

    # ارسال خودکار به کانال هر ۵ دقیقه
    app.job_queue.run_repeating(send_to_channel, interval=UPDATE_INTERVAL, first=10)

    logger.info("Bot started!")
    app.run_polling()

if __name__ == "__main__":
    main()
