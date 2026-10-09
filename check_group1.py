# 群1の参加者（パイロットでは想定外）を調べる。ローカル専用。使い方: python check_group1.py
from collections import Counter
import json
from utils.storage import get_connection

conn = get_connection()
rows = conn.execute(
    """SELECT p.session_id, p.group_no, p.created_at, p.completed_at, pr.resume_code, pr.state_json
       FROM participants p LEFT JOIN progress pr ON pr.session_id = p.session_id
       WHERE p.session_id NOT IN (SELECT session_id FROM test_sessions)
       ORDER BY p.created_at""").fetchall()
print("群ごとの人数（テスト除く）  開始 / 完了")
c_all, c_done = Counter(r[1] for r in rows), Counter(r[1] for r in rows if r[3])
for g in sorted(c_all, key=lambda x: (x is None, x)):
    print(f"  群{g}: {c_all[g]} / {c_done[g]}")
print()
print("群1の参加者")
for sid, g, created, done, code, st in rows:
    if g != 1:
        continue
    sg = json.loads(st).get("group") if st else None
    n_dlg = conn.execute("SELECT COUNT(*) FROM dialogue_log WHERE session_id = ?", (sid,)).fetchone()[0]
    print(f"  {code}  開始 {created}  完了 {done}  進捗の中の群={sg}  対話の件数={n_dlg}")
conn.close()
