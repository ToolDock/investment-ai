# 1段目のタスク（群2用／群3用）と、DBの群を突き合わせる。ローカル専用。
# 使い方: python check_task_vs_group.py
import csv
from collections import Counter

from payout_report import load_db

db = load_db()
for task, path in (("群2用タスク", "参加賞_群2.csv"), ("群3用タスク", "参加賞_群3.csv")):
    c, ng = Counter(), []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            code = (r.get("完了コード") or "").strip()
            g = db[code]["group"] if code in db else "番号なし"
            c[g] += 1
            if g not in (2, 3) or (task == "群2用タスク" and g != 2) or (task == "群3用タスク" and g != 3):
                ng.append((r.get("ワーカーID"), code, g))
    print(f"{task}: DBの群の内訳 {dict(c)}")
    for x in ng:
        print("   食い違い:", x)
