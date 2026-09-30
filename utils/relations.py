"""指標どうしの「関係の変化」を検知する。

関係が変わったかどうかと数値は間違ってはいけない部分なので、ここは計算だけで決める
（LLM は使わない）。検知と数値の用意までを行い、理由の説明は本文生成側に任せる。

やっていること
    直近 window_recent 営業日の日次変化どうしの相関を、その手前 window_base 営業日の
    相関と比べる。Fisher 変換の z 値で偶然のぶれを除く。
    設定は knowledge/relations.json。組を増やすときは JSON に足すだけでよい。

きっかけ（2026-09-30）
    本人が動画の原油×米10年債利回りのチャートを見て「随伴していたのに最近は別の動きを
    している。金利は原油以外の原因があると思われる」と指摘した。所見を残すだけでなく、
    こうした目線で情報を集めて話題にする仕組みとして追加した。

注意
    しきい値は手で決めたもの（データで最適化していない）。20営業日の相関はぶれが大きく、
    複数の組を毎日見るので偶然発火する日もある。check_relations.py で過去の発火頻度を確認できる。
"""

import json
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "knowledge", "relations.json")

KIND_JA = {"decoupled": "連動が外れた", "coupled": "連動が強まった", "flipped": "関係が逆転した"}


def load():
    with open(PATH, encoding="utf-8") as f:
        return json.load(f)


def _align(a, b):
    """日付が両方にある日だけ残す。片方だけ休場の日をまたぐ変化は、両方とも同じ期間で測る。"""
    bd = {d: v for d, v in b if v is not None}
    return [(d, v, bd[d]) for d, v in a if v is not None and d in bd]


def _deltas(levels, mode):
    """水準の並び → 日次変化の並び。pct は変化率（%）、diff は差。"""
    out = []
    for v0, v1 in zip(levels, levels[1:]):
        if mode == "pct":
            out.append((v1 / v0 - 1) * 100 if v0 else 0.0)
        else:
            out.append(v1 - v0)
    return out


def corr(xs, ys):
    """ピアソンの相関。長さが足りない・片方が動いていないときは None。"""
    n = len(xs)
    if n < 3 or n != len(ys):
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return sxy / math.sqrt(sxx * syy)


def _z(r1, n1, r0, n0):
    clip = lambda r: max(min(r, 0.999), -0.999)
    return ((math.atanh(clip(r1)) - math.atanh(clip(r0)))
            / math.sqrt(1 / (n1 - 3) + 1 / (n0 - 3)))


def _same(xs, ys):
    """同じ向きに動いた日数。どちらかが0の日は数えない。"""
    return sum(1 for x, y in zip(xs, ys) if x * y > 0)


def _fmt_level(v, spec):
    d = spec.get("digits", 2)
    u = spec.get("unit", "")
    return f"${v:,.{d}f}" if u == "$" else f"{v:,.{d}f}{u}"


def _move(first, last, spec):
    """window の最初から最後までの動き。価格は%、金利は bp。"""
    if spec["mode"] == "pct":
        return (last / first - 1) * 100 if first else 0.0, "%"
    scale = spec.get("scale", 1)
    return (last - first) * scale, spec.get("move_unit", "")


def _sign_word(r):
    """相関の強さを、読者に渡す言葉にする。『相関』という語そのものは本文に出さない。"""
    if r >= 0.7:
        return "かなり揃って同じ向きに動く"
    if r >= 0.3:
        return "やや同じ向きに動く"
    if r > -0.3:
        return "あまり連動していない"
    if r > -0.7:
        return "やや逆の向きに動く"
    return "かなり揃って逆の向きに動く"


