import os
import asyncio
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from datetime import datetime

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8864763894:AAE6eYrof1hvVFVfzZxbJXMnwl-aq_Opow0")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@tala_arz_irr")
UPDATE_INTERVAL = 300

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://tgju.org/"
}

def fetch_tgju(slug):
    try:
        url = f"https://tgju.org/widget/indicator/{slug}"
        r = requests.get(url, headers=HEADERS, timeout=15)
        data = r.json()
        price = data.get("data", {}).get("info", {}).get("p", None)
        if not price:
            price = data.get("current", {}).get("p", None)
        return str(price) if price else None
    except Exception as e:
        logger.error(f"tgju widget error for {slug}: {e}")
        return None

def fetch_crypto_coingecko(coin_id):
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
        r = requests.get(url, timeout=15)
        data = r.json()
        price = data.get(coin_id, {}).get("usd")
        if price:
            return f"{price:,.2f}"
        return None
    except Exception as e:
        logger.error(f"CoinGecko error for {coin_id}: {e}")
        return None

def fetch_metals_frankfurter():
    """دریافت قیمت اونس از API رایگان"""
    try:
        # قیمت اونس طلا از metals-api
        url = "https://api.metals.live/v1/spot"
        r = requests.get(url, timeout=15)
        data = r.json()
        result = {}
        for item in data:
            if "gold" in item:
                result["gold_ounce"] = f"{item['gold']:,.2f}"
            if "silver" in item:
                result["silver_ounce"] = f"{item['silver']:,.2f}"
        return result
    except Exception as e:
        logger.error(f"Metals API error: {e}")
        return {}

def fetch_all_prices():
    prices = {}

    # کریپتو از CoinGecko (رایگان و بدون نیاز به کلید)
    prices["bitcoin"] = {
        "label": "بیت‌کوین",
        "price": fetch_crypto_coingecko("bitcoin") or "---",
        "unit": "دلار"
    }
    prices["tether"] = {
        "label": "تتر",
        "price": fetch_crypto_coingecko("tether") or "1.00",
        "unit": "دلار"
    }

    # فلزات
    metals = fetch_metals_frankfurter()
    prices["gold_ounce"] = {
        "label": "اونس جهانی طلا",
        "price": metals.get("gold_ounce", "---"),
        "unit": "دلار"
    }
    prices["silver_ounce"] = {
        "label": "اونس نقره",
        "price": metals.get("silver_ounce", "---"),
        "unit": "دلار"
    }

    # قیمت‌های ایرانی از tgju
    tgju_map = {
        "gold_18":     ("طلای ۱۸ عیار",   "price_gram_18k",    "تومان"),
        "gold_24":     ("طلای ۲۴ عیار",   "price_gram_24k",    "تومان"),
        "silver_gram": ("نقره گرمی",       "price_gram_silver", "تومان"),
        "usd":         ("دلار",            "price_dollar_rl",   "ریال"),
        "eur":         ("یورو",            "price_eur",         "ریال"),
    }
    for key, (label, slug, unit) in tgju_map.items():
        raw = fetch_tgju(slug)
        if raw:
            try:
                num = float(str(raw).replace(",", ""))
                raw = f"{num:,.0f}"
            except:
                pass
        prices[key] = {"label": label, "price": raw or "---", "unit": unit}

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
    for k in ["gold_18", "gold_24", "gold_ounce", "silver_ounce", "silver_gram"]:
        p = prices.get(k, {})
        lines.append(f"• {p.get('label','')}: `{p.get('price','---')}` {p.get('unit','')}")

    lines += ["", "━━━━━━━━━━━━━━━━━━", "💰 *ارز دیجیتال*"]
    for k in ["bitcoin", "tether"]:
        p = prices.get(k, {})
        lines.append(f"• {p.get('label','')}: `{p.get('price','---')}` {p.get('unit','')}")

    lines += ["", "━━━━━━━━━━━━━━━━━━", "💵 *ارزهای خارجی*"]
    for k in ["usd", "eur"]:
        p = prices.get(k, {})
        lines.append(f"• {p.get('label','')}: `{p.get('price','---')}` {p.get('unit','')}")

    lines += ["", "━━━━━━━━━━━━━━━━━━", "🤖 @tala\\_arz\\_irr"]
    return "\n".join(lines)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📊 همه قیمت‌ها", callback_data="prices")],
        [InlineKeyboardButton("🥇 طلا و نقره", callback_data="gold"),
         InlineKeyboardButton("💰 کریپتو", callback_data="crypto")],
        [InlineKeyboardButton("💵 ارز", callback_data="fiat")],
    ]
    await update.message.reply_text(
        "سلام! 👋\nبه ربات قیمت طلا و ارز خوش اومدی.\nاز منوی زیر انتخاب کن:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⏳ در حال دریافت قیمت‌ها...")
    prices = fetch_all_prices()

    if query.data == "prices":
        msg = format_message(prices)
    elif query.data == "gold":
        lines = ["🥇 *فلزات گرانبها*\n"]
        for k in ["gold_18", "gold_24", "gold_ounce", "silver_ounce", "silver_gram"]:
            p = prices.get(k, {})
            lines.append(f"• {p.get('label','')}: `{p.get('price','---')}` {p.get('unit','')}")
        msg = "\n".join(lines)
    elif query.data == "crypto":
        lines = ["💰 *ارزهای دیجیتال*\n"]
        for k in ["bitcoin", "tether"]:
            p = prices.get(k, {})
            lines.append(f"• {p.get('label','')}: `{p.get('price','---')}` {p.get('unit','')}")
        msg = "\n".join(lines)
    elif query.data == "fiat":
        lines = ["💵 *ارزهای خارجی*\n"]
        for k in ["usd", "eur"]:
            p = prices.get(k, {})
            lines.append(f"• {p.get('label','')}: `{p.get('price','---')}` {p.get('unit','')}")
        msg = "\n".join(lines)

    await query.edit_message_text(msg, parse_mode="Markdown")

async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ در حال دریافت قیمت‌ها...")
    prices = fetch_all_prices()
    msg = format_message(prices)
    await update.message.reply_text(msg, parse_mode="Markdown")

async def send_to_channel(context: ContextTypes.DEFAULT_TYPE):
    try:
        prices = fetch_all_prices()
        msg = format_message(prices)
        await context.bot.send_message(chat_id=CHANNEL_ID, text=msg, parse_mode="Markdown")
        logger.info("Channel updated successfully")
    except Exception as e:
        logger.error(f"Error sending to channel: {e}")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("price", price_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.job_queue.run_repeating(send_to_channel, interval=UPDATE_INTERVAL, first=10)
    logger.info("Bot started!")
    app.run_polling()

if __name__ == "__main__":
    main()
