"""【一度だけ使う】GitHubに最初にpushする前に、investment_ai.db から
自分専用のテーブル（my_portfolio, dialogue_log）の中身を一時的に空にするスクリプト。

なぜ必要か:
    プライベートリポジトリとはいえ、自分のポートフォリオ金額やAIとの会話履歴を
    GitHub上に置きたくない（セキュリティ・プライバシーへの配慮）。
    このスクリプトは「一時的に空にする → コミット → すぐ元に戻す」という
    2段階セットで使う。手元のデータは最終的に一切失われない。

使い方（このスクリプトの実行後、git add/commit/push は必ず自分の手で行うこと）:
    1) venv\Scripts\python.exe prepare_initial_commit.py clear
       → investment_ai.db 内の my_portfolio, dialogue_log が空になる
         （直前の中身は investment_ai.pre-commit-backup.db に退避される）
    2) git status で「何がコミットされるか」を必ず確認する
    3) git add . / git commit -m "..." / git push を自分で実行する
    4) venv\Scripts\python.exe prepare_initial_commit.py restore
       → 退避しておいた自分のデータを investment_ai.db に書き戻す
"""

import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "investment_ai.db"
BACKUP_PATH = ROOT / "investment_ai.pre-commit-backup.db"

USER_OWNED_TABLES = ["my_portfolio", "dialogue_log"]


def clear():
    if BACKUP_PATH.exists():
        print("退避ファイルが既に存在します。restore を先に実行してください。")
        sys.exit(1)
    shutil.copy2(DB_PATH, BACKUP_PATH)
    con = sqlite3.connect(DB_PATH)
    for table in USER_OWNED_TABLES:
        con.execute(f"DELETE FROM {table}")
    con.commit()
    con.close()
    print("my_portfolio / dialogue_log を空にしました。")
    print(f"（元の内容は {BACKUP_PATH.name} に退避済み）")
    print("この状態で git add / commit / push を行ってください。")


def restore():
    if not BACKUP_PATH.exists():
        print("退避ファイルが見つかりません。clear を先に実行したか確認してください。")
        sys.exit(1)
    con = sqlite3.connect(DB_PATH)
    con.execute(f"ATTACH DATABASE '{BACKUP_PATH.as_posix()}' AS backup")
    for table in USER_OWNED_TABLES:
        con.execute(f"DELETE FROM {table}")
        con.execute(f"INSERT INTO {table} SELECT * FROM backup.{table}")
    con.commit()
    con.close()
    BACKUP_PATH.unlink()
    print("my_portfolio / dialogue_log を元に戻しました。")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("clear", "restore"):
        print(__doc__)
        sys.exit(1)
    {"clear": clear, "restore": restore}[sys.argv[1]]()
