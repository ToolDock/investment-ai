# いま実験の途中にいる人（直近N時間に進捗が動いた未完了者）を数える。ローカル専用。
# 使い方: python check_active.py [時間（既定3）]
import sys
from datetime import datetime, timedelta
from collections import Counter
import json
from utils.storage import get_connection

hours = float(sys.argv[1]) if len(sys.argv) > 1 else 3
now_utc = datetime.utcnow()
conn = get_connection()
rows = conn.execute(
    """SELECT p.group_no, pr.resume_code, pr.updated_at, pr.state_json
       FROM participants p JOIN progress pr ON pr.session_id = p.session_id
       LEFT JOIN participant_status ps ON ps.session_id = p.session_id
       WHERE p.session_id NOT IN (SELECT session_id FROM test_sessions)
         AND ps.survey_done_at IS NULL""").fetchall()
conn.close()
c = Counter()
for g, code, upd, st in rows:
    try:
        age_h = (now_utc - datetime.fromisoformat(upd)).total_seconds() / 3600
    except Exception:
        continue
    if age_h <= hours:
        month = json.loads(st).get("month_idx") if st else None
        c[g] += 1
        print(f"  群{g} {code} 最終更新 {age_h:.1f}時間前  月={month}")
print(f"直近{hours:g}時間に動いた未完了者: {dict(c)}（アンケート未送信を含む）")
