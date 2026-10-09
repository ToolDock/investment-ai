# -*- coding: utf-8 -*-
"""第1パイロットの基礎集計。ローカル専用。個人を特定する情報（セッションID・ワーカーID・自由記述）は出力しない。
使い方（Tursoの環境変数を設定した状態で）: python analyze_pilot.py
出力: 画面の集計 / pilot_features.csv（1人1行） / pilot_months.csv（1人1か月1行）。どちらも匿名の連番（pid）。
手動で除外したいセッションは、exclude_sessions.txt（1行に1つ、#以降はコメント）に書く。
群は、タスクではなくDBの群（実際に体験した群）で集計する。
"""
import csv
import math
import os
import statistics
from collections import defaultdict
from datetime import datetime

from utils.post_survey import COMMON, DIALOGUE, REPORT, screen
from utils.storage import get_connection

LOW_EFFORT_SEC = 15
RAW_IDS = ["attention_check", "sns_recall", "rep_recall_open", "rep_recall_close"]
PAUSE_CAP_SEC = 300
NOT_TEST = "session_id NOT IN (SELECT session_id FROM test_sessions)"
LIKERT_IDS = [c["id"] for c in COMMON] + [r["id"] for r in REPORT] + [d["id"] for d in DIALOGUE]


def q(conn, sql):
    try:
        return conn.execute(sql).fetchall()
    except Exception as e:
        print("  （取得できませんでした）", str(e)[:80])
        return []


def ts(s):
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def pct(vals, p):
    v = sorted(vals)
    if not v:
        return None
    k = (len(v) - 1) * p
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def mwu_p(a, b):
    # Mann-Whitney U（正規近似・同順位補正あり）。scipyがあればそちらを使う
    if len(a) < 3 or len(b) < 3:
        return None
    try:
        from scipy.stats import mannwhitneyu
        return mannwhitneyu(a, b, alternative="two-sided").pvalue
    except Exception:
        pass
    allv = sorted([(x, 0) for x in a] + [(x, 1) for x in b])
    n1, n2, n = len(a), len(b), len(a) + len(b)
    ranks, i, ties = {}, 0, 0.0
    while i < n:
        j = i
        while j + 1 < n and allv[j + 1][0] == allv[i][0]:
            j += 1
        r = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[k] = r
        t = j - i + 1
        ties += t ** 3 - t
        i = j + 1
    r1 = sum(ranks[k] for k in range(n) if allv[k][1] == 0)
    u1 = r1 - n1 * (n1 + 1) / 2
    mu = n1 * n2 / 2
    sd = math.sqrt(n1 * n2 / 12 * ((n + 1) - ties / (n * (n - 1))))
    if sd == 0:
        return 1.0
    z = (u1 - mu) / sd
    return math.erfc(abs(z) / math.sqrt(2))


