# -*- coding: utf-8 -*-
"""群の食い違い・重複参加の session_id を、exclude_sessions.txt に書き出す。ローカル専用。
使い方（Tursoの環境変数を設定した状態で）: python find_exclude_sessions.py
入力: 参加賞_群2.csv, 参加賞_群3.csv（ワーカーID・完了コード列）。
出力: exclude_sessions.txt（session_idと理由のみ。ワーカーIDは書かない）。画面にも、ワーカーIDは出さない。
"""
import csv
from collections import defaultdict

from utils.storage import get_connection

TASKS = (("参加賞_群2.csv", 2), ("参加賞_群3.csv", 3))


def read_rows(path):
    for enc in ("utf-8-sig", "cp932"):
        try:
            with open(path, encoding=enc, newline="") as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError:
            continue
    return []


def main():
    conn = get_connection()
    db = {}
    for code, sid, g, consented in conn.execute(
            """SELECT pr.resume_code, pr.session_id, p.group_no, ps.consented_at
               FROM progress pr JOIN participants p ON p.session_id = pr.session_id
               LEFT JOIN participant_status ps ON ps.session_id = pr.session_id
               WHERE pr.session_id NOT IN (SELECT session_id FROM test_sessions)""").fetchall():
        db[(code or "").strip().upper()] = {"sid": sid, "group": g, "t": consented or ""}
    conn.close()

    entries = []
    for path, task_group in TASKS:
        for r in read_rows(path):
            code = (r.get("完了コード") or "").strip().upper()
            worker = (r.get("ワーカーID") or "").strip()
            if code in db:
                entries.append({"worker": worker, "task": task_group, **db[code]})

    reasons = {}
    for e in entries:
        if e["group"] != e["task"]:
            reasons.setdefault(e["sid"], []).append(f"群の食い違い（タスク=群{e['task']}、DB=群{e['group']}）")
    by_worker = defaultdict(list)
    for e in entries:
        if e["worker"]:
            by_worker[e["worker"]].append(e)
    for es in by_worker.values():
        if len(es) > 1:
            for e in sorted(es, key=lambda x: x["t"])[1:]:
                reasons.setdefault(e["sid"], []).append("重複参加（2回目以降）")

    with open("exclude_sessions.txt", "w", encoding="utf-8") as f:
        for sid, rs in sorted(reasons.items()):
            f.write(f"{sid}  # {'、'.join(rs)}\n")

    n_mis = sum(any("食い違い" in x for x in rs) for rs in reasons.values())
    n_dup = sum(any("重複" in x for x in rs) for rs in reasons.values())
    print(f"照合できた提出: {len(entries)} 件 / 除外するセッション: {len(reasons)} 件"
          f"（群の食い違い {n_mis}、重複参加 {n_dup}）")
    print("exclude_sessions.txt に書き出した。続けて python analyze_pilot.py を実行すると、手動除外として反映される。")


if __name__ == "__main__":
    main()
