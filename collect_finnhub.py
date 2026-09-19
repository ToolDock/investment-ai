import requests
import os
from dotenv import load_dotenv
from db import get_connection, init_db

load_dotenv()

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
BASE_URL = "https://finnhub.io/api/v1"

def fetch_quote(symbol):
    # 指定シンボルの現在価格を取得
    res = requests.get(f"{BASE_URL}/quote", params={
        "symbol": symbol,
        "token": FINNHUB_API_KEY
    })
    data = res.json()
    return data.get("c")  # 現在値

def init_quotes_table():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS quotes (
            date TEXT,
            symbol TEXT,
            value REAL,
            PRIMARY KEY (date, symbol)
        )
    """)
    conn.commit()
    conn.close()

def save_quote(date, symbol, value):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR IGNORE INTO quotes (date, symbol, value)
        VALUES (?, ?, ?)
    """, (date, symbol, value))
    conn.commit()
    conn.close()

# 取得対象シンボル
symbols = {
    "NASDAQ": "QQQ",    # NASDAQ100 ETF
    "GOLD": "GLD",      # ゴールドETF
    "BTC": "BINANCE:BTCUSDT",  # ビットコイン
    "ACWI": "ACWI",     # オールカントリー
}

if __name__ == "__main__":
    from datetime import date
    init_quotes_table()

    today = date.today().isoformat()
    for name, symbol in symbols.items():
        value = fetch_quote(symbol)
        if value:
            save_quote(today, name, value)
            print(f"{name}: {value}")
        else:
            print(f"{name}: 取得失敗")