import os
import sqlite3

# どのディレクトリから実行しても同じDBを見るように、このファイルの場所を基準にする
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "investment_ai.db")

def get_connection():
    # DBファイルに接続（なければ自動作成）
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    # S&P500テーブル
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sp500 (
            date TEXT PRIMARY KEY,
            value REAL
        )
    """)
    conn.commit()
    conn.close()
    print("DB初期化完了")

if __name__ == "__main__":
    init_db()