# -*- coding: utf-8 -*-
"""
Tursoへの接続だけを単体で確認する使い捨てスクリプト。
本体（Streamlitアプリ）を動かす前に、まずこれだけで疎通確認する。

実行前に環境変数を設定しておくこと:
    $env:TURSO_CONNECTION_URL = "libsql://..."
    $env:TURSO_AUTH_TOKEN = "..."

実行: python test_turso_connection.py
"""
import os
import sys

url = os.environ.get("TURSO_CONNECTION_URL")
token = os.environ.get("TURSO_AUTH_TOKEN")

if not url or not token:
    print("エラー: 環境変数 TURSO_CONNECTION_URL / TURSO_AUTH_TOKEN が設定されていません。")
    print("PowerShellで $env:TURSO_CONNECTION_URL と $env:TURSO_AUTH_TOKEN を")
    print("先に設定してから、もう一度このスクリプトを実行してください。")
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

print("テストテーブルを作成し、1行書き込んでみます...")
try:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS connection_test "
        "(id INTEGER PRIMARY KEY AUTOINCREMENT, note TEXT)"
    )
    conn.execute("INSERT INTO connection_test (note) VALUES (?)", ("接続テスト成功",))
    conn.commit()
    print("書き込みに成功しました。")
except Exception as e:
    print(f"書き込みに失敗しました: {e}")
    sys.exit(1)

print("書き込んだ内容を読み出してみます...")
try:
    rows = list(conn.execute("SELECT id, note FROM connection_test ORDER BY id DESC LIMIT 3"))
    print("直近の書き込み:")
    for row in rows:
        print("  ", row)
except Exception as e:
    print(f"読み出しに失敗しました: {e}")
    sys.exit(1)

print()
print("=== すべて成功しました。Tursoへの接続・書き込み・読み出しが正常に動いています。 ===")
