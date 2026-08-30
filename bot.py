import os
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

def fetch_all_prices():
    prices = {}

    # ارزهای دیجیتال - CoinGecko رایگان
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

    # اونس طلا و نقره - Frankfurter + محاسبه
    try:
        # قیمت اونس از یه API رایگان دیگه
        r = requests.get("https://api.frankfurter.app/latest?from=USD&to=EUR", timeout=10)
        usd_eur = r.json().get("rates", {}).get("EUR", 0.92)

        # قیمت طلا از Open Exchange
        r2 = requests.get("https://openexchangerates.org/api/latest.json?app_id=&base=USD", timeout=10)
        # fallback به یه API ساده‌تر
        raise Exception("use alternative")
    except:
        try:
            # GoldAPI - رایگان بدون کلید
            r = requests.get(
                "https://api.gold-api.com/price/XAU",
                headers={"x-access-token": "goldapi-free"},
                timeout=15
            )
            data = r.json()
            gold_price = data.get("price", 0)
            if gold_price:
                prices["gold_ounce"] = {"label": "اونس جهانی طلا", "price": f"{gold_price:,.2f}", "unit": "دلار"}
            else:
                prices["gold_ounce"] = {"label": "اونس جهانی طلا", "price": "---", "unit": "دلار"}
        except Exception as e:
            logger.error(f"Gold API error: {e}")
            prices["gold_ounce"] = {"label": "اونس جهانی طلا", "price": "---", "unit": "دلار"}

        try:
            r = requests.get(
                "https://api.gold-api.com/price/XAG",
                headers={"x-access-token": "goldapi-free"},
                timeout=15
            )
            data = r.json()
            silver_price = data.get("price", 0)
            if silver_price:
                prices["silver_ounce"] = {"label": "اونس نقره", "price": f"{silver_price:,.2f}", "unit": "دلار"}
            else:
                prices["silver_ounce"] = {"label": "اونس نقره", "price": "---", "unit": "دلار"}
        except Exception as e:
            logger.error(f"Silver API error: {e}")
            prices["silver_ounce"] = {"label": "اونس نقره", "price": "---", "unit": "دلار"}

    # قیمت دلار و یورو به تومان از exchangerate-api
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=15)
        data = r.json()
        rates = data.get("rates", {})
        # IRR به تومان تقسیم بر ۱۰
        irr_rate = rates.get("IRR", 0)
        eur_usd = rates.get("EUR", 0)
        if irr_rate:
            toman = irr_rate / 10
            prices["usd"] = {"label": "دلار آمریکا", "price": f"{toman:,.0f}", "unit": "تومان"}
            if eur_usd:
                eur_toman = (irr_rate / eur_usd) / 10
                prices["eur"] = {"label": "یورو", "price": f"{eur_toman:,.0f}", "unit": "تومان"}
            else:
                prices["eur"] = {"label": "یورو", "price": "---", "unit": "تومان"}
        else:
            prices["usd"] = {"label": "دلار آمریکا", "price": "---", "unit": "تومان"}
            prices["eur"] = {"label": "یورو", "price": "---", "unit": "تومان"}
    except Exception as e:
        logger.error(f"Exchange rate error: {e}")
        prices["usd"] = {"label": "دلار آمریکا", "price": "---", "unit": "تومان"}
        prices["eur"] = {"label": "یورو", "price": "---", "unit": "تومان"}

    # محاسبه قیمت طلای ایرانی بر اساس اونس و دلار
    try:
        gold_ounce_str = prices.get("gold_ounce", {}).get("price", "---")
        usd_str = prices.get("usd", {}).get("price", "---")
        if gold_ounce_str != "---" and usd_str != "---":
            gold_ounce_usd = float(gold_ounce_str.replace(",", ""))
            usd_toman = float(usd_str.replace(",", ""))
            # هر اونس = 31.1035 گرم
            gold_gram_toman = (gold_ounce_usd * usd_toman) / 31.1035
            gold_18 = gold_gram_toman * 0.75  # ۱۸ عیار = ۷۵٪
            gold_24 = gold_gram_toman  # ۲۴ عیار
            prices["gold_18"] = {"label": "طلای ۱۸ عیار (گرم)", "price": f"{gold_18:,.0f}", "unit": "تومان"}
            prices["gold_24"] = {"label": "طلای ۲۴ عیار (گرم)", "price": f"{gold_24:,.0f}", "unit": "تومان"}
        else:
            prices["gold_18"] = {"label": "طلای ۱۸ عیار (گرم)", "price": "---", "unit": "تومان"}
            prices["gold_24"] = {"label": "طلای ۲۴ عیار (گرم)", "price": "---", "unit": "تومان"}
    except Exception as e:
        logger.error(f"Gold calculation error: {e}")
        prices["gold_18"] = {"label": "طلای ۱۸ عیار (گرم)", "price": "---", "unit": "تومان"}
        prices["gold_24"] = {"label": "طلای ۲۴ عیار (گرم)", "price": "---", "unit": "تومان"}

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
