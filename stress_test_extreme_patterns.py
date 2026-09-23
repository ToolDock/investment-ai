# -*- coding: utf-8 -*-
"""
極端な操作パターンを大量に流し、Simulator・パーソナライズ・対話AIのロジックが
実プレイでは選ばれないような極端な入力でも破綻しないかを機械的に確認する
一度きりの検証スクリプト。

対象: 60か月シナリオ（scenario_scripted.json）に対して、通常のプレイでは
まず選ばないような極端な意思決定パターン（暴落のたびに全部売って高値で全力買い戻す、
毎月有り金を全部投入し続ける、資産をゼロまで枯らす等）を生成し、その上で
- Simulator.simulate() が例外を出さず、数値が破綻しない（NaN・負の残高等）か
- 群3のパーソナライズ（build_overlay_block）が全月・overconfidence高低の両方で
  例外なく動き、生成される文章が異常な長さにならないか
- 対話AI（utils.dialogue.system_variable、実際のLLM呼び出しはしない）が、
  この極端な履歴を渡されても文脈を組み立てられるか
を確認する。

実行: python stress_test_extreme_patterns.py
再現性: 乱数はすべて固定シード。何度実行しても同じ結果になる。
"""
import json
import random
import traceback

from utils.simulator import Simulator
from utils.personalization import build_overlay_block, load_slots
from utils.dialogue import system_variable

SCENARIO_PATH = "scenario_scripted.json"
HUGE = 10 ** 15
EVENT_PHASES = {"暴落", "暴騰", "急回復"}
BASE_SEED = 20260922


def load_scenario():
    d = json.load(open(SCENARIO_PATH, encoding="utf-8"))
    return d["timeline"], d["settings"]


# ── 極端な意思決定パターンの生成 ──────────────────────

def pattern_panic_every_crash(timeline):
    """暴落・安定下落のたびに全部売り、急回復・暴騰のたびに全力で買い戻す
    （最悪の高値掴み・狼狽売りを毎回繰り返す、想定しうる中で一番ひどい動き）。"""
    decisions = {}
    for t in timeline:
        if t["phase"] in {"暴落", "安定下落"}:
            decisions[t["month"]] = {"sell_amount": HUGE}
        elif t["phase"] in {"急回復", "暴騰"}:
            decisions[t["month"]] = {"buy_amount": HUGE}
    return decisions


def pattern_buy_max_always(timeline):
    """毎月、有り金を全部投入し続ける。"""
    return {t["month"]: {"buy_amount": HUGE} for t in timeline}


def pattern_sell_max_always(timeline):
    """毎月、投資資産を全部現金化し続ける。"""
    return {t["month"]: {"sell_amount": HUGE} for t in timeline}


def pattern_flip_flop(timeline):
    """1か月おきに全部売る・全部買うを繰り返す。"""
    decisions = {}
    for i, t in enumerate(timeline):
        decisions[t["month"]] = {"sell_amount": HUGE} if i % 2 == 0 else {"buy_amount": HUGE}
    return decisions


def pattern_drain_to_zero(timeline):
    """1か月目で有り金を全部現金化し、以降も積立を0円にし続ける
    （cost_basis=0が60か月続くという極端な境界値のテスト）。"""
    decisions = {1: {"sell_amount": HUGE, "monthly_invest": 0}}
    for t in timeline[1:]:
        decisions[t["month"]] = {"monthly_invest": 0}
    return decisions


def pattern_chaotic_extreme(timeline, seed):
    """乱数で毎月ランダムに売買。金額レンジに HUGE も含めて極端さを増している。"""
    rng = random.Random(seed)
    decisions = {}
    for t in timeline:
        roll = rng.random()
        if roll < 0.25:
            decisions[t["month"]] = {"sell_amount": rng.choice([HUGE, rng.uniform(0, 500000)])}
        elif roll < 0.5:
            decisions[t["month"]] = {"buy_amount": rng.choice([HUGE, rng.uniform(0, 500000)])}
        elif roll < 0.65:
            decisions[t["month"]] = {"monthly_invest": rng.uniform(0, 200000)}
    return decisions


PATTERNS = {
    "panic_every_crash": pattern_panic_every_crash,
    "buy_max_always": pattern_buy_max_always,
    "sell_max_always": pattern_sell_max_always,
    "flip_flop": pattern_flip_flop,
    "drain_to_zero": pattern_drain_to_zero,
    "ignore_all(JKB)": lambda tl: {},
}
for _i in range(5):
    PATTERNS[f"chaotic_extreme_{_i}"] = (
        lambda tl, _i=_i: pattern_chaotic_extreme(tl, BASE_SEED + _i))


