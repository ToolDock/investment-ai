"""群3（パーソナライズ）の個人化ロジック。

発火条件（どの枠を使うか）はここで決める。文章は knowledge/personalization_slots.json の
固定文から月番号でローテーションして選ぶだけで、LLM には生成させない。理由は2つ。

1. 研究計画にある操作チェックのために、誰に・いつ・どの個人化が発火したかを
   コードとして再現できる必要がある（utils.storage.save_personalization で記録する）。
2. ここは chart_reading.json の「見方」と同じ、繰り返し安定して効くことが大事な部分であり、
   知識の中身を増やすものでもない。群2との差は、この1段落をどの参加者に・いつ差し込むかだけ。
"""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SLOTS_PATH = os.path.join(ROOT, "knowledge", "personalization_slots.json")


def load_slots():
    with open(SLOTS_PATH, encoding="utf-8") as f:
        return json.load(f)


def compute_slot(overconfidence, history, kb=None):
    """今月どの枠を使うかを決める。

    history は st.session_state.history と同じ形の list（直前までの月の記録）。
    行動側のトリガーは直前の1ターンだけを見る——「次のターンでだけ効く」という設計のため。
    """
    kb = kb or load_slots()
    th = kb["thresholds"]
    last = history[-1] if history else None

    if last:
        if "売却" in (last.get("action") or ""):
            return "after_sell"
        # 「売却」でないことはここまでで確定しているので、暴落局面だったかだけを見る。
        # sell_impulse の値にかかわらず、暴落を実際に耐えたという事実そのものを称賛する
        if last.get("phase") == "暴落":
            return "endured_crash"
        si = last.get("sell_impulse")
        if si is not None and si >= th["sell_impulse_min"]:
            return "after_hesitate"
        an = last.get("anxiety")
        if an is not None and an >= th["anxiety_min"]:
            return "after_anxious_event"

    oc = overconfidence if overconfidence is not None else 0.0
    return "baseline_high" if oc >= th["overconfidence"] else "baseline_low"


def pick_text(slot_id, month, kb=None):
    kb = kb or load_slots()
    texts = kb["slots"][slot_id]["texts"]
    return texts[(month - 1) % len(texts)]


def state_sentence(total, pl_pct):
    """層2（状態の翻訳）。当月の資産額・含み損益を、そのまま事実として言語化する一文。

    解釈（下がった月をどう捉えるか等）は各スロットの定型文に任せるので、ここでは
    数字を述べるだけにする。ダッシュボード表示と桁数を揃えるため pl_pct は小数2桁。
    """
    return f"あなたの投資資産は{total:,}円、取得原価に対して{pl_pct:+.2f}%です。"


def _recent_dip_depth(timeline, month, tol):
    """直近、最高値（drawdown が tol 以上）だった月からこの月の前月までの、最深の下落幅。

    month は1始まりの「今月」。month-2（0始まり）から遡り、drawdown が tol 以上の月に
    ぶつかるまでの最小値を返す（＝今回の下落局面がどれだけ深かったか）。
    """
    depth = 0.0
    for i in range(month - 2, -1, -1):
        dd = timeline[i]["market_context"]["drawdown"]["current"]
        if dd >= tol:
            break
        depth = min(depth, dd)
    return depth


def milestone_sentence(asset_history, timeline, month, kb=None):
    """層2の延長。行動ではなく「状態の節目」を検知する。

    - index_ath: 指数（S&P500）そのものが、深い下落（major_loss_pct 以下）から回復して
      この月にはじめて最高値を更新した（数%程度の浅い揺り戻しでは発火しない）
    - recovered_from_loss: 含み損益が一度 major_loss_pct 以下まで落ち込んだことがあり、
      この月にはじめてプラスに転じた（浅い下落からの回復では発火しない）

    行動履歴に基づく compute_slot の優先順位とは独立に扱う。両方の節目が同じ月に
    重なることは理論上ありうるが稀なので、該当したものをすべて連ねて返す。
    月をまたいだ履歴（前月・それ以前の最安値）を参照するため、asset_history と
    timeline をまるごと受け取る。どちらか一方でも None なら何もしない
    （overlay を作らない既存の呼び出し元との後方互換のため）。

    戻り値: 該当する節目がなければ None、あれば連結した文字列。
    """
    if asset_history is None or timeline is None or month < 2:
        return None

    kb = kb or load_slots()
    th = kb["thresholds"]
    major_loss = th.get("major_loss_pct", -10.0)
    sentences = []

    # 指数が最高値を更新した月（前月はまだ下落中だった場合に限る＝更新した"その月"だけ）。
    # ただし通常の値動きでの小さな揺り戻しまで「節目」扱いにしないよう、直近の下落が
    # major_loss_pct 以下まで深かった場合だけに絞る
    cur_dd = timeline[month - 1]["market_context"]["drawdown"]["current"]
    prev_dd = timeline[month - 2]["market_context"]["drawdown"]["current"]
    tol = th.get("ath_drawdown_tolerance", -0.05)
    if cur_dd >= tol and prev_dd < tol:
        if _recent_dip_depth(timeline, month, tol) <= major_loss:
            texts = kb["milestones"]["index_ath"]["texts"]
            sentences.append(texts[(month - 1) % len(texts)])

    # 含み損益が大きなマイナスから、この月はじめてプラスに転じた月
    cur_pl = asset_history[month]["pl_pct"]
    prev_pl = asset_history[month - 1]["pl_pct"]
    worst_so_far = min(h["pl_pct"] for h in asset_history[:month])  # month-1か月目まで
    major_loss = th.get("major_loss_pct", -10.0)
    if cur_pl >= 0 and prev_pl < 0 and worst_so_far <= major_loss:
        texts = kb["milestones"]["recovered_from_loss"]["texts"]
        sentences.append(texts[(month - 1) % len(texts)])

    return " ".join(sentences) if sentences else None


def build_overlay_block(overconfidence, history, month, state=None, kb=None,
                         asset_history=None, timeline=None):
    """今月の群3追加ブロックと、記録用のスロットIDを返す。

    state は当月の資産状態（{"total":..., "pl_pct":...}）。渡された場合のみ、
    層2の一文を先頭に追加する（呼び出し側で state を持たない既存のテスト・検証
    スクリプトとの後方互換のため任意引数にしてある）。asset_history / timeline を
    渡すと、節目（milestone_sentence）があれば state の直後・行動スロットの前に追加する。

    戻り値: (block, slot_id)。block は {"text":..., "chart": None}。
    """
    kb = kb or load_slots()
    slot_id = compute_slot(overconfidence, history, kb)

    parts = []
    if state is not None:
        parts.append(state_sentence(state["total"], state["pl_pct"]))
    milestone = milestone_sentence(asset_history, timeline, month, kb)
    if milestone:
        parts.append(milestone)
    parts.append(pick_text(slot_id, month, kb))

    return {"text": " ".join(parts), "chart": None}, slot_id
