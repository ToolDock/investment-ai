"""群3（パーソナライズ）の個人化ロジック。

発火条件（どの枠を使うか）はここで決める。文章は knowledge/personalization_slots.json の
固定文から月番号（または発生回数）でローテーションして選ぶだけで、LLM には生成させない。
理由は2つ。

1. 研究計画にある操作チェックのために、誰に・いつ・どの個人化が発火したかを
   コードとして再現できる必要がある（utils.storage.save_personalization で記録する）。
2. ここは chart_reading.json の「見方」と同じ、繰り返し安定して効くことが大事な部分であり、
   知識の中身を増やすものでもない。群2との差は、この1段落をどの参加者に・いつ差し込むかだけ。

2026-09-22 実機での通し確認（本人による33か月分のプレイ）で、直前1ターンしか見ない設計が
原因の複数の不整合が見つかったため、履歴を全カ月分参照する方式に拡張した（本人の指示：
「これまでの履歴を全カ月分参照するべきです。本番環境でも同様です」）。合わせて、AI日報の
役割を「簡潔な事実＋困ったら対話AIへ誘導」に絞る方針を確認した（対話AI側は utils/dialogue.py
が別に担当しており、感情面のケアはそちらに委ねる）。
"""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SLOTS_PATH = os.path.join(ROOT, "knowledge", "personalization_slots.json")


