"""対話AI用の「自分のポートフォリオ」記録と、対話ログの保存。

ポートフォリオは本人（Frisk）ひとり分の自己申告なので、1行だけを更新し続ける単純な形にする
（群3のように毎ターン自動で状態を追跡するものではない。まずは対話AIそのものを鍛える段階のため）。
対話ログは、群3「提案AI対話」を本番で鍛える際に読み返せるよう、やり取りをすべて残す。
investment_ai.db（日報と同じDB）に格納する。

TURSO_PROD_CONNECTION_URL が設定されていれば、外部の永続DB（Turso／libSQL）につなぐ。
Streamlit Community Cloud等、ローカルファイルシステムが再起動のたびにリセットされる
環境に本番アプリを置くための切り替え（utils/storage.py の get_connection() と同じ考え方。
実験用のTURSO_CONNECTION_URLとは別の環境変数名にして、参加者データ用DBと本番の個人データ用
DBを取り違えないようにしてある）。ローカルでの開発・自分のPCでの動作確認では、この環境変数
を設定しなければ従来どおりローカルの investment_ai.db を使う（挙動は一切変えていない）。

investment_ai.db の他のテーブル（sp500・daily_report等、GitHub Actionsが毎朝収集・生成する
市況データ）はこの変更の対象外。あちらは引き続きローカルSQLite→git commitの経路のまま
（db.py・collect_*.py・generate_daily_report.py は変更していない）。my_portfolio・
dialogue_log の2テーブルだけが、ユーザーの実際の操作で貯まっていくデータであり、
クラウド上での永続化が要る（2026-09-23、本番のスマホ対応にあたって追加）。

Turso（libSQL）はSQLite自体のフォークでSQL文はそのまま互換だが、CHECK制約・
ON CONFLICT...DO UPDATE（upsert）が実際にTursoで動くかは、utils/storage.py同様
未検証（アカウント作成がこちらの環境からはできないため。TURSO_SETUP_PROD.md参照）。

sqlite3.Row（列名アクセス）はTursoの接続オブジェクトでは使えない可能性があるため、
utils/storage.py に合わせて全関数を位置引数（タプル）ベースのアクセスに統一している。
"""

import os
import sqlite3
from datetime import datetime

from db import DB_PATH


def _conn():
    turso_url = os.environ.get("TURSO_PROD_CONNECTION_URL")
    if turso_url:
        import turso_serverless
        return turso_serverless.connect(
            turso_url, auth_token=os.environ.get("TURSO_PROD_AUTH_TOKEN"))
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA busy_timeout = 5000")
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
        row = conn.execute(
            "SELECT cash, invested_value, cost_basis, updated_at "
            "FROM my_portfolio WHERE id = 1").fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {"cash": row[0], "invested_value": row[1], "cost_basis": row[2],
            "updated_at": row[3]}


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
    return [{"role": r[0], "content": r[1]} for r in rows]


def load_recent_days(before_date, n_days=5):
    """「今日」より前で、実際にやり取りのあった直近 n_days 日ぶんの対話ログを、
    日付の古い順・各日はやり取りの順で返す（＝会話の連続性のための短期記憶）。

    戻り値: [{"date": ..., "turns": [{"role":..., "content":...}, ...]}, ...]
    今日のログは含めない（今日ぶんは load_today_log 側で別に持っている）。
    """
    conn = _conn()
    try:
        dates = [r[0] for r in conn.execute(
            "SELECT DISTINCT report_date FROM dialogue_log WHERE report_date < ? "
            "ORDER BY report_date DESC LIMIT ?", (before_date, n_days)).fetchall()]
        dates.reverse()  # 古い順に並べ直す
        out = []
        for d in dates:
            rows = conn.execute(
                "SELECT role, content FROM dialogue_log WHERE report_date = ? ORDER BY id",
                (d,)).fetchall()
            out.append({"date": d,
                       "turns": [{"role": r[0], "content": r[1]} for r in rows]})
    finally:
        conn.close()
    return out
