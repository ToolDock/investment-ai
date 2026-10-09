"""クラウドワークスの作業結果CSVと実験DBを突き合わせ、報酬の一覧を作る。

    python payout_report.py 作業結果.csv                 完了番号を探して報酬を付ける
    python payout_report.py 作業結果.csv --id-col ワーカーID   ワーカー識別の列を指定（出力に残す）
    python payout_report.py 作業結果.csv --code-col 完了コードの列名 --value-col 確認値の列名
                                                         参加者が貼り付けた確認値をDBの報酬額と照合する
    python payout_report.py --all                         CSVなしで、完了済みの全員の報酬を出す
    python payout_report.py --tier --stage1 参加賞_群2.csv 参加賞_群3.csv --stage2 S:S.csv A:A.csv B:B.csv C:C.csv D:D.csv --id-col ワーカーID
                                                         ランク方式。1段目（参加賞）と、ランクごとの追加報酬タスクの結果を突き合わせる

出力: payout.csv（行ごとの状態と報酬）、payout_summary.txt（報酬額ごとの人数と合計）
CSVの列名が分からなくても、各セルから6桁の完了番号らしい文字列を探して照合する。
状態: OK / 番号なし / 未完了（アンケート未送信）/ 重複（同じ番号が複数行にある）/ 値不一致（貼り付けた確認値がDBの報酬額と違う）
"""

import argparse
import csv
import re
import sys
from collections import Counter

from utils.storage import get_connection

CODE = re.compile(r"\b[2-9A-HJ-NP-Z]{6}\b")


def load_db():
    conn = get_connection()
    rows = conn.execute(
        """SELECT pr.resume_code, p.group_no, p.final_asset, p.profit, p.reward_yen,
                  ps.survey_done_at, ps.consented_at
           FROM progress pr
           JOIN participants p ON p.session_id = pr.session_id
           LEFT JOIN participant_status ps ON ps.session_id = pr.session_id
           WHERE pr.session_id NOT IN (SELECT session_id FROM test_sessions)"""
    ).fetchall()
    conn.close()
    return {r[0]: {"group": r[1], "final_asset": r[2], "profit": r[3],
                   "reward": r[4], "survey_done_at": r[5], "consented_at": r[6]} for r in rows}


SHORT_MINUTES = 20      # これより短い所要時間は、流して進めた可能性があるので要確認とする


def minutes_taken(d):
    """同意から事後アンケート送信までの分数。記録が欠けていれば None。
    途中で閉じて再開した人は長くなるので、短い側だけを疑う目安にする。"""
    from datetime import datetime
    try:
        a = datetime.fromisoformat(d["consented_at"])
        b = datetime.fromisoformat(d["survey_done_at"])
        return round((b - a).total_seconds() / 60, 1)
    except Exception:
        return None


def caution(d):
    m = minutes_taken(d)
    if m is None:
        return "", ""
    return m, (f"短時間（{m}分）" if m < SHORT_MINUTES else "")


def read_csv(path):
    for enc in ("utf-8-sig", "cp932"):
        try:
            with open(path, encoding=enc, newline="") as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError:
            continue
    raise SystemExit("CSVの文字コードを読めませんでした（utf-8 / cp932 以外）")


def parse_value(text):
    """貼り付けられた確認値を整数にする。全角数字・「円」・カンマ・空白まじりも読む。"""
    t = (text or "").translate(str.maketrans("０１２３４５６７８９，", "0123456789,"))
    digits = re.sub(r"[^0-9]", "", t.replace("円", ""))
    return int(digits) if digits else None


def find_code(row, db, col=None):
    """行の各セルから、DBにある完了番号を探す。小文字・空白まじりの入力も拾う。
    col を指定すると、その列だけを見る。"""
    cells = [row.get(col, "")] if col else row.values()
    for v in cells:
        text = (v or "").upper().replace(" ", "").replace("　", "")
        for m in CODE.findall(text):
            if m in db:
                return m
        # 入力に区切りが無く、他の文字と続いている場合のため、短い回答ならそのまま照合
        if len(text) == 6 and text in db:
            return text
    return None


