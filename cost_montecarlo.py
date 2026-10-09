# -*- coding: utf-8 -*-
"""本実施（ランク方式）の謝礼の総額を、モンテカルロ法で見積もる。
実行: python cost_montecarlo.py
  A. 行動モデル  : reward_montecarlo.py の行動の型×混合比から、ランクごとの確率を出す
  B. パイロット実測: パイロットのランク別人数から、ディリクレ事後分布で確率の不確かさを含めて予測する
  C. 当てはめの確認: パイロットの人数が、Aの各混合比とどの程度合うか（尤度・p値）
乱数は固定シード。ワーカーIDなどの個人情報は含まない。
"""
import random
import numpy as np
from reward_montecarlo import BEHAVIORS, MIXES, load, reward_of
from utils.simulator import Simulator
from utils.rank import reward_rank

RANKS = ["S", "A", "B", "C", "D"]
EXTRA = {"S": 45, "A": 35, "B": 25, "C": 15, "D": 5}
BASE = 10
TAX = 1.1
N_TRIALS = 10000
N_SIM = 20000
SEED = 20261006
PILOT = {"S": 14, "A": 19, "B": 10, "C": 10, "D": 6}   # 有効な完了者59人（重複・コードなしを除く）
STAGE2_OK, STAGE2_N = 59, 59                            # 完了者のうち、2段目を提出した人数
N_PEOPLE = 1000

MIXES = dict(MIXES)
MIXES["クラウドワーカー想定（積立継続と逆張りが多め）"] = {
    "積立継続": .35, "逆張り": .15, "現金多め": .15, "トレンド追随": .10, "パニック売り": .15, "ガチャガチャ": .10}
MIXES["参加賞狙い（現金多め・ガチャが多い）"] = {
    "現金多め": .35, "ガチャガチャ": .25, "積立継続": .2, "パニック売り": .1, "トレンド追随": .1}


def q(a, p):
    return float(np.percentile(a, p))


def summarize(label, total):
    t = np.asarray(total, dtype=float)
    print(f"  {label}: 平均 {t.mean():,.0f} / 中央値 {q(t,50):,.0f} / 95%区間 {q(t,2.5):,.0f}〜{q(t,97.5):,.0f}"
          f" / 99.9%点 {q(t,99.9):,.0f}  （税込 平均 {t.mean()*TAX:,.0f} / 99.9%点 {q(t,99.9)*TAX:,.0f}）")


