# -*- coding: utf-8 -*-
"""再開番号（＝完了コード）を忘れた参加者の番号を、手がかりから探す。

参加者は匿名なので、ワーカーIDからは探せない。本人に聞いた手がかり（群・開始のおおよその
時刻・進んだ月・最終資産）で候補を絞り、一致した番号を本人に伝える。
本人かどうかは、最終資産など、本人しか知らない値が合うかで確かめる。

使い方（時刻は日本時間で指定。DBの時刻はUTCとみなして換算する）:
  python find_resume_code.py --group 3 --from "2026-10-04 20:00" --to "2026-10-04 23:00"
  python find_resume_code.py --group 2 --month 30 --unfinished
  python find_resume_code.py --asset 1234567
  python find_resume_code.py --db-is-jst ...   # DBの時刻が日本時間のとき（ローカルでの確認用）
動作確認用のセッション（?test=1）は除く。
"""
import argparse
import json
from datetime import datetime, timedelta

from utils.storage import get_connection


def to_jst(iso, db_is_jst):
    t = datetime.fromisoformat(iso)
    return t if db_is_jst else t + timedelta(hours=9)


def load_rows(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT pr.resume_code, pr.session_id, pr.state_json, pr.created_at, pr.updated_at,
               pa.group_no, pa.completed_at, pa.final_asset, pa.profit, pa.reward_yen
        FROM progress pr
        LEFT JOIN participants pa ON pa.session_id = pr.session_id
        WHERE pr.session_id NOT IN (SELECT session_id FROM test_sessions)
        ORDER BY pr.created_at
    """)
    return cur.fetchall()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", type=int, choices=[1, 2, 3])
    ap.add_argument("--from", dest="t_from", help="開始時刻の下限（日本時間 例 2026-10-04 20:00）")
    ap.add_argument("--to", dest="t_to", help="開始時刻の上限（日本時間）")
    ap.add_argument("--month", type=int, help="進んだ月（前後3か月まで一致とみなす）")
    ap.add_argument("--asset", type=int, help="最終資産（円）。完了した人だけに一致する")
    ap.add_argument("--unfinished", action="store_true", help="シミュレーションを終えていない人だけ")
    ap.add_argument("--db-is-jst", action="store_true")
    a = ap.parse_args()

    t_from = datetime.fromisoformat(a.t_from) if a.t_from else None
    t_to = datetime.fromisoformat(a.t_to) if a.t_to else None

    conn = get_connection()
    rows = load_rows(conn)
    conn.close()

    out = []
    for code, sid, state_json, created, updated, g, completed, final_asset, profit, reward in rows:
        state = json.loads(state_json) if state_json else {}
        group = g if g is not None else state.get("group")
        month = state.get("month_idx", 0)
        start = to_jst(created, a.db_is_jst)
        last = to_jst(updated, a.db_is_jst)
        if a.group and group != a.group:
            continue
        if t_from and start < t_from:
            continue
        if t_to and start > t_to:
            continue
        if a.month is not None and completed is None and abs(month - a.month) > 3:
            continue
        if a.asset is not None and final_asset != a.asset:
            continue
        if a.unfinished and completed is not None:
            continue
        out.append((code, group, start, last, month, completed, final_asset, reward))

    print(f"候補 {len(out)} 件")
    print("再開番号  群  開始(JST)         最終更新(JST)     月  状態      最終資産    報酬")
    for code, group, start, last, month, completed, final_asset, reward in out:
        status = "完了" if completed else "途中"
        fa = f"{final_asset:,}" if final_asset is not None else "-"
        rw = f"{reward}" if reward is not None else "-"
        print(f"{code:<8}  {group}  {start:%m-%d %H:%M}  {last:%m-%d %H:%M}  "
              f"{month:>2}  {status}      {fa:>10}  {rw:>4}")
    if len(out) != 1:
        print("\n候補が1件に絞れたときだけ、番号を伝える。複数のときは、時刻・月・最終資産で絞る。")


if __name__ == "__main__":
    main()
