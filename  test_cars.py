import requests
from bs4 import BeautifulSoup
import re

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "fa-IR,fa;q=0.9",
}

cars = [
    ("شاهین اتوماتیک", "/profile/khodro-shahin-auto"),
    ("پژو ۲۰۷ اتوماتیک", "/profile/khodro-peugeot-207-auto"),
    ("دنا پلاس توربو اتوماتیک", "/profile/khodro-dena-plus-turbo-auto"),
    ("تارا اتوماتیک", "/profile/khodro-tara-auto"),
    ("سورن پلاس", "/profile/khodro-soren-plus"),
    ("ساینا S", "/profile/khodro-saina-s"),
    ("شاهین دنده‌ای", "/profile/khodro-shahin"),
    ("تیگو ۷ پرو", "/profile/khodro-tiggo7pro"),
]

for name, path in cars:
    try:
        url = f"https://www.tgju.org{path}"
        r = requests.get(url, headers=headers, timeout=15)
        print(f"{name}: Status {r.status_code}")
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            text = soup.get_text(" ", strip=True)
            match = re.search(r"نرخ فعلی\s*[:：]?\s*([\d,٬.]+)", text)
            if match:
                val = float(match.group(1).replace(",", "").replace("٬", ""))
                print(f"  ✅ قیمت: {val:,.0f}")
            else:
                print(f"  ❌ قیمت پیدا نشد")
    except Exception as e:
        print(f"  Error: {e}")