def load_slots():
    with open(SLOTS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _is_sell_action(action):
    return "売却" in (action or "")


def _is_buy_action(action):
    return "買い増し" in (action or "") or "買付" in (action or "") or (action or "") == "購入"


def _net_position_state(history):
    """全履歴のうち、最後に発生した売却／買い増しのどちらが新しいかを見て、
    いま「以前売った分をまだ市場に戻していない」状態かどうかを判定する。

    戻り値: "out"（売却したまま） / "returned"（その後買い増しして戻っている） /
    None（一度も能動的な売買をしていない＝ずっと積立のみ）。
    """
    last_sell_month = None
    last_buy_month = None
    for h in history:
        if _is_sell_action(h.get("action")):
            last_sell_month = h["month"]
        elif _is_buy_action(h.get("action")):
            last_buy_month = h["month"]
    if last_sell_month is None:
        return None
    if last_buy_month is not None and last_buy_month > last_sell_month:
        return "returned"
    return "out"


def _trade_direction(action):
    if _is_sell_action(action):
        return "sell"
    if _is_buy_action(action):
        return "buy"
    return None


def _recent_direction_switches(history, window):
    """直近 window か月の売買方向（買い／売り）の並びで、方向が何回入れ替わったかを数える。

    「売却→買い増し→売却→買い増し」のように行き来していれば switches は増えるが、
    分割買い戻し計画のように「買い増しを何か月も続ける」一方向の実行では switches は
    0のままになる。単純な売買回数ではなく方向転換の回数を見ることで、対話AIと相談の
    うえ決めた計画的な行動を frequent_trading と誤検知しないようにする（2026-09-22、
    本人からの指摘「12カ月に分けて買い戻す計画にも反応してしまう」を受けて導入）。
    window が history 全体より大きい／None の場合は全履歴を対象にする。
    """
    recent = history[-window:] if window else history
    dirs = [_trade_direction(h.get("action")) for h in recent]
    dirs = [d for d in dirs if d is not None]
    return sum(1 for i in range(1, len(dirs)) if dirs[i] != dirs[i - 1])


def _slot_occurrence_index(overconfidence, history, kb, slot_id):
    """今月の slot_id が、これまで何回目の発生か（今回を含む、0始まり）を返す。

    history の各時点まででcompute_slotを遡って再計算し、同じslot_idが何回
    選ばれてきたかを数える。単純な月番号ローテーションだと、同じ枠が近い月に
    続けて発火したときに同じ文言が出やすい（例：分割買い戻し計画中はafter_buyが
    何か月も続く、長い暴落中はstill_out_during_crashが何か月も続く）ため、
    「これが何回目のこの枠か」で選ぶことで、実際に読者が見た回数に沿って
    ローテーションする（2026-09-22、本人からの指摘「毎回同じこと言われると
    『ん？』ってなる」「話す角度も変わるべき」を受けて全スロットに拡張）。
    overconfidence は事前アンケート由来で全期間一定なので、過去の再計算に使っても
    矛盾は生じない。history は最大でも60件程度なので計算量は問題にならない。
    """
    count = 0
    for i in range(1, len(history) + 1):
        if compute_slot(overconfidence, history[:i], kb) == slot_id:
            count += 1
    return count - 1


def compute_slot(overconfidence, history, kb=None):
    """今月どの枠を使うかを決める。

    history は st.session_state.history と同じ形の list（直前までの月の記録、
    今月の行動を含む最新の1件が末尾）。2026-09-22 以降、行動側のトリガーも
    「直前の1ターンだけ」ではなく全履歴を参照する（退避したままの検知・
    直近の売買頻度の検知のため）。
    """
    kb = kb or load_slots()
    th = kb["thresholds"]
    last = history[-1] if history else None

    # 0. 売買の方向が短期間で行き来している（＝ガチャガチャしている）場合を
    #    最優先でチェックする。単純な売買回数ではなく方向転換の回数で判定するのは、
    #    分割買い戻し計画のような一方向の計画的な実行を誤って churn 扱いしないため。
    churn_window = th.get("churn_window_months", 6)
    churn_switch_min = th.get("churn_switch_min", 2)
    if _recent_direction_switches(history, churn_window) >= churn_switch_min:
        return "frequent_trading"

    if last:
        if _is_sell_action(last.get("action")):
            return "after_sell"

        if _is_buy_action(last.get("action")):
            # 下落局面で買い増したときは、その事実を肯定する別枠にする
            if last.get("phase") in ("暴落", "安定下落"):
                return "after_buy_dip"
            return "after_buy"

        if last.get("phase") == "暴落":
            # 直前ターンは売却していなくても、それ以前の売却をまだ市場に
            # 戻していなければ「耐えた」という称賛は事実と違う（2026-09-22、
            # 実機確認で発見）。その場合は別枠にする。
            if _net_position_state(history) == "out":
                return "still_out_during_crash"
            return "endured_crash"

        si = last.get("sell_impulse")
        if si is not None and si >= th["sell_impulse_min"]:
            return "after_hesitate"
        an = last.get("anxiety")
        if an is not None and an >= th["anxiety_min"]:
            return "after_anxious_event"

    oc = overconfidence if overconfidence is not None else 0.0
    return "baseline_high" if oc >= th["overconfidence"] else "baseline_low"


def pick_text(slot_id, month, kb=None, occurrence=None):
    """slot_id の定型文を1つ選ぶ。

    occurrence（このslot_idが今回で何回目の発生か、0始まり）が渡されていれば、
    そちらでローテーションする（同じ枠が近い月に繰り返し発火しても、毎回同じ文には
    ならないようにするため）。occurrence 未指定（後方互換）の場合は従来どおり月番号で選ぶ。

    連続発火しやすいスロット（after_buy・frequent_trading・baseline_high/low・after_sell）は
    "texts"（本題、core）と"closers"（結びの一文）の組み合わせ式になっている。互いに素な
    個数（既定8×9）で組み合わせることで、本題だけの単純なローテーションより長い周期
    （既定72通り）で文言が一巡し、60か月のどんな操作パターンでも文言が重複しないようにして
    ある（2026-09-22、本人からの指示「60カ月、全く同じ文章の使いまわしはしない」を受けて導入）。
    """
    kb = kb or load_slots()
    slot = kb["slots"][slot_id]
    texts = slot["texts"]
    closers = slot.get("closers") or []

    idx = occurrence if occurrence is not None else (month - 1)
    text = texts[idx % len(texts)]
    if closers:
        text = text + " " + closers[idx % len(closers)]
    return text


def state_sentence(invest_value, pl_pct):
    """層2（状態の翻訳）。当月の投資評価額・含み損益を、そのまま事実として言語化する一文。

    解釈（下がった月をどう捉えるか等）は各スロットの定型文に任せるので、ここでは
    数字を述べるだけにする。ダッシュボード表示と桁数を揃えるため pl_pct は小数2桁。
    invest_value は現金を含まない投資評価額（Simulator._state() の "invest_value"）。
    「投資資産」という言い回しに対して現金込みの総資産（"total"）を渡すと、実際より
    多い額を投資分として語ってしまう（2026-09-21の実プレイで発見・修正）。
    """
    return f"あなたの投資資産は{invest_value:,}円、取得原価に対して{pl_pct:+.2f}%です。"


def behavior_counts(history):
    """これまでの行動の通算。重複なく数える（売却・買い増し・それ以外）。"""
    n_sell = sum(1 for h in history if _is_sell_action(h.get("action")))
    n_buy = sum(1 for h in history if _is_buy_action(h.get("action")))
    return {"months": len(history), "sell": n_sell, "buy": n_buy,
            "other": len(history) - n_sell - n_buy}


def behavior_summary_text(history):
    """対話AI向けの通算の行動要約。直近数か月だけでは「ずっと売っていない」ことが伝わらない。"""
    if not history:
        return ""
    c = behavior_counts(history)
    parts = [f"開始から{c['months']}か月：売却{c['sell']}回、買い増し{c['buy']}回、"
             f"それ以外（積立のまま・何もしない等）{c['other']}回。"]
    if c["sell"] == 0:
        parts.append("一度も売却していない（暴落局面を含めて、決めた積立を続けている）。")
    else:
        last_sell = max(h["month"] for h in history if _is_sell_action(h.get("action")))
        parts.append(f"最後の売却は{last_sell}か月目。")
    return "".join(parts)


STREAK_MIN_MONTHS = 3
STREAK_TEXTS = [
    "ここまで{n}か月、一度も売らずに続けています。",
    "開始から{n}か月、売却はゼロのままです。",
    "{n}か月間、売らずに積み立てを続けられています。",
]


def streak_sentence(history, month):
    """一度も売っていない人に、その事実をそのまま返す一文（層3：行動履歴の通算）。

    直近1〜3か月の行動だけを見る枠（compute_slot）では、「ずっと売っていない」ことは
    表に出ない（2026-10-01、60か月通しプレイで本人が指摘）。売却が一度でもあれば出さない。
    """
    if len(history) < STREAK_MIN_MONTHS:
        return None
    if behavior_counts(history)["sell"] > 0:
        return None
    return STREAK_TEXTS[month % len(STREAK_TEXTS)].format(n=len(history))


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


def edge_sentence(history, month, state, timeline, asset_history, milestone_fired=False, kb=None):
    """指数はまだ最高値に戻っていないのに、自分の資産は先に含み益へ戻っているとき、
    その差を「安いときに買い続けた成果」として返す一文。

    一度も売っていない人にだけ出す（売っていると、この説明が事実と違うため）。
    過去に含み損の時期があった場合に限る（最初からプラスだっただけの人には言わない）。
    毎月出すと単調になるので、偶数月か、含み益に転じた節目の月だけ出す。
    """
    if state is None or timeline is None or asset_history is None or month < 2:
        return None
    if behavior_counts(history)["sell"] > 0:
        return None
    dd = timeline[month - 1]["market_context"]["drawdown"]["current"]
    pl = state["pl_pct"]
    if dd > -3.0 or pl <= 0:
        return None
    if min(h["pl_pct"] for h in asset_history[:month]) >= 0:
        return None
    if not milestone_fired and month % 2 != 0:
        return None
    kb = kb or load_slots()
    texts = kb["edge_recovery"]["texts"]
    return texts[(month // 2) % len(texts)].format(dd=f"{abs(dd):.1f}%", pl=f"{pl:+.2f}%")


def build_overlay_block(overconfidence, history, month, state=None, kb=None,
                         asset_history=None, timeline=None):
    """今月の群3追加ブロックと、記録用のスロットIDを返す。

    state は当月の資産状態（{"invest_value":..., "pl_pct":...}）。invest_value は現金を
    含まない投資評価額（Simulator._state() の "invest_value"。現金込みの "total" ではない
    ——§21-2で発見・修正した「投資資産」に現金込み総資産を表示していたバグの教訓）。渡された
    場合のみ、層2の一文を先頭に追加する（呼び出し側で state を持たない既存のテスト・検証
    スクリプトとの後方互換のため任意引数にしてある）。asset_history / timeline を
    渡すと、節目（milestone_sentence）があれば state の直後・行動スロットの前に追加する。

    戻り値: (block, slot_id)。block は {"text":..., "chart": None}。
    """
    kb = kb or load_slots()
    slot_id = compute_slot(overconfidence, history, kb)

    parts = []
    if state is not None:
        parts.append(state_sentence(state["invest_value"], state["pl_pct"]))
    streak = streak_sentence(history, month)
    if streak:
        parts.append(streak)
    milestone = milestone_sentence(asset_history, timeline, month, kb)
    if milestone:
        parts.append(milestone)
    edge = edge_sentence(history, month, state, timeline, asset_history,
                         milestone_fired=bool(milestone and "プラス" in milestone), kb=kb)
    if edge:
        parts.append(edge)
    occurrence = _slot_occurrence_index(overconfidence, history, kb, slot_id) if history else None
    parts.append(pick_text(slot_id, month, kb, occurrence=occurrence))

    return {"text": " ".join(parts), "chart": None}, slot_id
