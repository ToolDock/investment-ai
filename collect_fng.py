import requests
from datetime import date
from db import get_connection

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://edition.cnn.com/",
    "Origin": "https://edition.cnn.com"
}

def init_fng_table():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fear_greed (
            date TEXT,
            type TEXT,
            value REAL,
            classification TEXT,
            PRIMARY KEY (date, type)
        )
    """)
    conn.commit()
    conn.close()

def fetch_stock_fng():
    # CNN公式F&G
    res = requests.get(
        "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
        headers=HEADERS
    )
    data = res.json()
    fg = data["fear_and_greed"]
    return round(fg["score"], 1), fg["rating"]

def fetch_crypto_fng():
    # 暗号資産F&G（alternative.me）
    res = requests.get("https://api.alternative.me/fng/")
    data = res.json()
    item = data["data"][0]
    return int(item["value"]), item["value_classification"]

def save_fng(date_str, type_str, value, classification):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO fear_greed (date, type, value, classification)
        VALUES (?, ?, ?, ?)
    """, (date_str, type_str, value, classification))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_fng_table()
    today = date.today().isoformat()

    stock_value, stock_label = fetch_stock_fng()
    print(f"株式F&G: {stock_value} ({stock_label})")
    save_fng(today, "stock", stock_value, stock_label)

    crypto_value, crypto_label = fetch_crypto_fng()
    print(f"暗号資産F&G: {crypto_value} ({crypto_label})")
    save_fng(today, "crypto", crypto_value, crypto_label)