def analyze(pair, rows, th, guides=None):
    """1組を分析する。データが足りなければ None。発火していなくても結果は返す（fired で区別）。"""
    nr, nb = th["window_recent"], th["window_base"]
    if len(rows) < nr + nb + 1:
        return None
    la = [r[1] for r in rows]
    lb = [r[2] for r in rows]
    da = _deltas(la, pair["a"]["mode"])
    db = _deltas(lb, pair["b"]["mode"])
    ra, rb = da[-nr:], db[-nr:]
    ba, bb = da[-(nr + nb):-nr], db[-(nr + nb):-nr]
    r1, r0 = corr(ra, rb), corr(ba, bb)
    if r1 is None or r0 is None:
        return None
    z = _z(r1, nr, r0, nb)
    delta = r1 - r0
    fired = (abs(delta) >= th["min_delta"] and abs(z) >= th["min_z"]
             and max(abs(r0), abs(r1)) >= th["min_abs"])
    if r0 * r1 < 0 and abs(r0) >= th["min_abs"] and abs(r1) >= th["min_abs"]:
        kind = "flipped"
    elif abs(r1) < abs(r0):
        kind = "decoupled"
    else:
        kind = "coupled"

    def side(spec, levels):
        mv, mu = _move(levels[-nr - 1], levels[-1], spec)
        return {"name": spec["name"],
                "level_text": _fmt_level(levels[-1], spec),
                "move_text": f"{mv:+.1f}%" if mu == "%" else f"{mv:+.0f}{mu}",
                "move": round(mv, 3)}

    days = th.get("chart_days", 60)
    tail = rows[-days:]
    return {
        "id": pair["id"], "label": pair["label"],
        "kind": kind, "kind_ja": KIND_JA[kind], "fired": fired,
        "asof": rows[-1][0],
        "corr_recent": round(r1, 2), "corr_base": round(r0, 2), "z": round(z, 2),
        "n_recent": nr, "n_base": nb,
        "same_recent": _same(ra, rb), "same_base": _same(ba, bb),
        "word_recent": _sign_word(r1), "word_base": _sign_word(r0),
        "a": side(pair["a"], la), "b": side(pair["b"], lb),
        "prior": pair.get("prior", ""), "hint": pair.get("hint", ""),
        "guide": (guides or {}).get(kind, ""),
        "chart": {"dates": [t[0] for t in tail],
                  "a": {"name": pair["a"]["name"], "values": [t[1] for t in tail],
                        "digits": pair["a"].get("digits", 2), "unit": pair["a"].get("unit", "")},
                  "b": {"name": pair["b"]["name"], "values": [t[2] for t in tail],
                        "digits": pair["b"].get("digits", 2), "unit": pair["b"].get("unit", "")}},
    }


def _run_length(pair, rows, th, guides, cap):
    """今日まで連続して発火している日数（今日を含む）。cap で打ち切る。"""
    run = 1
    while run < cap:
        prev = analyze(pair, rows[:len(rows) - run], th, guides)
        if not prev or not prev["fired"]:
            break
        run += 1
    return run


def analyze_all(get_series, cfg=None):
    """全ての組を分析して返す（発火していないものも含む）。

    get_series(symbol, series) は [(日付, 値), ...] を昇順で返す関数。
    データが取れていない組は結果に入れない（埋めない）。
    """
    cfg = cfg or load()
    th = cfg["thresholds"]
    guides = cfg["meta"].get("guide_by_kind")
    out = []
    for pair in cfg["pairs"]:
        a = get_series(pair["a"]["symbol"], pair["a"].get("series"))
        b = get_series(pair["b"]["symbol"], pair["b"].get("series"))
        if not a or not b:
            continue
        rows = _align(a, b)
        item = analyze(pair, rows, th, guides)
        if item:
            # 発火が続いている区間は、毎日同じ話をしないように最初の日と repeat_days ごとだけ報告する
            rep = th.get("repeat_days", 15)
            item["run"] = _run_length(pair, rows, th, guides, rep * 4) if item["fired"] else 0
            item["report"] = item["fired"] and (item["run"] == 1 or item["run"] % rep == 0)
            out.append(item)
    return out


def detect(get_series, cfg=None):
    """今日報告する関係だけを、変化の大きい順に返す（最大 max_items 件）。"""
    cfg = cfg or load()
    items = [i for i in analyze_all(get_series, cfg) if i["report"]]
    items.sort(key=lambda i: -abs(i["z"]))
    return items[:cfg["thresholds"].get("max_items", 1)]


def strip_chart(items):
    """文脈（DBに保存する側）には図の元データを持たせない。図は history 側で持つ。"""
    return [{k: v for k, v in i.items() if k != "chart"} for i in items]
