import requests
import os
from datetime import date, timedelta
from dotenv import load_dotenv
from db import get_connection

load_dotenv()

FMP_API_KEY = os.getenv("FMP_API_KEY")
BASE_URL = "https://financialmodelingprep.com/stable"

def init_sector_table():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sector_performance (
            date TEXT,
            sector TEXT,
            exchange TEXT,
            average_change REAL,
            PRIMARY KEY (date, sector, exchange)
        )
    """)
    conn.commit()
    conn.close()

def get_latest_trading_day():
    """最後に引けたセッションの日付。

    暦で today を渡すと、まだ引けていない日や祝日の分を取ってしまい、
    価格系列（FRED・Yahoo）とセクターの日付がずれる。
    すでに取れている S&P500 のクオートに合わせるのが確実。
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT session FROM market_quote WHERE symbol='^GSPC'").fetchone()
    except Exception:
        row = None
    finally:
        conn.close()
    if row and row[0]:
        return date.fromisoformat(row[0])

    # クオートがまだ無いときだけ、暦で当てる（土日は直前の金曜へ）
    today = date.today()
    if today.weekday() == 5:
        return today - timedelta(days=1)
    if today.weekday() == 6:
        return today - timedelta(days=2)
    return today

def fetch_sector_performance(target_date):
    res = requests.get(f"{BASE_URL}/sector-performance-snapshot", params={
        "apikey": FMP_API_KEY,
        "date": target_date.isoformat()
    })
    return res.json()

def save_sector_performance(data):
    conn = get_connection()
    cur = conn.cursor()
    count = 0
    for item in data:
        cur.execute("""
            INSERT OR IGNORE INTO sector_performance (date, sector, exchange, average_change)
            VALUES (?, ?, ?, ?)
        """, (item["date"], item["sector"], item["exchange"], item["averageChange"]))
        count += 1
    conn.commit()
    conn.close()
    print(f"{count}件保存しました")

if __name__ == "__main__":
    init_sector_table()
    target_date = get_latest_trading_day()
    print(f"取得日: {target_date}")
    data = fetch_sector_performance(target_date)
    if not data:
        print("データなし（休場日の可能性）")
    else:
        for item in data:
            print(f"{item['sector']} ({item['exchange']}): {item['averageChange']:.2f}%")
        save_sector_performance(data)