# ── 検証 ──────────────────────────────────────

def check_numeric_sanity(hist):
    """NaN・負の現金・負の投資評価額など、あってはいけない値がないかを確認する。"""
    problems = []
    for s in hist:
        for key in ("cash", "invest_value", "total", "cost_basis"):
            v = s[key]
            if v != v:  # NaN check
                problems.append(f"month={s['month']} {key} is NaN")
            elif v < 0:
                problems.append(f"month={s['month']} {key} is negative ({v})")
        if s["pl_pct"] != s["pl_pct"]:
            problems.append(f"month={s['month']} pl_pct is NaN")
    return problems


def run_pattern(name, gen, timeline, settings):
    initial_cash = settings["initial_cash"]
    monthly_budget = settings["monthly_invest"]
    sim = Simulator(initial_cash, monthly_budget)
    decisions = gen(timeline)

    result = {"pattern": name, "errors": []}
    try:
        hist = sim.simulate(timeline, decisions, initial_invest=initial_cash,
                             initial_monthly_invest=monthly_budget)
    except Exception:
        result["errors"].append("Simulator.simulate crashed:\n" + traceback.format_exc())
        return result

    result["final_total"] = hist[-1]["total"]
    result["errors"].extend(check_numeric_sanity(hist))

    # ── 群3パーソナライズを全月・overconfidence高低の両方で流す ──
    kb = load_slots()
    rng = random.Random(BASE_SEED + (hash(name) % 1000))
    hist_log = []  # st.session_state.history 相当
    for m in range(1, len(timeline) + 1):
        t = timeline[m - 1]
        phase = t["phase"]
        is_event = phase in EVENT_PHASES
        state_m = hist[m]
        d = decisions.get(m) or {}
        action_label = "売却" if d.get("sell_amount") else ("買い増し" if d.get("buy_amount")
                        else "何もしない")

        for oc in (1.0, -1.0):
            try:
                overlay, slot_id = build_overlay_block(
                    oc, hist_log, m,
                    state={"invest_value": state_m["invest_value"], "pl_pct": state_m["pl_pct"]},
                    asset_history=hist, timeline=timeline, kb=kb)
                if not overlay["text"] or len(overlay["text"]) > 2000:
                    result["errors"].append(
                        f"month={m} oc={oc}: overlay text length abnormal "
                        f"({len(overlay['text'])} chars)")
                if slot_id not in kb["slots"]:
                    result["errors"].append(f"month={m} oc={oc}: unknown slot_id {slot_id}")
            except Exception:
                result["errors"].append(
                    f"month={m} oc={oc}: build_overlay_block crashed:\n" +
                    traceback.format_exc())

        # ── 対話AIのプロンプト組み立て（実際のLLM呼び出しはしない）──
        try:
            dr = t.get("daily_report") or {}
            report_for_ai = {"headline": dr.get("headline", ""),
                              "blocks": dr.get("blocks") or [{"text": "ダミー本文", "chart": None}]}
            pf_for_ai = {"cash": state_m["cash"], "invested_value": state_m["invest_value"],
                         "cost_basis": state_m["cost_basis"]}
            recent_actions = [{"label": f"{h['month']}か月目", "phase": h.get("phase"),
                               "action": h.get("action")} for h in hist_log[-3:]]
            system_variable(report_for_ai, pf_for_ai, recent_days=None, unit="month",
                             recent_actions=recent_actions)
        except Exception:
            result["errors"].append(
                f"month={m}: dialogue.system_variable crashed:\n" + traceback.format_exc())

        hist_log.append({
            "month": m, "phase": phase, "is_event": is_event,
            "action": action_label,
            "sell_impulse": rng.randint(1, 5) if is_event else None,
            "anxiety": rng.randint(1, 5) if is_event else None,
        })

    return result


def main():
    timeline, settings = load_scenario()
    all_results = [run_pattern(name, gen, timeline, settings) for name, gen in PATTERNS.items()]

    total_errors = 0
    for r in all_results:
        n = len(r["errors"])
        total_errors += n
        status = "OK" if n == 0 else f"NG({n}件)"
        final = r.get("final_total")
        final_s = f"{final:,}円" if final is not None else "-"
        print(f"[{status}] {r['pattern']:<20} 最終資産={final_s}")
        for e in r["errors"][:5]:
            print("    -", e.splitlines()[0])
        if n > 5:
            print(f"    ...ほか{n - 5}件")

    print()
    print(f"パターン数: {len(all_results)} / 合計エラー件数: {total_errors}")


if __name__ == "__main__":
    main()
