# -*- coding: utf-8 -*-
"""人手コーディング用のシートを作る。ローカル専用。
入力: pilot_dialogue.csv, pilot_months.csv
出力: coding_sheet.xlsx（コーディング用。群とLLMの判定は載せない）
      coding_key.csv（シートのID→pid・月・ターンの対応。コーディングが終わるまで見ない）
使い方: python make_coding_sheet.py [件数=50] [出力名=coding_sheet.xlsx]
"""
import csv
import random
import re
import sys

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from coding_defs import CODES, RUBRIC, CODE_RULES

SEED = 20261009
QUESTION = re.compile(r"[?？]|ですか|ますか|でしょうか|かな$|なぜ|どう|教えて|べき|いつ|何")
PER_PID = 2          # 1人から取る上限（独白の多い人に偏らないように）
N_PLAIN_RATIO = 0.3  # 質問の形でないものの割合


def read(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def pairs(dialogue):
    """参加者ごとに、発話とその直後の応答を組にする"""
    by_pid = {}
    for r in dialogue:
        by_pid.setdefault(r["pid"], []).append(r)
    out = []
    for pid, rows in by_pid.items():
        rows.sort(key=lambda r: int(r["turn"]))
        for a, b in zip(rows, rows[1:]):
            if a["role"] == "user" and b["role"] == "assistant":
                out.append({"pid": pid, "group": a["group"], "month": int(a["month"]),
                            "turn": int(a["turn"]), "user": a["content"], "assistant": b["content"]})
    return out


def state_line(m):
    if not m:
        return ""
    return (f"局面:{m['phase']} / 評価損益:{float(m['pl_pct']):+.1f}% / "
            f"現金:{int(float(m['cash'])):,}円 / 投資評価額:{int(float(m['investment_value'])):,}円")


def pick(items, n, rng):
    """人数の上限と、群の均衡を守りながら、n件を選ぶ"""
    rng.shuffle(items)
    chosen, count, grp = [], {}, {"2": 0, "3": 0}
    for it in items:                                  # 1周目：群の均衡も守る
        if len(chosen) >= n:
            break
        if count.get(it["pid"], 0) >= PER_PID or grp[it["group"]] >= (n + 1) // 2:
            continue
        chosen.append(it)
        count[it["pid"]] = count.get(it["pid"], 0) + 1
        grp[it["group"]] += 1
    for it in items:                                  # 足りなければ均衡だけ緩める
        if len(chosen) >= n:
            break
        if it not in chosen and count.get(it["pid"], 0) < PER_PID:
            chosen.append(it)
            count[it["pid"]] = count.get(it["pid"], 0) + 1
    return chosen


def main():
    total = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    out = sys.argv[2] if len(sys.argv) > 2 else "coding_sheet.xlsx"
    dialogue = [r for r in read("pilot_dialogue.csv") if r["pii_flag"] == "0"]
    months = {(r["pid"], int(r["month"])): r for r in read("pilot_months.csv")}
    ps = pairs(dialogue)
    plain = [p for p in ps if not QUESTION.search(p["user"])]
    quest = [p for p in ps if QUESTION.search(p["user"])]
    rng = random.Random(SEED)
    n_plain = round(total * N_PLAIN_RATIO)
    chosen = pick(plain, n_plain, rng) + pick(quest, total - n_plain, rng)
    rng.shuffle(chosen)

    wb = Workbook()
    ws = wb.active
    ws.title = "コーディング"
    heads = (["ID", "月", "その月の状態", "参加者の発話", "AIの応答", "コード"]
             + [r[1] for r in RUBRIC] + ["メモ"])
    ws.append(heads)
    key = []
    for i, p in enumerate(chosen, 1):
        cid = f"c{i:03d}"
        ws.append([cid, p["month"], state_line(months.get((p["pid"], p["month"]))),
                   p["user"], p["assistant"], None] + [None] * len(RUBRIC) + [None])
        key.append({"id": cid, "pid": p["pid"], "group": p["group"], "month": p["month"], "turn": p["turn"]})

    head_fill = PatternFill("solid", fgColor="DDEBF7")
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = head_fill
        c.alignment = Alignment(wrap_text=True, vertical="center")
    widths = [6, 4, 22, 30, 56, 8] + [8] * len(RUBRIC) + [20]
    for col, w in zip(ws.iter_cols(min_row=1, max_row=1), widths):
        ws.column_dimensions[col[0].column_letter].width = w
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A2"   # 見出し行だけ固定する（左の列を固定すると、画面がそれで埋まり、コード欄が見えなくなる）
    last = len(chosen) + 1
    dv_code = DataValidation(type="list", formula1='"' + ",".join(CODES) + '"', allow_blank=True)
    dv_score = DataValidation(type="list", formula1='"1,2,3,4,5"', allow_blank=True)
    ws.add_data_validation(dv_code)
    ws.add_data_validation(dv_score)
    dv_code.add(f"F2:F{last}")
    dv_score.add(f"G2:{chr(ord('G') + len(RUBRIC) - 1)}{last}")

    wd = wb.create_sheet("定義")
    wd.append(["コード", "名前", "定義", "例"])
    for k, (name, definition, ex) in CODES.items():
        wd.append([k, name, definition, ex])
    wd.append([])
    wd.append(["選び方", CODE_RULES])
    wd.append([])
    wd.append(["評価の観点（1〜5。当てはまらないときは空欄）"])
    for _, name, text in RUBRIC:
        wd.append([name, text])
    for col, w in zip("ABCD", [18, 28, 70, 36]):
        wd.column_dimensions[col].width = w
    for row in wd.iter_rows():
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    for c in wd[1]:
        c.font = Font(bold=True)
        c.fill = head_fill

    wb.save(out)
    with open("coding_key.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "pid", "group", "month", "turn"])
        w.writeheader()
        w.writerows(key)
    g = {x: sum(1 for k in key if k["group"] == x) for x in ("2", "3")}
    print(f"{out}: {len(key)}件（群2={g['2']}、群3={g['3']}、{len({k['pid'] for k in key})}人）")
    print("コーディングが終わるまで coding_key.csv は開かない")


if __name__ == "__main__":
    main()
