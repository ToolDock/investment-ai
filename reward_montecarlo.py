# -*- coding: utf-8 -*-
"""
謝礼（参加賞10円＋利益÷30,000円の四捨五入）が、参加者の行動しだいでどの程度になるかを
モンテカルロ法で見積もる。シナリオは scenario_scripted.json（全員共通の固定60か月）。

行動の型ごとに、パラメータを乱数で振った試行を N_TRIALS 回行い、1人あたりの謝礼の分布と、
1,000人分の合計額の分布（型の混合比つき）を出す。理論上限（完全な先読み）も出す。

実行: python reward_montecarlo.py
再現性: 乱数は固定シード。
"""
import json
import random

from utils.simulator import Simulator
from utils.storage import compute_reward

SCENARIO_PATH = "scenario_scripted.json"
N_TRIALS = 10000
SEED = 20261001
HUGE = 10 ** 15
N_PEOPLE = 1000
N_BOOT = 3000

# 型ごとの混合比（仮置き。母集団の実際の構成は分からないので、感度として複数用意する）
MIXES = {
    "標準（積立継続が最多）": {"積立継続": .40, "パニック売り": .20, "トレンド追随": .10,
                          "逆張り": .10, "ガチャガチャ": .10, "現金多め": .10},
    "全員が最良に近い（積立継続のみ）": {"積立継続": 1.0},
    "上振れ（積立継続と逆張りが半々）": {"積立継続": .5, "逆張り": .5},
}


def load():
    d = json.load(open(SCENARIO_PATH, encoding="utf-8"))
    return d["timeline"], d["settings"]


def pick_amount(rng, full_p, hi):
    return hi if rng.random() < full_p else rng.uniform(0, hi)


def b_keep(rng, ret, cash0, budget):
    """積立継続：売買しない。初期投資・積立額は満額か、ばらつく"""
    return {}, pick_amount(rng, .6, cash0), pick_amount(rng, .6, budget)


def b_panic(rng, ret, cash0, budget):
    """パニック売り：下落月に売却し、積立を止めることもある。何か月後かに戻る／戻らない"""
    thr = -rng.uniform(.03, .08)
    p = rng.uniform(.5, 1)
    frac = rng.uniform(.3, 1)
    stop = rng.random() < .5
    never = rng.random() < .3
    wait = rng.randint(2, 24)
    dec, sold_at = {}, None
    for m in range(1, len(ret) + 1):
        d = dec.setdefault(m, {})
        if sold_at is None and ret[m] <= thr and rng.random() < p:
            d["sell_amount"] = HUGE * frac
            if stop:
                d["monthly_invest"] = 0
            sold_at = m
        elif sold_at is not None and not never and m == sold_at + wait:
            d["buy_amount"] = HUGE
            d["monthly_invest"] = budget
    return dec, pick_amount(rng, .6, cash0), pick_amount(rng, .6, budget)


def b_trend(rng, ret, cash0, budget):
    """トレンド追随：直近3か月が上がれば買い増し、下がれば売る"""
    up, dn = rng.uniform(.03, .08), -rng.uniform(.03, .08)
    dec = {}
    for m in range(3, len(ret) + 1):
        c = (1 + ret[m]) * (1 + ret[m - 1]) * (1 + ret[m - 2]) - 1
        if c >= up:
            dec[m] = {"buy_amount": rng.uniform(30000, 300000)}
        elif c <= dn and rng.random() < .6:
            dec[m] = {"sell_amount": rng.uniform(30000, 300000)}
    return dec, pick_amount(rng, .6, cash0), pick_amount(rng, .6, budget)


def b_contra(rng, ret, cash0, budget):
    """逆張り：高値から大きく下げたら買い増し、戻ったら買い増しを止める"""
    thr = -rng.uniform(.08, .2)
    price = peak = 1.0
    dec = {}
    for m in range(1, len(ret) + 1):
        price *= 1 + ret[m]
        peak = max(peak, price)
        if price / peak - 1 <= thr:
            dec[m] = {"buy_amount": HUGE}
    return dec, pick_amount(rng, .6, cash0), pick_amount(rng, .6, budget)


