# -*- coding: utf-8 -*-
"""
3つの投資戦略（何もせず積立／ガチャガチャ動かす／全知全能の完璧な選択）を
実験用シナリオ（scenario_scripted.json、60か月）で比較する一度きりの分析スクリプト。

研究上の主張：「この実験相場は不調な期間が長いにもかかわらず、何もせず積立を
続ける方が無秩序な売買より明確に強く、未来を完全に知っていた場合の結果とも
桁違いには離れていない」ことを、実際の数値で示す。

実行: python compare_strategies.py
再現性: すべての乱数は固定シード。何度実行しても同じ結果になる。
"""
import json
import random

from utils.simulator import Simulator

SCENARIO_PATH = "scenario_scripted.json"
HUGE = 10 ** 15
N_TRIALS = 10000
BASE_SEED = 20260921


def load_scenario():
    d = json.load(open(SCENARIO_PATH, encoding="utf-8"))
    timeline = d["timeline"]
    settings = d["settings"]
    ret = {t["month"]: t["return"] for t in timeline}
    return timeline, settings, ret


def market_stress_stats(timeline):
    """『不調な期間が長い』ことを裏づける客観指標。"""
    price = peak = 1.0
    dds = []
    worst, worst_month = 0.0, None
    for t in timeline:
        price *= (1 + t["return"])
        peak = max(peak, price)
        dd = (price / peak - 1) * 100
        dds.append(dd)
        if dd < worst:
            worst, worst_month = dd, t["month"]
    underwater = sum(1 for dd in dds if dd < -0.01)
    longest = cur = 0
    for dd in dds:
        cur = cur + 1 if dd < -0.01 else 0
        longest = max(longest, cur)
    return {
        "max_drawdown_pct": round(worst, 1),
        "max_drawdown_month": worst_month,
        "months_underwater": underwater,
        "total_months": len(timeline),
        "longest_underwater_streak": longest,
        "price_multiple": round(price, 3),
    }


def run_jkb(sim, timeline, initial_cash, monthly_budget):
    """1. 何もせず積み立て（Just Keep Buying）。初期資金は即全額投入、毎月満額積立、
    一度も売買しない。"""
    hist = sim.simulate(timeline, {}, initial_invest=initial_cash,
                         initial_monthly_invest=monthly_budget)
    return hist[-1]


def run_perfect(sim, timeline, ret, initial_cash, monthly_budget, n_months):
    """2. 全知全能・完璧な選択。60か月分の騰落をあらかじめ知っている前提で、
    翌月がプラスなら全力投資、マイナスなら全額現金に退避する（手数料・税金は考慮しない）。
    月内の処理順（今月のリターン適用→今月分積立→今月の決定）により、ある月の決定は
    「翌月」のリターンに対する持ち高を決めるので、次の月の符号だけを見れば足りる
    （現金・投資額を厳密に把握しなくても、buy_amount/sell_amountに巨大な値を渡せば
    Simulator側のmin()でその時点の実際の残高に自動的に丸められる）。"""
    decisions = {}
    for m in range(1, n_months):
        next_r = ret[m + 1]
        decisions[m] = {"buy_amount": HUGE} if next_r > 0 else {"sell_amount": HUGE}
    initial_invest = initial_cash if ret[1] > 0 else 0
    hist = sim.simulate(timeline, decisions, initial_invest=initial_invest,
                         initial_monthly_invest=monthly_budget)
    return hist[-1]


def run_chaotic_trial(sim, timeline, monthly_budget, n_months, initial_invest, seed):
    """3. ガチャガチャ動かした場合の1試行。相場の根拠なしに、毎月ランダムな確率で
    ランダムな額を売買する（乱数額は現在の残高を上回ればSimulator側のmin()で
    自動的に丸められるので、事前に残高を追跡しなくてよい）。"""
    rng = random.Random(seed)
    decisions = {}
    for m in range(1, n_months + 1):
        roll = rng.random()
        if roll < 0.30:
            decisions[m] = {"sell_amount": rng.uniform(30000, 400000)}
        elif roll < 0.60:
            decisions[m] = {"buy_amount": rng.uniform(30000, 400000)}
        elif roll < 0.70:
            decisions[m] = {"monthly_invest": rng.uniform(0, monthly_budget)}
        # 残り30%は何もしない
    hist = sim.simulate(timeline, decisions, initial_invest=initial_invest,
                         initial_monthly_invest=monthly_budget)
    return hist[-1]["total"]


