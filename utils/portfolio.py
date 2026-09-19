"""対話AI用の「自分のポートフォリオ」記録と、対話ログの保存。

ポートフォリオは本人（Frisk）ひとり分の自己申告なので、1行だけを更新し続ける単純な形にする
（群3のように毎ターン自動で状態を追跡するものではない。まずは対話AIそのものを鍛える段階のため）。
対話ログは、群3「提案AI対話」を本番で鍛える際に読み返せるよう、やり取りをすべて残す。
investment_ai.db（日報と同じDB）に格納する。
"""

import sqlite3
from datetime import datetime

from db import DB_PATH


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_store():
    conn = _conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS my_portfolio (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            cash INTEGER,
            invested_value INTEGER,
            cost_basis INTEGER,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dialogue_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date TEXT,
            role TEXT,
            content TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def get_portfolio():
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM my_portfolio WHERE id = 1").fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def save_portfolio(cash, invested_value, cost_basis):
    conn = _conn()
    conn.execute("""
        INSERT INTO my_portfolio (id, cash, invested_value, cost_basis, updated_at)
        VALUES (1, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            cash=excluded.cash, invested_value=excluded.invested_value,
            cost_basis=excluded.cost_basis, updated_at=excluded.updated_at
    """, (cash, invested_value, cost_basis, datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    conn.close()


def log_turn(report_date, role, content):
    conn = _conn()
    conn.execute(
        "INSERT INTO dialogue_log (report_date, role, content, created_at) VALUES (?, ?, ?, ?)",
        (report_date, role, content, datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    conn.close()


def load_today_log(report_date):
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT role, content FROM dialogue_log WHERE report_date = ? ORDER BY id",
            (report_date,)).fetchall()
    finally:
        conn.close()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def load_recent_days(before_date, n_days=5):
    """「今日」より前で、実際にやり取りのあった直近 n_days 日ぶんの対話ログを、
    日付の古い順・各日はやり取りの順で返す（＝会話の連続性のための短期記憶）。

    戻り値: [{"date": ..., "turns": [{"role":..., "content":...}, ...]}, ...]
    今日のログは含めない（今日ぶんは load_today_log 側で別に持っている）。
    """
    conn = _conn()
    try:
        dates = [r["report_date"] for r in conn.execute(
            "SELECT DISTINCT report_date FROM dialogue_log WHERE report_date < ? "
            "ORDER BY report_date DESC LIMIT ?", (before_date, n_days)).fetchall()]
        dates.reverse()  # 古い順に並べ直す
        out = []
        for d in dates:
            rows = conn.execute(
                "SELECT role, content FROM dialogue_log WHERE report_date = ? ORDER BY id",
                (d,)).fetchall()
            out.append({"date": d,
                       "turns": [{"role": r["role"], "content": r["content"]} for r in rows]})
    finally:
        conn.close()
    return out