def b_chaotic(rng, ret, cash0, budget):
    """ガチャガチャ：毎月ランダムに売買（compare_strategies.py と同じ設計）"""
    dec = {}
    for m in range(1, len(ret) + 1):
        roll = rng.random()
        if roll < .30:
            dec[m] = {"sell_amount": rng.uniform(30000, 400000)}
        elif roll < .60:
            dec[m] = {"buy_amount": rng.uniform(30000, 400000)}
        elif roll < .70:
            dec[m] = {"monthly_invest": rng.uniform(0, budget)}
    return dec, rng.uniform(0, cash0), budget


def b_cash(rng, ret, cash0, budget):
    """現金多め：投資に慎重で、少額だけ投資する"""
    return {}, rng.uniform(0, 150000), rng.uniform(0, 20000)


BEHAVIORS = {"積立継続": b_keep, "パニック売り": b_panic, "トレンド追随": b_trend,
             "逆張り": b_contra, "ガチャガチャ": b_chaotic, "現金多め": b_cash}


def reward_of(sim, timeline, dec, init_inv, mon_inv, principal):
    final = sim.simulate(timeline, dec, init_inv, mon_inv)[-1]["total"]
    reward, profit = compute_reward(final, principal)
    return reward, profit


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(int(len(xs) * p), len(xs) - 1)]


def main():
    timeline, st = load()
    cash0, budget, n = st["initial_cash"], st["monthly_invest"], st["total_months"]
    principal = cash0 + budget * n
    ret = {t["month"]: t["return"] for t in timeline}
    sim = Simulator(cash0, budget)
    rng = random.Random(SEED)

    out = {}
    pools = {}
    for name, fn in BEHAVIORS.items():
        rs = []
        for _ in range(N_TRIALS):
            dec, ii, mi = fn(rng, ret, cash0, budget)
            r, _ = reward_of(sim, timeline, dec, ii, mi, principal)
            rs.append(r)
        pools[name] = rs
        out[name] = {"mean": round(sum(rs) / len(rs), 1), "median": pct(rs, .5),
                     "p95": pct(rs, .95), "p99": pct(rs, .99), "max": max(rs),
                     "参加賞のみ(%)": round(sum(1 for x in rs if x <= 10) / len(rs) * 100, 1)}

    # 理論上限：60か月分の騰落を全て知っていた場合（毎月、翌月がプラスなら全力投資、マイナスなら全額現金）
    dec = {m: ({"buy_amount": HUGE} if ret[m + 1] > 0 else {"sell_amount": HUGE}) for m in range(1, n)}
    perfect, pprofit = reward_of(sim, timeline, dec, cash0 if ret[1] > 0 else 0, budget, principal)
    jkb, jprofit = reward_of(sim, timeline, {}, cash0, budget, principal)

    # 混合比ごとに、1,000人分の合計額の分布
    mixres = {}
    for label, w in MIXES.items():
        names, wts = list(w), list(w.values())
        totals = []
        for _ in range(N_BOOT):
            s = 0
            for _ in range(N_PEOPLE):
                s += rng.choice(pools[rng.choices(names, wts)[0]])
            totals.append(s)
        mixres[label] = {"1人あたり平均": round(sum(totals) / len(totals) / N_PEOPLE, 1),
                         "1000人合計 平均(円)": round(sum(totals) / len(totals)),
                         "1000人合計 99.9%点(円)": pct(totals, .999), "最大(円)": max(totals)}

    print(json.dumps({"元本": principal, "JKB": {"謝礼": jkb, "利益": jprofit},
                      "理論上限(完全な先読み)": {"謝礼": perfect, "利益": pprofit},
                      "行動の型ごと(1人あたりの謝礼, 円)": out,
                      "混合比ごとの1000人合計": mixres}, ensure_ascii=False, indent=2))
    print(f"\n全員が理論上限の場合の1000人合計: {perfect * N_PEOPLE:,}円")
    print(f"全員がJKB(積立継続・満額)の場合の1000人合計: {jkb * N_PEOPLE:,}円")


if __name__ == "__main__":
    main()
