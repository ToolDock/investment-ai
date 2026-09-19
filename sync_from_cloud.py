"""クラウド（GitHub）が毎朝更新したデータを、手元のPCに安全に取り込むスクリプト。

    venv\Scripts\python.exe sync_from_cloud.py

やること（順番が重要）:
  1. 今の investment_ai.db から、自分専用のテーブル（my_portfolio, dialogue_log）だけを
     一時ファイルに退避する。
  2. investment_ai.db に対するローカルの変更を捨てて（git checkout）、
     git pull でクラウド（bot）が積み上げた最新のデータを取り込む。
  3. 退避しておいた my_portfolio, dialogue_log を、pull後のDBに書き戻す。
     → これらの2テーブルは collect_all.py / generate_daily_report.py が
       一切書き込まないテーブルなので、必ず「手元の内容の方が新しい・正しい」。
       クラウド側にどんな内容が入っていても、常に手元の内容で上書きする。

失敗した場合は investment_ai.db を一切変更せず、退避ファイルも残したまま終了する
（何度でもやり直せるようにするため）。
"""

import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "investment_ai.db"
BACKUP_PATH = ROOT / "investment_ai.local-backup.db"

# bot側のスクリプトが一切書き込まない、ユーザー専用のテーブル
USER_OWNED_TABLES = ["my_portfolio", "dialogue_log"]


def run(cmd, **kw):
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=ROOT, check=True, **kw)


def main():
    if not DB_PATH.exists():
        print("investment_ai.db が見つかりません。初回セットアップがまだの可能性があります。")
        sys.exit(1)

    # 1. 自分専用テーブルを退避
    print(f"[1/3] {DB_PATH.name} の my_portfolio / dialogue_log を退避中...")
    shutil.copy2(DB_PATH, BACKUP_PATH)

    # 2. git pull で最新を取り込む（手元の investment_ai.db への変更は一旦捨てる）
    print("[2/3] git pull でクラウドの最新データを取得中...")
    try:
        run(["git", "checkout", "--", "investment_ai.db"])
    except subprocess.CalledProcessError:
        pass  # 追跡されていない・差分がない場合はそのまま進む
    run(["git", "pull"])

    # 3. 自分専用テーブルを、pull後のDBに書き戻す
    print("[3/3] my_portfolio / dialogue_log を書き戻し中...")
    con = sqlite3.connect(DB_PATH)
    con.execute(f"ATTACH DATABASE '{BACKUP_PATH.as_posix()}' AS backup")
    for table in USER_OWNED_TABLES:
        has_backup_table = con.execute(
            "SELECT 1 FROM backup.sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if not has_backup_table:
            continue
        con.execute(f"DELETE FROM {table}")
        con.execute(f"INSERT INTO {table} SELECT * FROM backup.{table}")
    con.commit()
    con.close()

    BACKUP_PATH.unlink(missing_ok=True)
    print("完了しました。最新のデータ（自分のポートフォリオ・会話履歴はそのまま）に更新しました。")


if __name__ == "__main__":
    main()
