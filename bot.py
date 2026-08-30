import os
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from datetime import datetime
import pytz

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8864763894:AAE6eYrof1hvVFVfzZxbJXMnwl-aq_Opow0")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@tala_arz_irr")
BRSAPI_KEY = os.environ.get("BRSAPI_KEY", "BxHwktsGdRAuqvjmJQMDGh3p2xPmqy5K")
UPDATE_INTERVAL = 300

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
IRAN_TZ = pytz.timezone("Asia/Tehran")

def get_iran_time():
    return datetime.now(IRAN_TZ).strftime("%Y/%m/%d - %H:%M")

def fmt(val):
    try:
        return f"{int(str(val).replace(',', '')):,}"
    except:
        return str(val) if val else "---"

def fetch_all_prices():
    prices = {}
    headers = {"User-Agent": "Mozilla/5.0"}

    # طلا، ارز، سکه از BrsApi
    try:
        r = requests.get(
            f"https://Api.BrsApi.ir/Market/Gold_Currency.php?key={BRSAPI_KEY}",
            headers=headers, timeout=15
        )
        data = r.json()
        logger.info(f"BrsApi Gold_Currency keys: {list(data.keys())[:10]}")

        # طلا
        prices["gold_18"] = {"label": "طلای ۱۸ عیار (گرم)", "price": fmt(data.get("geram18") or data.get("gold_18")), "unit": "تومان"}
        prices["gold_24"] = {"label": "طلای ۲۴ عیار (گرم)", "price": fmt(data.get("geram24") or data.get("gold_24")), "unit": "تومان"}
        prices["gold_mesghal"] = {"label": "مثقال طلا", "price": fmt(data.get("mesghal") or data.get("gold_mesghal")), "unit": "تومان"}
        prices["gold_abshode"] = {"label": "طلای آبشده", "price": fmt(data.get("abshodeh") or data.get("gold_abshode") or data.get("abshode")), "unit": "تومان"}
        prices["gold_ounce"] = {"label": "اونس جهانی طلا", "price": fmt(data.get("ons") or data.get("gold_ounce") or data.get("ounce")), "unit": "دلار"}

        # ارز
        prices["usd"] = {"label": "دلار آمریکا", "price": fmt(data.get("usd") or data.get("dollar")), "unit": "تومان"}
        prices["eur"] = {"label": "یورو", "price": fmt(data.get("eur") or data.get("euro")), "unit": "تومان"}

        # سکه
        prices["sekke_emami"] = {"label": "سکه امامی", "price": fmt(data.get("sekee_emami") or data.get("coin_emami")), "unit": "تومان"}
        prices["sekke_nim"] = {"label": "نیم سکه", "price": fmt(data.get("nim") or data.get("coin_nim")), "unit": "تومان"}

    except Exception as e:
        logger.error(f"BrsApi Gold error: {e}")
        for k in ["gold_18","gold_24","gold_mesghal","gold_abshode","gold_ounce","usd","eur","sekke_emami","sekke_nim"]:
            prices[k] = {"label": k, "price": "---", "unit": ""}

    # کریپتو از BrsApi
    try:
        r = requests.get(
            f"https://Api.BrsApi.ir/Market/Cryptocurrency.php?key={BRSAPI_KEY}",
            headers=headers, timeout=15
        )
        data = r.json()
        logger.info(f"BrsApi Crypto keys: {list(data.keys())[:10]}")

        prices["bitcoin"] = {"label": "بیت‌کوین", "price": fmt(data.get("bitcoin") or data.get("btc")), "unit": "دلار"}
        prices["ethereum"] = {"label": "اتریوم", "price": fmt(data.get("ethereum") or data.get("eth")), "unit": "دلار"}
        prices["tether"] = {"label": "تتر", "price": fmt(data.get("tether") or data.get("usdt")), "unit": "تومان"}

    except Exception as e:
        logger.error(f"BrsApi Crypto error: {e}")
        prices["bitcoin"] = {"label": "بیت‌کوین", "price": "---", "unit": "دلار"}
        prices["ethereum"] = {"label": "اتریوم", "price": "---", "unit": "دلار"}
        prices["tether"] = {"label": "تتر", "price": "---", "unit": "تومان"}

    return prices

def format_message(prices):
    now = get_iran_time()
    lines = [
        "📊 *قیمت‌های لحظه‌ای بازار*",
        f"🕐 آخرین به‌روزرسانی: `{now}`",
        "",
        "━━━━━━━━━━━━━━━━━━",
        "🥇 *فلزات گرانبها*",
    ]
    for k in ["gold_18", "gold_24", "gold_abshode", "gold_mesghal", "gold_ounce"]:
        p = prices.get(k, {})
        lines.append(f"• {p.get('label','')}: `{p.get('price','---')}` {p.get('unit','')}")

    lines += ["", "━━━━━━━━━━━━━━━━━━", "🪙 *سکه*"]
    for k in ["sekke_emami", "sekke_nim"]:
        p = prices.get(k, {})
        lines.append(f"• {p.get('label','')}: `{p.get('price','---')}` {p.get('unit','')}")

    lines += ["", "━━━━━━━━━━━━━━━━━━", "💰 *ارز دیجیتال*"]
    for k in ["bitcoin", "ethereum", "tether"]:
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
        [InlineKeyboardButton("🥇 طلا و سکه", callback_data="gold"),
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
        lines = ["🥇 *طلا و سکه*\n"]
        for k in ["gold_18","gold_24","gold_abshode","gold_mesghal","gold_ounce","sekke_emami","sekke_nim"]:
            p = prices.get(k, {})
            lines.append(f"• {p.get('label','')}: `{p.get('price','---')}` {p.get('unit','')}")
        msg = "\n".join(lines)
    elif query.data == "crypto":
        lines = ["💰 *ارزهای دیجیتال*\n"]
        for k in ["bitcoin", "ethereum", "tether"]:
            p = prices.get(k, {})
            lines.append(f"• {p.get('label','')}: `{p.get('price','---')}` {p.get('unit','')}")
        msg = "\n".join(lines)
    elif query.data == "fiat":
        lines = ["💵 *ارزهای خارجی*\n"]
        for k in ["usd", "eur"]:
            p = prices.get(k, {})
            lines.append(f"• {p.get('label','')}: `{p.get('price','---')}` {p.get('unit','')}")
        msg = "\n".join(lines)
    else:
        msg = "خطا!"

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
