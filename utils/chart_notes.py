"""チャートに添える短い読み方を組み立てる。

「いま」はデータから機械的に出す。「見方」は knowledge/chart_reading.json の固定文。
毎日変わらない解説をあえて毎日出すことで、読者に見方そのものを覚えてもらう。
LLM は使わない。ここは決して間違ってはいけない部分なので、計算と定型文だけで作る。
"""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "knowledge", "chart_reading.json")

UP, DOWN, FLAT = "上げ基調", "下げ基調", "横ばい"


def load():
    with open(PATH, encoding="utf-8") as f:
        return json.load(f)


def _band(value, bands):
    for lo, hi, label in bands:
        if lo <= value < hi:
            return label
    return bands[-1][2] if bands else ""


def trend(values, spec):
    """直近の並びから (傾き, 変化量, 変化の表示) を返す。値が足りなければ None。"""
    if not values or len(values) < 5:
        return None, None, ""
    first, last = values[0], values[-1]
    mode = spec.get("mode", "pct")
    if mode == "bp":
        chg = (last - first) * 100
        text = f"{chg:+.0f}bp"
    elif mode == "yen":
        chg = last - first
        text = f"{chg:+.2f}円"
    elif mode == "point":
        chg = last - first
        text = f"{chg:+.{spec.get('digits', 0)}f}ポイント"
    else:
        if not first:
            return None, None, ""
        chg = (last / first - 1) * 100
        text = f"{chg:+.1f}%"
    flat = spec.get("flat", 2.0)
    if chg >= flat:
        return UP, chg, text
    if chg <= -flat:
        return DOWN, chg, text
    return FLAT, chg, text


def _note(spec, values, now_extra=""):
    t, _, text = trend(values, spec)
    parts = []
    if t:
        parts.append(f"直近20営業日は{t}（{text}）")
    if now_extra:
        parts.append(now_extra)
    return {"title": spec["title"], "now": "。".join(parts), "read": spec["read"]}


def build(ctx, history, days=20):
    """ctx（当日の文脈）と history（指標ID → 終値の並び）から注記を組み立てる。

    history に無い指標は「いま」を省き、見方だけ出す。取れないものは埋めない。
    """
    cfg = load()
    ind = cfg["indicators"]
    mc = ctx["market_context"]
    out = {}

    def add(key, values, extra=""):
        if key in ind:
            out[key] = _note(ind[key], (values or [])[-days:], extra)

    add("index", history.get("index"))

    dd = mc["drawdown"]
    label = (ctx.get("window") or {}).get("label", "この期間")
    add("drawdown", history.get("drawdown"),
        f"いまは{label}の最高値から{dd['current']:.1f}%（この期間の最大は{dd['max_so_far']:.1f}%）")

    if mc.get("vix") is not None:
        add("vix", history.get("vix"),
            f"いまは{mc['vix']}で「{_band(mc['vix'], ind['vix']['bands'])}」の水準")

    fg = mc.get("fear_greed")
    if fg:
        add("fear_greed", history.get("fear_greed"),
            f"いまは{fg['value']}で「{_band(fg['value'], ind['fear_greed']['bands'])}」")

    if ctx.get("rates"):
        r = ctx["rates"]
        add("rates", history.get("rates"),
            f"いまは{r['level']:.2f}%（前営業日比 {r['day_bp']:+.1f}bp）")

    if ctx.get("fx"):
        f = ctx["fx"]
        add("fx", history.get("fx"),
            f"いまは{f['level']:.2f}円（前営業日比 {f['day_yen']:+.2f}円）")

    for key, sym in (("gold", "GOLD"), ("btc", "BTC"), ("semis", "SOX")):
        v = next((i["change_pct"] for i in mc.get("indices") or []
                  if i["symbol"] == sym), None)
        if v is not None:
            add(key, history.get(key), f"今日は{v:+.1f}%")

    sec = mc.get("sectors") or []
    if len(sec) >= 2:
        spread = sec[0]["change_pct"] - sec[-1]["change_pct"]
        add("sectors", None,
            f"今日は最強と最弱の差が{spread:.1f}ポイント")

    out["_links"] = links(ctx, cfg, history)
    return out


def _sector_pct(sectors, name):
    return next((s["change_pct"] for s in sectors if s["sector"] == name), None)