def main():
    rng = random.Random(SEED)
    nrng = np.random.default_rng(SEED)
    timeline, st = load()
    cash0, budget, n = st["initial_cash"], st["monthly_invest"], st["total_months"]
    principal = cash0 + budget * n
    ret = {t["month"]: t["return"] for t in timeline}
    sim = Simulator(cash0, budget)

    # 行動の型ごとのランク確率
    pool = {}
    for name, fn in BEHAVIORS.items():
        c = {k: 0 for k in RANKS}
        for _ in range(N_TRIALS):
            dec, ii, mi = fn(rng, ret, cash0, budget)
            r, _ = reward_of(sim, timeline, dec, ii, mi, principal)
            c[reward_rank(r)] += 1
        pool[name] = np.array([c[k] / N_TRIALS for k in RANKS])
    print("【行動の型ごとのランク確率(%)】 " + " ".join(RANKS))
    for name, p in pool.items():
        print(f"  {name}: " + " ".join(f"{x*100:5.1f}" for x in p))

    extra = np.array([EXTRA[k] for k in RANKS], dtype=float)
    pil = np.array([PILOT[k] for k in RANKS])
    n_pil = pil.sum()
    print(f"\n【パイロット（有効な完了者 {n_pil} 人）】 " + " ".join(f"{k}={PILOT[k]}({PILOT[k]/n_pil*100:.1f}%)" for k in RANKS))
    print(f"  1人あたり平均 {BASE + (pil*extra).sum()/n_pil:.2f} 円（参加賞{BASE}円を含む）。最大は {BASE+EXTRA['S']} 円（Sランク）")

    # --- B. パイロット実測（ディリクレ事後） ---
    print(f"\n【B. パイロット実測に基づく、{N_PEOPLE}人分の謝礼の総額（税抜、円）】")
    p_post = nrng.dirichlet(pil + 1, size=N_SIM)                 # 事前は一様
    q2 = nrng.beta(STAGE2_OK + 1, STAGE2_N - STAGE2_OK + 1, size=N_SIM)   # 2段目の提出率
    total_b = np.empty(N_SIM)
    counts_b = np.empty((N_SIM, 5))
    for i in range(N_SIM):
        c = nrng.multinomial(N_PEOPLE, p_post[i])
        counts_b[i] = c
        sub = nrng.binomial(c, q2[i])                           # 2段目を出した人数（ランク別）
        total_b[i] = BASE * N_PEOPLE + (sub * extra).sum()
    summarize("パイロット実測（確率の不確かさ込み）", total_b)
    print("  ランク別の人数（1,000人のとき）: " + " ".join(
        f"{k}: 平均{counts_b[:,j].mean():.0f}/99.9%点{q(counts_b[:,j],99.9):.0f}" for j, k in enumerate(RANKS)))
    print(f"  2段目の提出率の事後平均 {q2.mean()*100:.1f}%（95%区間 {q(q2,2.5)*100:.1f}〜{q(q2,97.5)*100:.1f}%）")
    for lab, N in (("500人", 500), ("660人", 660)):
        tot = np.empty(N_SIM)
        for i in range(N_SIM):
            c = nrng.multinomial(N, p_post[i]); sub = nrng.binomial(c, q2[i])
            tot[i] = BASE * N + (sub * extra).sum()
        summarize(f"（参考）{lab}", tot)

    # --- A. 行動モデル ---
    print(f"\n【A. 行動モデルに基づく、{N_PEOPLE}人分の謝礼の総額（税抜、円）】")
    mix_prob = {}
    for label, w in MIXES.items():
        p = sum(pool[k] * v for k, v in w.items())
        mix_prob[label] = p / p.sum()
        tot = np.empty(N_SIM)
        for i in range(N_SIM):
            c = nrng.multinomial(N_PEOPLE, mix_prob[label])
            tot[i] = BASE * N_PEOPLE + (c * extra).sum()
        summarize(label, tot)

    # --- C. パイロットとの当てはめ ---
    print("\n【C. パイロットの人数との当てはめ（多項分布の尤度、p値＝モデルのもとで観測より尤度が低い試行の割合）】")
    def ll(counts, p):
        return float((counts * np.log(np.clip(p, 1e-12, 1))).sum())
    for label, p in mix_prob.items():
        obs = ll(pil, p)
        sims = nrng.multinomial(int(n_pil), p, size=N_SIM)
        s_ll = (sims * np.log(np.clip(p, 1e-12, 1))).sum(axis=1)
        pval = float((s_ll <= obs).mean())
        print(f"  {label}: 対数尤度 {obs:.2f}、p値 {pval:.3f}、モデルの予測(%) " + " ".join(f"{x*100:.0f}" for x in p))

    # --- 構造的な上限 ---
    print("\n【構造的な上限（全員がSランクで、2段目も提出）】")
    print(f"  税抜 {(BASE+EXTRA['S'])*N_PEOPLE:,} 円 / 税込 {(BASE+EXTRA['S'])*N_PEOPLE*TAX:,.0f} 円（1人最大55円のため、10万円は超えない）")

    # --- 件数（2段目タスク）の目安：1,000人のときの99.9%点 ---
    print("\n【2段目タスクの件数の目安（1,000人のとき、ランクごとの99.9%点。件数は減らせないので、余裕を持って設定する）】")
    print("  " + " ".join(f"{k}={q(counts_b[:,j],99.9):.0f}" for j, k in enumerate(RANKS)))


if __name__ == "__main__":
    main()
