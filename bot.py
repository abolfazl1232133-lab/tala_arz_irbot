import os
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from datetime import datetime
import pytz

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8864763894:AAE6eYrof1hvVFVfzZxbJXMnwl-aq_Opow0")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@tala_arz_irr")
UPDATE_INTERVAL = 300

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

IRAN_TZ = pytz.timezone("Asia/Tehran")

def get_iran_time():
    return datetime.now(IRAN_TZ).strftime("%Y/%m/%d - %H:%M")

def fetch_all_prices():
    prices = {}

    # ارزهای دیجیتال - CoinGecko
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,tether&vs_currencies=usd"
        r = requests.get(url, timeout=15)
        data = r.json()
        prices["bitcoin"] = {"label": "بیت‌کوین", "price": f"{data['bitcoin']['usd']:,.0f}", "unit": "دلار"}
        prices["tether"] = {"label": "تتر", "price": f"{data['tether']['usd']:,.2f}", "unit": "دلار"}
        prices["ethereum"] = {"label": "اتریوم", "price": f"{data['ethereum']['usd']:,.0f}", "unit": "دلار"}
    except Exception as e:
        logger.error(f"CoinGecko error: {e}")
        prices["bitcoin"] = {"label": "بیت‌کوین", "price": "---", "unit": "دلار"}
        prices["tether"] = {"label": "تتر", "price": "---", "unit": "دلار"}
        prices["ethereum"] = {"label": "اتریوم", "price": "---", "unit": "دلار"}

    # اونس طلا و نقره - از Metals-API رایگان
    try:
        r = requests.get("https://api.metals.live/v1/spot/gold", timeout=15)
        data = r.json()
        gold_price = data[0].get("gold") if isinstance(data, list) else data.get("gold")
        if gold_price:
            prices["gold_ounce"] = {"label": "اونس جهانی طلا", "price": f"{float(gold_price):,.2f}", "unit": "دلار"}
        else:
            prices["gold_ounce"] = {"label": "اونس جهانی طلا", "price": "---", "unit": "دلار"}
    except Exception as e:
        logger.error(f"Gold metals.live error: {e}")
        # fallback
        try:
            r = requests.get("https://api.metals.live/v1/spot", timeout=15)
            data = r.json()
            for item in data:
                if isinstance(item, dict) and "gold" in item:
                    prices["gold_ounce"] = {"label": "اونس جهانی طلا", "price": f"{float(item['gold']):,.2f}", "unit": "دلار"}
                    break
        except:
            prices["gold_ounce"] = {"label": "اونس جهانی طلا", "price": "---", "unit": "دلار"}

    try:
        r = requests.get("https://api.metals.live/v1/spot/silver", timeout=15)
        data = r.json()
        silver_price = data[0].get("silver") if isinstance(data, list) else data.get("silver")
        if silver_price:
            prices["silver_ounce"] = {"label": "اونس نقره", "price": f"{float(silver_price):,.2f}", "unit": "دلار"}
        else:
            prices["silver_ounce"] = {"label": "اونس نقره", "price": "---", "unit": "دلار"}
    except Exception as e:
        logger.error(f"Silver error: {e}")
        prices["silver_ounce"] = {"label": "اونس نقره", "price": "---", "unit": "دلار"}

    # دلار و یورو به تومان - از navasan.tech (قیمت بازار آزاد ایران)
    try:
        r = requests.get("https://api.navasan.tech/latest/?api_key=free&item=usd,eur", timeout=15)
        data = r.json()
        usd = data.get("usd", {}).get("value")
        eur = data.get("eur", {}).get("value")
        if usd:
            prices["usd"] = {"label": "دلار آمریکا", "price": f"{int(usd):,}", "unit": "تومان"}
        else:
            prices["usd"] = {"label": "دلار آمریکا", "price": "---", "unit": "تومان"}
        if eur:
            prices["eur"] = {"label": "یورو", "price": f"{int(eur):,}", "unit": "تومان"}
        else:
            prices["eur"] = {"label": "یورو", "price": "---", "unit": "تومان"}
    except Exception as e:
        logger.error(f"Navasan error: {e}")
        # fallback به open.er-api
        try:
            r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=15)
            data = r.json()
            rates = data.get("rates", {})
            irr_rate = rates.get("IRR", 0)
            eur_rate = rates.get("EUR", 0)
            if irr_rate:
                toman = irr_rate / 10
                prices["usd"] = {"label": "دلار آمریکا", "price": f"{toman:,.0f}", "unit": "تومان"}
            if eur_rate and irr_rate:
                eur_toman = (irr_rate / eur_rate) / 10
                prices["eur"] = {"label": "یورو", "price": f"{eur_toman:,.0f}", "unit": "تومان"}
        except:
            prices["usd"] = {"label": "دلار آمریکا", "price": "---", "unit": "تومان"}
            prices["eur"] = {"label": "یورو", "price": "---", "unit": "تومان"}

    # محاسبه طلای ایرانی از اونس × دلار
    try:
        gold_str = prices.get("gold_ounce", {}).get("price", "---")
        usd_str = prices.get("usd", {}).get("price", "---")
        if gold_str != "---" and usd_str != "---":
            gold_usd = float(gold_str.replace(",", ""))
            usd_toman = float(usd_str.replace(",", ""))
            gram_toman = (gold_usd * usd_toman) / 31.1035
            gold_18 = gram_toman * 0.75
            gold_24 = gram_toman
            prices["gold_18"] = {"label": "طلای ۱۸ عیار (گرم)", "price": f"{gold_18:,.0f}", "unit": "تومان"}
            prices["gold_24"] = {"label": "طلای ۲۴ عیار (گرم)", "price": f"{gold_24:,.0f}", "unit": "تومان"}
        else:
            prices["gold_18"] = {"label": "طلای ۱۸ عیار (گرم)", "price": "---", "unit": "تومان"}
            prices["gold_24"] = {"label": "طلای ۲۴ عیار (گرم)", "price": "---", "unit": "تومان"}
    except Exception as e:
        logger.error(f"Gold calc error: {e}")
        prices["gold_18"] = {"label": "طلای ۱۸ عیار (گرم)", "price": "---", "unit": "تومان"}
        prices["gold_24"] = {"label": "طلای ۲۴ عیار (گرم)", "price": "---", "unit": "تومان"}

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
    for k in ["gold_18", "gold_24", "gold_ounce", "silver_ounce"]:
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
        for k in ["gold_18", "gold_24", "gold_ounce", "silver_ounce"]:
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