def summarize(rows, out_path):
    ok = [r for r in rows if r["状態"] == "OK"]
    c = Counter(r["報酬(円)"] for r in ok)
    lines = [f"行数 {len(rows)} / OK {len(ok)} / 要確認 {len(rows) - len(ok)}",
             f"OKの報酬合計 {sum(r['報酬(円)'] for r in ok):,} 円", "", "報酬額ごとの人数:"]
    for amt in sorted(c):
        lines.append(f"  {amt:>4} 円 × {c[amt]} 人")
    bad = Counter(r["状態"] for r in rows if r["状態"] != "OK")
    if bad:
        lines += ["", "要確認の内訳:"] + [f"  {k}: {v}" for k, v in bad.items()]
    text = "\n".join(lines)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text)


def _extra_summary(rows, out_path):
    ok = [r for r in rows if r["状態"] == "OK"]
    by = Counter((r["段階"], r["支払い(円)"]) for r in ok)
    total = sum(r["支払い(円)"] for r in ok)
    lines = [f"行数 {len(rows)} / OK {len(ok)} / 要確認 {len(rows) - len(ok)}",
             f"OKの支払い合計 {total:,} 円（税込の目安 {round(total * 1.1):,} 円）", "", "段階・金額ごとの人数:"]
    for (stage, amt) in sorted(by):
        lines.append(f"  {stage} {amt:>4} 円 × {by[(stage, amt)]} 人")
    bad = Counter((r["段階"], r["状態"]) for r in rows if r["状態"] != "OK")
    if bad:
        lines += ["", "要確認の内訳:"] + [f"  {k[0]} {k[1]}: {v}" for k, v in bad.items()]
    # 短時間承認済.txt（1行1人のワーカーID）に載せた人は、短時間の一覧から外す
    try:
        done = {l.strip() for l in open("短時間承認済.txt", encoding="utf-8-sig") if l.strip()}
    except OSError:
        done = set()
    short = [r for r in ok if r.get("注意") and r["ワーカー"] not in done]
    if short:
        lines += ["", f"OKだが所要時間が短い（{SHORT_MINUTES}分未満。承認前に目視で確認）: {len(short)}件"]
        lines += [f"  {r['段階']} {r['ワーカー']} {r['注意']}" for r in short]
    text = "\n".join(lines)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text)


