import requests
import os
from datetime import date, timedelta
from dotenv import load_dotenv
from db import get_connection

load_dotenv()

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
BASE_URL = "https://finnhub.io/api/v1"

def init_news_table():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS news (
            id TEXT PRIMARY KEY,
            date TEXT,
            headline TEXT,
            source TEXT,
            category TEXT
        )
    """)
    conn.commit()
    conn.close()

def fetch_news():
    # 直近2日分の市場ニュース見出しを取得
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=2)).isoformat()
    res = requests.get(f"{BASE_URL}/news", params={
        "category": "general",
        "from": yesterday,
        "to": today,
        "token": FINNHUB_API_KEY
    })
    return res.json()

def save_news(articles):
    conn = get_connection()
    cur = conn.cursor()
    count = 0
    for article in articles:
        cur.execute("""
            INSERT OR IGNORE INTO news (id, date, headline, source, category)
            VALUES (?, ?, ?, ?, ?)
        """, (
            str(article["id"]),
            date.fromtimestamp(article["datetime"]).isoformat(),
            article["headline"],
            article["source"],
            article["category"]
        ))
        count += 1
    conn.commit()
    conn.close()
    return count

if __name__ == "__main__":
    init_news_table()
    articles = fetch_news()
    count = save_news(articles)
    print(f"{count}件保存しました")
    for a in articles[:3]:
        print(f"・{a['headline']}")