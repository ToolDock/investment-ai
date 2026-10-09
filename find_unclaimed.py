# CSVに出てこない完了者（コードが未提出・誤入力）を探す。ローカル専用。
# 使い方: python find_unclaimed.py 参加賞_群2.csv 参加賞_群3.csv S.csv A.csv B.csv C.csv D.csv
import csv
import sys

from payout_report import load_db
from utils.rank import reward_rank

used = set()
for p in sys.argv[1:]:
    with open(p, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            used.add((r.get("完了コード") or "").strip())

db = load_db()
print("DBの完了者のうち、CSVに出てこない人（完了コード／群／ランク／同意／完了）")
for code, d in sorted(db.items(), key=lambda x: x[1]["survey_done_at"] or ""):
    if d["survey_done_at"] and code not in used:
        print(code, d["group"], reward_rank(d["reward"]) if d["reward"] is not None else "-",
              d["consented_at"], d["survey_done_at"])
