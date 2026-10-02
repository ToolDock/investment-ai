# -*- coding: utf-8 -*-
"""ランク別の人数をモンテカルロ法で見積もり、2段目タスクの件数を決める材料にする。
実行: python rank_montecarlo.py
"""
import random
from reward_montecarlo import (BEHAVIORS, MIXES, load, reward_of, pct)
from utils.simulator import Simulator
from utils.rank import reward_rank

N_TRIALS = 10000
N_BOOT = 20000
SEED = 20261002
RANKS = ["S", "A", "B", "C", "D"]
MIN_COUNT = {"S": 7, "A": 9, "B": 12, "C": 20, "D": 60}
MIXES = dict(MIXES)
MIXES["クラウドワーカー想定（積立継続と逆張りが多め、売買は少なめ）"] = {
    "積立継続": .35, "逆張り": .15, "現金多め": .15, "トレンド追随": .10, "パニック売り": .15, "ガチャガチャ": .10}
MIXES["参加賞狙い（現金多め・ガチャが多い）"] = {
    "現金多め": .35, "ガチャガチャ": .25, "積立継続": .2, "パニック売り": .1, "トレンド追随": .1}


def main():
    timeline, st = load()
    cash0, budget, n = st["initial_cash"], st["monthly_invest"], st["total_months"]
    principal = cash0 + budget * n
    ret = {t["month"]: t["return"] for t in timeline}
    sim = Simulator(cash0, budget)
    rng = random.Random(SEED)

    pools = {}
    print("【行動の型ごとのランク分布(%)】")
    for name, fn in BEHAVIORS.items():
        ranks = []
        for _ in range(N_TRIALS):
            dec, ii, mi = fn(rng, ret, cash0, budget)
            r, _ = reward_of(sim, timeline, dec, ii, mi, principal)
            ranks.append(reward_rank(r))
        pools[name] = ranks
        print(f"{name}: " + " ".join(f"{k}={ranks.count(k)/len(ranks)*100:.1f}" for k in RANKS))

    for people in (8, 20, 60):
        print(f"\n===== 参加者 {people} 人のとき、ランクごとの人数 =====")
        worst = {k: 0 for k in RANKS}
        for label, w in MIXES.items():
            names, wts = list(w), list(w.values())
            cnt = {k: [] for k in RANKS}
            for _ in range(N_BOOT):
                c = {k: 0 for k in RANKS}
                for _ in range(people):
                    c[rng.choice(pools[rng.choices(names, wts)[0]])] += 1
                for k in RANKS:
                    cnt[k].append(c[k])
            print(f"[{label}]")
            for k in RANKS:
                xs = cnt[k]
                p999 = pct(xs, .999)
                worst[k] = max(worst[k], p999)
                print(f"  {k}: 平均 {sum(xs)/len(xs):.1f} / 95%点 {pct(xs,.95)} / 99.9%点 {p999} / 最大 {max(xs)}")
        print(f"→ {people}人のとき、全混合比の99.9%点の最大: " + " ".join(f"{k}={worst[k]}" for k in RANKS))


if __name__ == "__main__":
    main()
