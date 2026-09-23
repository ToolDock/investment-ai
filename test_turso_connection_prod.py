# -*- coding: utf-8 -*-
"""
本番用Turso(TURSO_PROD_CONNECTION_URL)への接続だけを単体で確認する使い捨てスクリプト。
実験用の test_turso_connection.py と同じ考え方だが、こちらは production_app 側
(utils/portfolio.py の _conn())が実際に使う環境変数名・テーブル構造で確認する。

utils/portfolio.py のdocstringに「CHECK制約・ON CONFLICT...DO UPDATE(upsert)が
実際にTursoで動くかは未検証」とあるため、このテストでは my_portfolio と同じ
CHECK制約付きのテーブル・upsert文をそのまま使って確認する(汎用のテストテーブル
ではなく、本番が実際に使う形そのものを検証する)。

実行前に環境変数を設定しておくこと:
    $env:TURSO_PROD_CONNECTION_URL = "libsql://..."
    $env:TURSO_PROD_AUTH_TOKEN = "..."

実行: python test_turso_connection_prod.py
"""
import os
import sys

url = os.environ.get("TURSO_PROD_CONNECTION_URL")
token = os.environ.get("TURSO_PROD_AUTH_TOKEN")

if not url or not token:
    print("エラー: 環境変数 TURSO_PROD_CONNECTION_URL / TURSO_PROD_AUTH_TOKEN が設定されていません。")
    print("PowerShellで $env:TURSO_PROD_CONNECTION_URL と $env:TURSO_PROD_AUTH_TOKEN を")
    print("先に設定してから、もう一度このスクリプトを実行してください。")
    print("(実験用の TURSO_CONNECTION_URL / TURSO_AUTH_TOKEN とは別物です。取り違えに注意)")
    sys.exit(1)

print(f"接続先: {url}")
print("turso_serverless をインポート中...")

try:
    import turso_serverless
except ImportError:
    print("エラー: turso_serverless がインストールされていません。")
    print("先に次を実行してください: venv\\Scripts\\pip.exe install turso_serverless")
    sys.exit(1)

print("接続を試みます...")
try:
    conn = turso_serverless.connect(url, auth_token=token)
    print("接続に成功しました。")
except Exception as e:
    print(f"接続に失敗しました: {e}")
    sys.exit(1)

print()
print("--- CHECK制約つきテーブルの作成(my_portfolioと同じ形) ---")
try:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS connection_test_prod ("
        "id INTEGER PRIMARY KEY CHECK (id = 1), "
        "note TEXT, "
        "updated_at TEXT)"
    )
    print("CHECK制約つきテーブルの作成に成功しました。")
except Exception as e:
    print(f"CHECK制約つきテーブルの作成に失敗しました: {e}")
    sys.exit(1)

print()
print("--- upsert(INSERT ... ON CONFLICT DO UPDATE)の動作確認 ---")
try:
    from datetime import datetime
    conn.execute(
        """
        INSERT INTO connection_test_prod (id, note, updated_at)
        VALUES (1, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            note=excluded.note, updated_at=excluded.updated_at
        """,
        ("1回目の書き込み", datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    print("1回目のupsertに成功しました。")

    conn.execute(
        """
        INSERT INTO connection_test_prod (id, note, updated_at)
        VALUES (1, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            note=excluded.note, updated_at=excluded.updated_at
        """,
        ("2回目の書き込み(上書き確認)", datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    print("2回目のupsert(上書き)に成功しました。")
except Exception as e:
    print(f"upsertに失敗しました: {e}")
    print("(もし失敗した場合、utils/portfolio.py の save_portfolio() も同じ書き方なので")
    print(" 同様のエラーになる可能性があります。エラー内容を控えて報告してください。)")
    sys.exit(1)

print()
print("--- 読み出し確認(位置引数アクセス) ---")
try:
    row = conn.execute(
        "SELECT id, note, updated_at FROM connection_test_prod WHERE id = 1"
    ).fetchone()
    if row is None:
        print("エラー: 書き込んだはずの行が読み出せませんでした。")
        sys.exit(1)
    print(f"  id={row[0]}, note={row[1]}, updated_at={row[2]}")
    if row[1] != "2回目の書き込み(上書き確認)":
        print("エラー: 上書きされた内容と一致しません(upsertが正しく動いていない可能性)。")
        sys.exit(1)
    print("読み出しに成功し、2回目の内容で正しく上書きされていることを確認しました。")
except Exception as e:
    print(f"読み出しに失敗しました: {e}")
    sys.exit(1)

print()
print("--- 後片付け(テストテーブルの削除) ---")
try:
    conn.execute("DROP TABLE connection_test_prod")
    conn.commit()
    print("テストテーブルを削除しました。")
except Exception as e:
    print(f"テストテーブルの削除に失敗しました(実害は無いので無視してよい): {e}")

print()
print("=== すべて成功しました。本番用Turso(TURSO_PROD_*)への接続・CHECK制約・upsert・読み出しが")
print("    正常に動いています。utils/portfolio.py の実際の書き方でも問題ないはずです。 ===")
