import requests
import os
from datetime import date
from dotenv import load_dotenv
from db import get_connection, init_db

load_dotenv()

FRED_API_KEY = os.getenv("FRED_API_KEY")
BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

# 取得対象シリーズ
SERIES = {
    "SP500": "sp500",
    "VIXCLS": "vix",
    "DFF": "fed_funds_rate",
    "CPIAUCSL": "cpi",
    "T10YIE": "inflation_expectation",
    "DGS10": "us_10y_yield",
    "DEXJPUS": "usdjpy",          # 円建て資産の伸びを左右するので日次で持つ
    "CP": "corp_profits",         # 法人企業利益（四半期）。「見るべきは企業の稼ぐ力」の裏づけ
}

def init_fred_table():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fred_data (
            date TEXT,
            series TEXT,
            value REAL,
            PRIMARY KEY (date, series)
        )
    """)
    conn.commit()
    conn.close()

# ドローダウンを5年窓で測るため、日次系列は10年ぶん取る
# （FRED の SP500 系列自体が直近10年しか持たない）
DEFAULT_START = date(date.today().year - 10, 1, 1).isoformat()


def fetch_series(series_id, start=DEFAULT_START):
    res = requests.get(BASE_URL, params={
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "observation_start": start,
    })
    data = res.json()
    return data["observations"]

def save_series(observations, series_name):
    conn = get_connection()
    cur = conn.cursor()
    count = 0
    for obs in observations:
        if obs["value"] == ".":
            continue
        cur.execute("""
            INSERT OR IGNORE INTO fred_data (date, series, value)
            VALUES (?, ?, ?)
        """, (obs["date"], series_name, float(obs["value"])))
        count += 1
    conn.commit()
    conn.close()
    return count

if __name__ == "__main__":
    init_fred_table()
    for series_id, series_name in SERIES.items():
        obs = fetch_series(series_id)
        count = save_series(obs, series_name)
        latest = next((o for o in reversed(obs) if o["value"] != "."), None)
        print(f"{series_name}: {latest['value']} ({latest['date']}) → {count}件保存")