def run_tier(a, db):
    """ランク方式。1段目（参加賞）と2段目（ランクごとの追加報酬）を、完了コードとDBのランクで照合する。

    1段目: 完了コードがDBにあり、アンケートまで終えていて、重複していなければ OK（参加賞）。
    2段目: 完了コードがDBにあり、アンケートまで終え、そのタスクのランクとDBのランクが一致し、
           重複せず、（--id-col と --stage1 があれば）同じワーカーが1段目に同じ完了コードを
           出していれば OK（追加報酬）。
    """
    from utils.rank import reward_rank, rank_extra, TIERS
    base = 10
    out = []

    stage1_code_by_worker = {}
    stage1_rows = []
    for path in a.stage1 or []:
        rows = read_csv(path)
        codes = [find_code(r, db, a.code_col) for r in rows]
        stage1_rows += [(r, c, path) for r, c in zip(rows, codes)]
    seen = Counter(c for _, c, _ in stage1_rows if c)
    # 同じワーカーが1段目に複数回出している（群2用と群3用の両方に参加した場合など）
    worker_n = Counter((r.get(a.id_col, "") if a.id_col else "") for r, _, _ in stage1_rows)
    for r, code, path in stage1_rows:
        wid = r.get(a.id_col, "") if a.id_col else ""
        if not code:
            st_, pay = "番号なし", ""
        elif not db[code]["survey_done_at"]:
            st_, pay = "未完了", ""
        elif wid and worker_n[wid] > 1:
            st_, pay = "同一ワーカーが複数回", ""
        elif seen[code] > 1:
            st_, pay = "重複", ""
        else:
            st_, pay = "OK", base
            if wid:
                stage1_code_by_worker[wid] = code
        out.append({"段階": "1段目(参加賞)", "ワーカー": wid, "完了番号": code or "",
                    "タスクのランク": "", "DBのランク": reward_rank(db[code]["reward"]) if code else "",
                    "状態": st_, "支払い(円)": pay,
                    "所要分": caution(db[code])[0] if code else "",
                    "注意": caution(db[code])[1] if code else ""})

    for spec in a.stage2 or []:
        rank, _, path = spec.partition(":")
        if rank not in [t[1] for t in TIERS] or not path:
            raise SystemExit(f"--stage2 は ランク:CSVのパス の形で指定してください（例 S:S.csv）。受け取った値: {spec}")
        rows = read_csv(path)
        codes = [find_code(r, db, a.code_col) for r in rows]

        def owner_ok(wid, code):
            # 1段目に同じ完了コードを出したワーカー本人か（1段目と ID の列があるときだけ見る）
            return not (a.stage1 and a.id_col) or stage1_code_by_worker.get(wid) == code

        # 重複は、本人の提出どうしの間だけで数える（他人が同じコードを出しても、本人は巻き込まない）
        seen = Counter(c for r, c in zip(rows, codes)
                       if c and owner_ok(r.get(a.id_col, "") if a.id_col else "", c))
        for r, code in zip(rows, codes):
            wid = r.get(a.id_col, "") if a.id_col else ""
            real = reward_rank(db[code]["reward"]) if code else ""
            if not code:
                st_, pay = "番号なし", ""
            elif not db[code]["survey_done_at"]:
                st_, pay = "未完了", ""
            elif real != rank:
                st_, pay = f"ランク違い(正しくは{real})", ""
            elif not owner_ok(wid, code):
                st_, pay = "1段目と一致せず", ""
            elif seen[code] > 1:
                st_, pay = "重複", ""
            else:
                st_, pay = "OK", rank_extra(rank)
            out.append({"段階": "2段目(追加報酬)", "ワーカー": wid, "完了番号": code or "",
                        "タスクのランク": rank, "DBのランク": real, "状態": st_, "支払い(円)": pay,
                        "所要分": caution(db[code])[0] if code else "",
                        "注意": caution(db[code])[1] if code else ""})

    cols = ["段階", "ワーカー", "完了番号", "タスクのランク", "DBのランク", "状態", "支払い(円)", "所要分", "注意"]
    with open("payout_tier.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, restval="")
        w.writeheader()
        w.writerows(out)
    _extra_summary([{**r, "支払い(円)": r["支払い(円)"] if r["支払い(円)"] != "" else 0} for r in out],
                   "payout_tier_summary.txt")
    print("\n-> payout_tier.csv / payout_tier_summary.txt")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="?")
    ap.add_argument("--id-col")
    ap.add_argument("--code-col", help="完了コードの列名（省略時は全列から探す）")
    ap.add_argument("--value-col", help="確認値の列名。指定するとDBの報酬額と照合する")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--tier", action="store_true", help="ランク方式の照合（--stage1 / --stage2 を使う）")
    ap.add_argument("--stage1", nargs="+", help="1段目（参加賞）の結果CSV。群2用・群3用など複数を並べてよい")
    ap.add_argument("--stage2", nargs="+", help="2段目の結果CSVを ランク:パス の形で（例 S:S.csv A:A.csv）")
    a = ap.parse_args()

    db = load_db()
    if a.tier:
        return run_tier(a, db)
    out = []
    if a.all or not a.csv:
        for code, d in db.items():
            if d["survey_done_at"]:
                out.append({"ワーカー": "", "完了番号": code, "群": d["group"],
                            "状態": "OK", "報酬(円)": d["reward"]})
    else:
        seen = Counter()
        rows = read_csv(a.csv)
        codes = [find_code(r, db, a.code_col) for r in rows]
        seen.update(c for c in codes if c)
        for r, code in zip(rows, codes):
            wid = r.get(a.id_col, "") if a.id_col else ""
            if not code:
                out.append({"ワーカー": wid, "完了番号": "", "群": "", "状態": "番号なし", "報酬(円)": "",
                            "申告値": "", "DBの報酬額": ""})
                continue
            d = db[code]
            claimed = parse_value(r.get(a.value_col, "")) if a.value_col else None
            if not d["survey_done_at"]:
                status = "未完了"
            elif seen[code] > 1:
                status = "重複"
            elif a.value_col and claimed != d["reward"]:
                status = "値不一致"
            else:
                status = "OK"
            out.append({"ワーカー": wid, "完了番号": code, "群": d["group"],
                        "状態": status, "報酬(円)": d["reward"] if status == "OK" else "",
                        "申告値": "" if claimed is None else claimed, "DBの報酬額": d["reward"]})

    with open("payout.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ワーカー", "完了番号", "群", "状態", "報酬(円)", "申告値", "DBの報酬額"],
                           restval="")
        w.writeheader()
        w.writerows(out)
    summarize([{**r, "報酬(円)": r["報酬(円)"] if r["報酬(円)"] != "" else 0} for r in out],
              "payout_summary.txt")
    print("\n-> payout.csv / payout_summary.txt")


if __name__ == "__main__":
    sys.exit(main())