def fmt(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return "-"
    return f"{statistics.median(vals):.1f} [{pct(vals, .25):.1f}-{pct(vals, .75):.1f}]"


def main():
    conn = get_connection()
    parts = q(conn, f"""SELECT session_id, group_no, age, gender, invest_experience, fin_score, overconfidence,
                        created_at, final_asset, profit, reward_yen FROM participants WHERE {NOT_TEST}
                        ORDER BY participant_no""")
    done_at = {r[0]: r[1] for r in q(conn, "SELECT session_id, survey_done_at FROM participant_status")}
    resp = q(conn, f"""SELECT session_id, month, phase, return_rate, is_event, engaged, action_label, total, cash,
                       investment_value, pl_pct, sell_amount, buy_amount, monthly_invest, anxiety, sell_impulse,
                       continue_invest, created_at FROM responses WHERE {NOT_TEST} ORDER BY session_id, month""")
    survey = defaultdict(dict)
    for sid, qid, ans in q(conn, "SELECT session_id, qid, answer FROM post_survey WHERE answer IS NOT NULL"):
        survey[sid][qid] = ans
    dlg_month = defaultdict(int)
    for sid, m, n in q(conn, "SELECT session_id, month, COUNT(*) FROM dialogue_log WHERE role = 'user' GROUP BY session_id, month"):
        dlg_month[(sid, m)] = n
    pers = {(s, m): slot for s, m, slot in q(conn, "SELECT session_id, month, slot_id FROM personalization_log")}
    conn.close()

    manual = set()
    if os.path.exists("exclude_sessions.txt"):
        for line in open("exclude_sessions.txt", encoding="utf-8-sig"):
            line = line.split("#")[0].strip()
            if line:
                manual.add(line)

    by_sid = defaultdict(list)
    for r in resp:
        by_sid[r[0]].append(r)

    rows, month_rows = [], []
    for pid, p in enumerate(parts, 1):
        sid, g = p[0], p[1]
        rs = by_sid.get(sid, [])
        done = done_at.get(sid)
        t0 = ts(p[7])
        times = [ts(r[17]) for r in rs]
        ivs = [None] * len(rs)
        for i in range(1, len(rs)):
            if times[i] and times[i - 1]:
                ivs[i] = (times[i] - times[i - 1]).total_seconds()
        iv_ok = [v for v in ivs if v is not None]
        drops = [r for r in rs if r[4] and (r[3] or 0) < 0]
        sold = [r for r in rs if (r[11] or 0) > 0]
        sold_drop = [r for r in drops if (r[11] or 0) > 0]

        def mean_of(sub, idx):
            v = [r[idx] for r in sub if r[idx] is not None]
            return sum(v) / len(v) if v else None

        ans = survey.get(sid, {})
        sc = screen(g, ans) if ans else None
        total_min = ((ts(done) - t0).total_seconds() / 60) if (done and t0 and ts(done)) else None
        med_iv = statistics.median(iv_ok) if iv_ok else None
        rec = {
            "pid": pid, "group": g, "age": p[2], "gender": p[3], "invest_experience": p[4],
            "fin_score": p[5], "overconfidence": p[6], "completed": int(bool(done)),
            "n_months": len(rs),
            "total_min": total_min,
            "active_min": (sum(min(v, PAUSE_CAP_SEC) for v in iv_ok) / 60) if iv_ok else None,
            "med_interval": med_iv,
            "n_sell_months": len(sold),
            "n_drop_months": len(drops),
            "n_sell_in_drop": len(sold_drop),
            "panic_sell": int(bool(sold_drop)) if drops else None,
            "sell_amt_event": sum((r[11] or 0) for r in drops),
            "final_asset": p[8], "profit": p[9], "reward_yen": p[10],
            "sell_imp_event": mean_of(drops, 15), "anx_event": mean_of(drops, 14),
            "cont_event": mean_of(drops, 16), "cont_all": mean_of(rs, 16),
            "dlg_msgs": sum(n for (s, m), n in dlg_month.items() if s == sid),
            "attention_pass": int(sc["attention_pass"]) if sc else None,
            "recall_common_pass": int(sc["recall_common_pass"]) if sc else None,
            "report_recall_correct": sc["report_recall_correct"] if sc else None,
            "screen_excluded": int(sc["excluded"]) if sc else None,
            "low_effort": int(med_iv is not None and med_iv < LOW_EFFORT_SEC),
            "manual_excluded": int(sid in manual),
        }
        rec["analysis_set"] = int(bool(done) and not rec["screen_excluded"] and not rec["low_effort"]
                                  and not rec["manual_excluded"])
        for k in LIKERT_IDS + RAW_IDS:
            rec[k] = ans.get(k)
        rows.append(rec)
        for r, iv in zip(rs, ivs):
            month_rows.append({
                "pid": pid, "group": g, "month": r[1], "phase": r[2], "is_event": r[4], "engaged": r[5],
                "return_rate": r[3], "pl_pct": r[10], "total": r[7], "cash": r[8], "investment_value": r[9],
                "sell_amount": r[11], "buy_amount": r[12], "monthly_invest": r[13],
                "anxiety": r[14], "sell_impulse": r[15], "continue_invest": r[16], "action_label": r[6],
                "sec_since_prev": iv, "dlg_user_msgs": dlg_month.get((sid, r[1]), 0),
                "personalization_slot": pers.get((sid, r[1])),
            })

    groups = (1, 2, 3)
    print("【参加の流れ（DBの群、テストを除く）】")
    for g in groups:
        gr = [r for r in rows if r["group"] == g]
        print(f"  群{g}: 登録 {len(gr)} / 60か月到達 {sum(r['n_months'] >= 60 for r in gr)}"
              f" / 完了（事後アンケート送信） {sum(r['completed'] for r in gr)}")
    comp = [r for r in rows if r["completed"]]

    print("\n【除外の内訳（完了者のみ）】")
    for g in groups:
        gr = [r for r in comp if r["group"] == g]
        print(f"  群{g}: 完了 {len(gr)} / 注意チェック・SNS記憶で除外 {sum(bool(r['screen_excluded']) for r in gr)}"
              f" / 間隔の中央値が{LOW_EFFORT_SEC}秒未満 {sum(r['low_effort'] for r in gr)}"
              f" / 手動除外 {sum(r['manual_excluded'] for r in gr)} → 分析対象 {sum(r['analysis_set'] for r in gr)}")
    print("  ※ タスクと群の食い違い・重複参加は、ワーカーIDとの突き合わせが必要なので、ここでは出ない。"
          "該当のsession_idを exclude_sessions.txt に書けば除外できる。")

    metrics = [("total_min", "所要時間（分、待ち時間を含む）"), ("active_min", "実操作の時間（分）"),
               ("med_interval", "月ごとの間隔の中央値（秒）"), ("n_sell_months", "売却した月数"),
               ("sell_amt_event", "下落月の売却額の合計（円）"), ("final_asset", "最終資産（円）"),
               ("profit", "利益（円）"), ("sell_imp_event", "売却衝動の平均（下落月）"),
               ("anx_event", "不安の平均（下落月）"), ("cont_event", "継続意向の平均（下落月）"),
               ("cont_all", "継続意向の平均（全月）"), ("dlg_msgs", "対話AIへの質問数")]
    names = {i["id"]: i["text"] for i in COMMON + REPORT + DIALOGUE}
    metrics += [(k, "事後: " + names[k][:16]) for k in LIKERT_IDS]

    def table(sub, label):
        print(f"\n【{label}】中央値 [四分位範囲]（参考のp値は探索的。人数が少ないので、結論には使わない）")
        gs = {g: [r for r in sub if r["group"] == g] for g in groups}
        print("  人数: " + " / ".join(f"群{g}={len(gs[g])}" for g in groups))
        for g in groups:
            d = [r for r in gs[g] if r["panic_sell"] is not None]
            if d:
                print(f"  群{g}: 下落月に売った人 {sum(r['panic_sell'] for r in d)}/{len(d)}"
                      f"（{100 * sum(r['panic_sell'] for r in d) / len(d):.0f}%）")
        print(f"  {'指標':<34}{'群1':>26}{'群2':>26}{'群3':>26}  p(2v3)  p(1v23)")
        for key, name in metrics:
            vals = {g: [r[key] for r in gs[g] if r[key] is not None] for g in groups}
            if not any(vals.values()):
                continue
            p23 = mwu_p(vals[2], vals[3])
            p1 = mwu_p(vals[1], vals[2] + vals[3])
            ps = lambda x: f"{x:.3f}" if x is not None else "  -  "
            print(f"  {name:<30}{fmt(vals[1]):>26}{fmt(vals[2]):>26}{fmt(vals[3]):>26}  {ps(p23)}   {ps(p1)}")

    table(comp, "全完了者")
    table([r for r in comp if r["analysis_set"]], "除外後（分析対象）")

    with open("pilot_features.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())) if rows else None
        if w:
            w.writeheader()
            w.writerows(rows)
    with open("pilot_months.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(month_rows[0].keys())) if month_rows else None
        if w:
            w.writeheader()
            w.writerows(month_rows)
    print(f"\n保存: pilot_features.csv（{len(rows)}行）, pilot_months.csv（{len(month_rows)}行）。"
          "匿名の連番だが、commitしない（.gitignore済み）。")


if __name__ == "__main__":
    main()