def summarize(totals, principal, jkb_total):
    totals = sorted(totals)
    n = len(totals)
    mean = sum(totals) / n

    def pct(p):
        return totals[min(int(n * p), n - 1)]

    return {
        "mean": mean,
        "median": pct(0.50),
        "p05": pct(0.05),
        "p95": pct(0.95),
        "min": totals[0],
        "max": totals[-1],
        "below_principal_pct": sum(1 for x in totals if x < principal) / n * 100,
        "below_jkb_pct": sum(1 for x in totals if x < jkb_total) / n * 100,
    }


def main():
    timeline, settings, ret = load_scenario()
    initial_cash = settings["initial_cash"]
    monthly_budget = settings["monthly_invest"]
    n_months = settings["total_months"]
    principal = initial_cash + monthly_budget * n_months
    sim = Simulator(initial_cash, monthly_budget)

    stress = market_stress_stats(timeline)
    jkb = run_jkb(sim, timeline, initial_cash, monthly_budget)
    perfect = run_perfect(sim, timeline, ret, initial_cash, monthly_budget, n_months)

    # ガチャガチャ（A）：初期投資割合もランダム（0〜100%）— 最も「何も考えていない」設定
    totals_a = [
        run_chaotic_trial(sim, timeline, monthly_budget, n_months,
                           initial_invest=initial_cash * random.Random(BASE_SEED + i).uniform(0, 1),
                           seed=BASE_SEED + i)
        for i in range(N_TRIALS)
    ]
    # ガチャガチャ（B）：初期投資はJKBと同条件（即全額投入）に揃え、
    # 「毎月の無秩序な売買」だけを切り出して比較する統制版
    totals_b = [
        run_chaotic_trial(sim, timeline, monthly_budget, n_months,
                           initial_invest=initial_cash, seed=BASE_SEED + 100000 + i)
        for i in range(N_TRIALS)
    ]

    summary_a = summarize(totals_a, principal, jkb["total"])
    summary_b = summarize(totals_b, principal, jkb["total"])

    result = {
        "settings": {
            "initial_cash": initial_cash, "monthly_budget": monthly_budget,
            "n_months": n_months, "principal": principal, "n_trials": N_TRIALS,
            "base_seed": BASE_SEED,
        },
        "market_stress": stress,
        "jkb_total": jkb["total"],
        "perfect_total": perfect["total"],
        "chaotic_random_initial": summary_a,
        "chaotic_matched_initial": summary_b,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    print("\n--- 読み方の要点 ---")
    print(f"元本: {principal:,}円")
    print(f"① 何もせず積立: {jkb['total']:,}円（元本比 {jkb['total']/principal:.2f}倍）")
    print(f"② 完璧な選択  : {perfect['total']:,}円（元本比 {perfect['total']/principal:.2f}倍、①の{perfect['total']/jkb['total']:.2f}倍）")
    print(f"①が②に対して捉えた割合（総資産ベース）: {jkb['total']/perfect['total']*100:.1f}%")
    excess_jkb = jkb['total'] - principal
    excess_perfect = perfect['total'] - principal
    print(f"①が②に対して捉えた割合（元本超過分ベース）: {excess_jkb/excess_perfect*100:.1f}%")
    print(f"③ガチャガチャ（初期割合も乱数）平均: {summary_a['mean']:,.0f}円、①に負けた試行 {summary_a['below_jkb_pct']:.1f}%")
    print(f"③ガチャガチャ（初期はJKBと同条件）平均: {summary_b['mean']:,.0f}円、①に負けた試行 {summary_b['below_jkb_pct']:.1f}%")


if __name__ == "__main__":
    main()
