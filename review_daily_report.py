"""生成した日報を、規定に照らして機械的に点検する。

    python review_daily_report.py            全月を点検して一覧を出す
    python review_daily_report.py -v         違反の該当箇所も表示する

人手のレビューを置き換えるものではなく、人手で見るべき月を絞るための道具。
"""

import json
import re
import sys
from collections import Counter, defaultdict

from generate_daily_report import CHART_BY_PHASE, CHARTS, EVENT_PHASES, length_range
from utils.providers import select_segments
from utils.visuals import select_recent

SCENARIO = "scenario_scripted.json"
HV = "knowledge/historical_visuals.json"
# 締めの決まり文句。実験は月次、本番は日次で語尾だけが変わる
CLOSINGS = {"month": "相場は相場に任せて、今月も Just Keep Buying。",
            "day": "相場は相場に任せて、今日も Just Keep Buying。"}

NG_PHRASES = ["売ってください", "売るべきです", "買ってください", "買うべきです",
              "買い増しましょう", "買い増すべき", "一切売らない", "絶対に売らない",
              "買わないでください", "売却をお勧め", "購入をお勧め"]
HIGH_WORDS = ["高値圏", "最高値圏", "史上最高値", "年初来高値"]

# 値動きの理由を語るときの言い回しと、出典を示す言い回し
CAUSE_WORDS = ["を受けて", "が原因", "を背景に", "によって", "が意識され",
               "警戒感", "懸念から", "嫌気され"]
ATTRIB_WORDS = ["伝えて", "報道", "報じ", "との見方", "挙げられ", "によると",
                "とされ", "CNBC", "Reuters", "ロイター", "見出し"]

# 触れてはいけないもの。実験では為替も存在しないが、本番では実在する
ABSENT = {
    "month": ["信託報酬", "手数料", "税金", "為替", "円安", "円高", "ドル円", "NISA"],
    "day": ["信託報酬", "手数料", "税金", "NISA"],
}


