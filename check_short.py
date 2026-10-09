# 短時間の完了者の中身を見る（ローカル専用）。使い方: python check_short.py GU7DPQ TWP7GD
import sys
from collections import Counter
from utils.storage import get_connection

conn = get_connection()
for code in sys.argv[1:]:
    r = conn.execute("SELECT session_id FROM progress WHERE resume_code = ?", (code,)).fetchone()
    if not r:
        print(code, "見つからない"); continue
    sid = r[0]
    rows = conn.execute(
        "SELECT month, action_label, anxiety, sell_impulse, continue_invest, created_at "
        "FROM responses WHERE session_id = ? ORDER BY month", (sid,)).fetchall()
    n_dlg = conn.execute("SELECT COUNT(*) FROM dialogue_log WHERE session_id = ? AND role = 'user'", (sid,)).fetchone()[0]
    ans = conn.execute("SELECT answer FROM post_survey WHERE session_id = ? AND answer IS NOT NULL", (sid,)).fetchall()
    print("====", code)
    print("月数:", len(rows), " 対話の質問数:", n_dlg)
    print("行動の内訳:", dict(Counter(x[1] for x in rows)))
    print("不安の値:", dict(Counter(x[2] for x in rows)))
    print("売却衝動の値:", dict(Counter(x[3] for x in rows)))
    print("継続意向の値:", dict(Counter(x[4] for x in rows)))
    print("事後アンケートの回答の分布:", dict(Counter(a[0] for a in ans)))
    ts = [x[5] for x in rows if x[5]]
    if len(ts) > 1:
        from datetime import datetime
        t = [datetime.fromisoformat(s) for s in ts]
        gaps = sorted((b - a).total_seconds() for a, b in zip(t, t[1:]))
        print("月ごとの間隔(秒) 最小/中央/最大:", round(gaps[0]), round(gaps[len(gaps)//2]), round(gaps[-1]))
conn.close()
