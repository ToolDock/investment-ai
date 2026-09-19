import requests
import os
from dotenv import load_dotenv
from db import get_connection

load_dotenv()

ESTAT_API_KEY = os.getenv("ESTAT_API_KEY")
BASE_URL = "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsData"

# 取得対象統計
SERIES = {
    "CPI": "0003427113",        # 消費者物価指数（総合）
    "UNEMPLOYMENT": "0003005865",  # 完全失業率
}

def init_estat_table():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS estat_data (
            date TEXT,
            series TEXT,
            value REAL,
            PRIMARY KEY (date, series)
        )
    """)
    conn.commit()
    conn.close()

def fetch_estat(stats_data_id):
    res = requests.get(BASE_URL, params={
        "appId": ESTAT_API_KEY,
        "statsDataId": stats_data_id,
        "startPosition": 1,
        "limit": 24,
        "metaGetFlg": "N",
        "cntGetFlg": "N",
    })
    return res.json()

def save_estat(data, series_name):
    conn = get_connection()
    cur = conn.cursor()
    count = 0
    try:
        values = data["GET_STATS_DATA"]["STATISTICAL_DATA"]["DATA_INF"]["VALUE"]
        for item in values:
            date_str = item.get("@time", "").replace("-", "")[:6]
            if not date_str or item.get("$") in ("", "-"):
                continue
            # YYYYMM → YYYY-MM
            formatted = f"{date_str[:4]}-{date_str[4:6]}"
            cur.execute("""
                INSERT OR IGNORE INTO estat_data (date, series, value)
                VALUES (?, ?, ?)
            """, (formatted, series_name, float(item["$"])))
            count += 1
    except KeyError:
        print(f"{series_name}: データ構造が想定外")
    conn.commit()
    conn.close()
    return count

if __name__ == "__main__":
    init_estat_table()
    for series_name, stats_id in SERIES.items():
        data = fetch_estat(stats_id)
        count = save_estat(data, series_name)
        print(f"{series_name}: {count}件保存")