def check(m, hv, prev_texts, unit="month"):
    """(重大な違反, 気になる点) を返す。"""
    dr = m.get("daily_report") or {}
    blocks = dr.get("blocks") or []
    ng, warn = [], []

    if not blocks:
        return ["日報がない"], []

    text = "".join(b["text"] for b in blocks)
    mc = m["market_context"]
    dd = mc["drawdown"]

    # 定型
    def _norm(x):
        return re.sub(r"\s+", "", x)

    if not _norm(blocks[-1]["text"]).endswith(_norm(CLOSINGS[unit])):
        ng.append("締めが決め台詞で終わっていない")
    # 挨拶は実行時に前置きされるので、指数と騰落率から入っていれば型は満たされている
    if "S&P500" not in blocks[0]["text"][:40]:
        warn.append("書き出しで指数の騰落に触れていない")
    hl = dr.get("headline", "")
    if not hl:
        ng.append("見出しがない")
    elif len(hl) > 25:
        warn.append(f"見出しが長い（{len(hl)}字）")

    # 構造。実験は2〜4段落、本番はその日に載せるべき話題の数と一致しているはず
    is_event = m["phase"] in EVENT_PHASES
    # 実験（月次）も本番と同じく、話題の数から段落数と字数の目安を決める
    want = len(select_segments(m))
    if len(blocks) != want:
        warn.append(f"段落数が{len(blocks)}（話題は{want}件）")
    charts = [b["chart"] for b in blocks if b.get("chart")]
    if not 1 <= len(charts) <= 2:
        warn.append(f"図が{len(charts)}枚")
    allowed = CHART_BY_PHASE.get(m["phase"], list(CHARTS))
    for c in charts:
        if c not in allowed:
            ng.append(f"局面に許されていない図: {c}")

    # 数値との整合
    # 「最高値圏ではなく」のような否定は違反ではない
    NEG = "ではなく|ではありません|ではない|とは言えま|には遠い|ほど遠い|には届|途中"
    quoted = {i for a, b in
              [(mm.start(), mm.end()) for mm in re.finditer(r"[「『][^」』]{0,40}[」』]", text)]
              for i in range(a, b)}
    if dd["current"] < -3.0:
        for w in HIGH_WORDS:
            hit_found = False
            for hit in re.finditer(w, text):
                if hit.start() in quoted:      # 報道の見出しの引用は違反ではない
                    continue
                if re.search(NEG, text[hit.end():hit.end() + 16]):
                    continue
                if re.search(NEG, text[max(0, hit.start() - 24):hit.start()]):
                    continue
                hit_found = True
                break
            if hit_found:
                ng.append(f"下落幅{dd['current']:.1f}%なのに「{w}」")
                break
    # 見出しも同じ基準で見る（本文だけの点検では「年初来高値圏」の見出しを見逃した）
    if dd["current"] < -3.0:
        for w in HIGH_WORDS:
            if w in hl and not re.search(NEG, hl):
                ng.append(f"見出しが下落幅{dd['current']:.1f}%と矛盾:「{w}」")
                break
    # 回復を言い切る表現は、深い下落のあいだは使わない
    if dd["current"] < -10.0:
        for w in ["順調に回復", "順調に戻", "順調に推移", "好調"]:
            if w in text and not re.search(NEG, text[text.index(w):text.index(w) + 16]):
                ng.append(f"下落幅{dd['current']:.1f}%なのに「{w}」")
                break
        if re.search(r"買い増し?(した|そう)くなる|買い増そう", text):
            warn.append("戻りを理由に買い増しを想起させている")
    # 最高値の近くでは、下落の図が空になる
    if dd["current"] > -1.5 and any(c in ("v_recent_drawdowns", "v_drawdown") for c in charts):
        ng.append(f"下落幅{dd['current']:.1f}%（最高値付近）なのに下落の図を使っている")
    if "一日の値動き" in text or "1日の値動き" in text:
        warn.append("日次の値動きに言及している")

    # 図と本文の整合
    if "v_recent_drawdowns" in charts:
        eps = json.load(open(HV, encoding="utf-8"))["v_recent_drawdowns"]["data"]["episodes"]
        shown = {e["name"] for e in select_recent(eps, dd["max_so_far"])}
        named = {e["name"] for e in eps if e["name"] in text}
        extra = named - shown
        if extra:
            ng.append(f"図にない局面を本文で引いている: {'／'.join(extra)}")

    # 実データの日報は、理由を自分の見立てで語らない（出典つきで引く）
    if unit == "day" and any(w in text for w in CAUSE_WORDS) \
            and not any(w in text for w in ATTRIB_WORDS):
        warn.append("値動きの理由を出典なしで述べている")

    # 単独引用を禁じた行
    if "世界恐慌" in text or "第一次大戦" in text:
        warn.append("単独引用を禁じた弱気相場に言及している")

    # 存在しない要素への言及
    for w in ABSENT[unit]:
        if w in text:
            ng.append(f"存在しない要素: {w}")
            break

    # 与えられていない数値
    allowed = {f"{m['return']*100:.1f}", f"{mc['vix']:.1f}" if False else str(mc["vix"]),
               str(mc["fear_greed"]["value"]),
               f"{dd['current']:.1f}", f"{dd['max_so_far']:.1f}"}
    for sec in mc["sectors"]:
        allowed.add(f"{sec['change_pct']:.1f}")
    for idx in mc["indices"]:
        allowed.add(f"{idx['change_pct']:.1f}")
    eps = json.load(open(HV, encoding="utf-8"))["v_recent_drawdowns"]["data"]["episodes"]
    for e in eps:
        allowed.add(f"{e['decline_pct']:.1f}")
        if e.get("recovery_months"):
            allowed.add(f"{e['recovery_months']:.1f}")
        allowed.add(f"{e['decline_months']:.1f}")
    for r in json.load(open(HV, encoding="utf-8"))["v_bear_markets"]["rows"]:
        allowed.add(f"{r['decline_pct']:.1f}")
    # 本番だけ渡している円建て投信の数値
    fx = m.get("fx") or {}
    for k in ("level", "day_yen", "day_pct", "ytd_yen", "ytd_pct"):
        if fx.get(k) is not None:
            allowed.add(f"{abs(fx[k]):.1f}")
            allowed.add(f"{abs(fx[k]):.2f}")
    rates = m.get("rates") or {}
    for k in ("level", "day_bp", "ytd_bp"):
        if rates.get(k) is not None:
            allowed.add(f"{abs(rates[k]):.1f}")
            allowed.add(f"{abs(rates[k]):.2f}")
    fund = m.get("fund") or {}
    if fund:
        # 円建て投信の数値は本文で小数2桁になることがあるので両方許す
        for v in (fund.get("change_pct"),
                  (fund.get("drawdown") or {}).get("current"),
                  (fund.get("drawdown") or {}).get("max_so_far")):
            if v is not None:
                allowed.add(f"{abs(v):.1f}")
                allowed.add(f"{abs(v):.2f}")
    earnings = m.get("earnings") or {}
    if earnings.get("yoy_pct") is not None:
        allowed.add(f"{abs(earnings['yoy_pct']):.1f}")
    allowed = {a.lstrip("-") for a in allowed}
    found = re.findall(r"[-+−]?\d+\.\d+(?=%|パーセント)", text)
    unknown = {f.lstrip("-+−") for f in found} - allowed
    if unknown:
        warn.append(f"渡していない数値: {'／'.join(sorted(unknown))}")

    # 発言の境界
    for p in NG_PHRASES:
        for hit in re.finditer(re.escape(p), text):
            tail = text[hit.end():hit.end() + 16]
            if not re.search("ではありません|ではなく|必要はありま|わけではな|理由にはな|判断材料では", tail):
                ng.append(f"禁止表現: {p}")
                break

    # 繰り返し
    head = blocks[0]["text"][:24]
    if head in prev_texts:
        warn.append("書き出しが他の月と重複")

    # 長さ。本番は話題の数から決まる目安に対して見る（下振れは薄さの兆候）
    n = len(text)
    if want:
        lo, hi = length_range(want, is_event)
        lo, hi = int(lo * 0.8), int(hi * 1.2)
    else:
        lo, hi = 350, 800
    if not lo <= n <= hi:
        warn.append(f"本文が{n}字（目安 {lo}〜{hi}字）")

    return ng, warn


