"""データ収集をまとめて1回だけ実行する。

    python collect_all.py

scheduler.py と同じ処理を、常駐せずに1回だけ回す。
出力は logs/collect_*.txt にも残る。
"""

from utils.runlog import tee

if __name__ == "__main__":
    path = tee("collect")
    from scheduler import collect_all
    collect_all()
    print(f"\nログ: {path}")