def links(ctx, cfg=None, history=None):
    """指標どうしの関係のうち、今日実際に成り立っているものだけを返す。

    各項目は次を持つ。
        text  … 数値を入れた既定の文（LLM が使えないときはこれをそのまま出す）
        facts … 計算で出した数値。LLM に理由を書かせるときの材料
        guide … その項目で言うべきこと・言ってはいけないこと
    """
    cfg = cfg or load()
    by_id = {l["id"]: l for l in cfg["links"]}
    history = history or {}
    mc = ctx["market_context"]
    sec = mc.get("sectors") or []
    found = []

    def take(lid, text, facts):
        item = dict(by_id[lid])
        item["text"] = text
        item["facts"] = facts
        found.append(item)

    # 金利上昇 × 成長株安
    rates = ctx.get("rates") or {}
    tech = _sector_pct(sec, "Technology")
    if rates.get("day_bp", 0) >= 5 and sec and sec[-1]["sector"] == "Technology":
        take("rates_growth",
             f"米10年債利回りが{rates['day_bp']:+.1f}bp上がり、"
             f"テクノロジーが{tech:+.1f}%と最弱でした。" + by_id["rates_growth"]["text"],
             {"利回りの変化": f"{rates['day_bp']:+.1f}bp",
              "利回りの水準": f"{rates['level']:.2f}%",
              "テクノロジー": f"{tech:+.1f}%"})

    # 指数と円建ての乖離
    # 説明したい「差」は下落局面の間ずっと積み上がったものなので、
    # 為替も同じ期間（window）で見た累積変化を使う。前営業日比（1日分）を使うと、
    # 期間の差と時間軸が合わないうえ、日によっては向きが逆に見えて誤読を生む
    # （2026-09-18、本人が生成結果の矛盾から発見）。
    fund = ctx.get("fund")
    fx = ctx.get("fx") or {}
    if fund and fund["drawdown"]["current"] < mc["drawdown"]["current"] - 1.0:
        gap = mc["drawdown"]["current"] - fund["drawdown"]["current"]
        win_label = (ctx.get("window") or {}).get("label") or "この下落局面"
        yen = (f"ドル円は{win_label}で {fx['ytd_yen']:+.2f}円動いています。"
               if fx.get("ytd_yen") is not None else "")
        take("fx_gap",
             f"指数は最高値から{mc['drawdown']['current']:.1f}%の下げですが、"
             f"円建ての基準価額は{fund['drawdown']['current']:.1f}%と"
             f"{gap:.1f}ポイント深いところにいます。{yen}"
             + by_id["fx_gap"]["text"],
             {"指数の下落幅": f"{mc['drawdown']['current']:.1f}%",
              "円建ての下落幅": f"{fund['drawdown']['current']:.1f}%",
              "差": f"{gap:.1f}ポイント",
              f"ドル円（{win_label}の累積）": (f"{fx['ytd_yen']:+.2f}円"
                                if fx.get("ytd_yen") is not None else "取れていない")})

    # 値動きは静かなのに心理は慎重
    vix = mc.get("vix")
    fg = (mc.get("fear_greed") or {}).get("value")
    if vix is not None and fg is not None and vix < 18 and fg <= 45:
        fgh = history.get("fear_greed") or []
        move = (f"（20営業日で{fg - fgh[0]:+.0f}ポイント）"
                if len(fgh) >= 5 else "")
        take("calm_but_fearful",
             f"VIXは{vix}と落ち着いているのに、Fear & Greed は{fg}で恐怖側にいます{move}。"
             + by_id["calm_but_fearful"]["text"],
             {"VIX": str(vix), "Fear & Greed": str(fg),
              "F&Gの20営業日の変化": (f"{fg - fgh[0]:+.0f}ポイント"
                                      if len(fgh) >= 5 else "取れていない")})

    # 一部と全体の向きが逆
    sox = next((i["change_pct"] for i in mc.get("indices") or []
                if i["symbol"] == "SOX"), None)
    sp = ctx.get("return")
    if sox is not None and sp is not None and sox * sp < 0 and abs(sox) >= 1.0:
        verb = "上昇" if sox > 0 else "下落"
        whole = "下げています" if sp < 0 else "上げています"
        take("semis_diverge",
             f"半導体指数は{sox:+.1f}%と大きく{verb}しました。"
             f"よく動いていますが、米国全体としては{sp*100:+.1f}%と{whole}。"
             + by_id["semis_diverge"]["text"],
             {"SOX": f"{sox:+.1f}%", "S&P500": f"{sp*100:+.1f}%"})

    return found