def load_live(limit=60):
    """本番の日報を、台本と同じ形にそろえて読み出す。"""
    import sqlite3
    from db import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM daily_report ORDER BY date LIMIT ?", (limit,)).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()
    out = []
    for r in rows:
        ctx = json.loads(r["context"] or "{}")
        ctx["daily_report"] = {"blocks": json.loads(r["blocks"] or "[]"),
                               "headline": r["headline"]}
        ctx.setdefault("month", r["seq"] or 0)
        ctx.setdefault("phase", r["phase"])
        ctx["label"] = r["date"]
        out.append(ctx)
    return out


def main():
    verbose = "-v" in sys.argv
    live = "live" in sys.argv
    hv = json.load(open(HV, encoding="utf-8"))
    if live:
        items, unit, noun = load_live(), "day", "日"
        if not items:
            print("本番の日報がまだありません（investment_ai.db / daily_report）")
            return
    else:
        items = json.load(open(SCENARIO, encoding="utf-8"))["timeline"]
        unit, noun = "month", "か月"

    seen_heads = Counter()
    rows, chart_use = [], defaultdict(Counter)
    for m in items:
        dr = m.get("daily_report") or {}
        blocks = dr.get("blocks") or []
        head = blocks[0]["text"][:24] if blocks else ""
        prev = {h for h, c in seen_heads.items() if c >= 1}
        ng, warn = check(m, hv, prev, unit)
        seen_heads[head] += 1
        for b in blocks:
            if b.get("chart"):
                chart_use[m["phase"]][b["chart"]] += 1
        rows.append((m.get("label") or m["month"], m["phase"], ng, warn))

    bad = [r for r in rows if r[2]]
    n_ng = sum(len(r[2]) for r in rows)
    n_warn = sum(len(r[3]) for r in rows)
    print(f"点検: {len(rows)}{noun}　重大 {n_ng}件（{len(bad)}{noun}）　"
          f"気になる点 {n_warn}件\n")

    for mo, ph, ng, warn in rows:
        if ng or (verbose and warn):
            mark = "×" if ng else "・"
            label = f"{mo}か月目" if unit == "month" else str(mo)
            print(f"{mark} {label:>10} {ph}")
            for x in ng:
                print(f"     [重大] {x}")
            if verbose:
                for x in warn:
                    print(f"     [注意] {x}")

    if not verbose:
        counts = Counter(x for _, _, _, w in rows for x in
                         (re.sub(r"\d+", "N", i) for i in w))
        print("\n気になる点の内訳（-v で月ごとに表示）:")
        for k, v in counts.most_common():
            print(f"  {v:>3}件  {k}")

    print("\n局面ごとの図の使われ方:")
    for ph, c in chart_use.items():
        print(f"  {ph:<5}", dict(c.most_common()))


if __name__ == "__main__":
    from utils.runlog import tee
    tee("review")
    main()
