"""合成マーケットコンテキスト生成器。

台本（scenario）の月次リターンから、日報に表示する
VIX・Fear&Greed・セクターヒートマップ・各指数を決定論的に生成する。
較正パラメータは knowledge/market_calibration.json（実データ較正＋文献値）。
seed 固定なので全群で同一・再現可能（研究要件）。
"""

import os
import json
import math
import random
import statistics

CAL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "knowledge",
    "market_calibration.json",
)


def load_calibration():
    with open(CAL_PATH, encoding="utf-8") as f:
        return json.load(f)


def _classify(value, bands):
    for lo, hi, label in bands:
        if lo <= value <= hi:
            return label
    return bands[-1][2]


def _realized_vol_3m(returns, i):
    window = returns[max(0, i - 2):i + 1]
    if len(window) >= 2:
        vol = statistics.pstdev(window)
    else:
        # 3ヶ月未満は当月の値動きの大きさで代用
        vol = abs(window[0])
    return vol * math.sqrt(12)


def compute_drawdowns(returns):
    """月次リターンから各月のドローダウン（%）と、その時点までの最大下落幅を返す。"""
    price = 1.0
    peak = 1.0
    result = []
    worst = 0.0
    for r in returns:
        price *= (1 + r)
        peak = max(peak, price)
        dd = (price / peak - 1) * 100
        worst = min(worst, dd)
        result.append({"current": round(dd, 1), "max_so_far": round(worst, 1)})
    return result


def generate_market_context(timeline, calibration=None):
    """timeline（各要素に 'month' と 'return' を持つ）から月ごとの
    market_context のリストを返す。"""
    cal = calibration or load_calibration()
    vix_c = cal["vix"]
    fg_c = cal["fear_greed"]
    sector_betas = cal["sector_betas"]
    sector_noise = cal["sector_noise_sd"]
    index_betas = cal["index_betas"]
    index_noise = cal["index_noise_sd"]
    base_seed = cal.get("seed", 0)

    returns = [m["return"] for m in timeline]
    drawdowns = compute_drawdowns(returns)
    vix_lo, vix_hi = vix_c["clip"]

    contexts = []
    prev_vix = None

    for i, m in enumerate(timeline):
        r = m["return"]
        month = m["month"]

        # ── VIX（実データ較正）
        realized_vol = _realized_vol_3m(returns, i)
        downside = max(0.0, -r)
        vix = vix_c["const"] + vix_c["trailing_vol_coef"] * realized_vol \
            + vix_c["downside_coef"] * downside
        vix = round(min(max(vix, vix_lo), vix_hi), 1)

        # ── Fear & Greed（VIX＝恐怖側 ＋ 当月重視モメンタム＝強欲側）
        weights = fg_c["momentum_weights"]  # [当月, 前月, 前々月]
        recent = returns[max(0, i - 2):i + 1]
        momentum = sum(w * ret for w, ret in zip(weights, reversed(recent)))
        fg_lo, fg_hi = fg_c["clip"]
        fg = 50 - fg_c["vix_coef"] * (vix - fg_c["vix_neutral"]) \
            + fg_c["momentum_coef"] * momentum
        fg = int(round(min(max(fg, fg_lo), fg_hi)))
        fg_class = _classify(fg, fg_c["bands"])

        # ── 月ごとにシードを固定してノイズを再現可能に
        rng = random.Random(base_seed + month)

        # ── セクターヒートマップ（全体リターン×β＋固定ノイズ）
        sectors = []
        for name, beta in sector_betas.items():
            change = r * beta + rng.gauss(0, sector_noise)
            sectors.append({"sector": name, "change_pct": round(change * 100, 2)})
        sectors.sort(key=lambda s: s["change_pct"], reverse=True)

        # ── 各指数（対S&P500β＋固定ノイズ）
        indices = []
        for name, beta in index_betas.items():
            sd = index_noise.get(name, 0.0)
            noise = rng.gauss(0, sd) if sd > 0 else 0.0
            change = r * beta + noise
            indices.append({"symbol": name, "change_pct": round(change * 100, 2)})

        contexts.append({
            "month": month,
            "vix": vix,
            "vix_change": None if prev_vix is None else round(vix - prev_vix, 1),
            "fear_greed": {"value": fg, "classification": fg_class},
            "indices": indices,
            "sectors": sectors,
            "drawdown": drawdowns[i],
        })
        prev_vix = vix

    return contexts
