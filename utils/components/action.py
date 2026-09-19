import streamlit as st


def action_selector(turn_key, investment_value, cash, current_monthly_invest, monthly_budget):
    """行動選択UI。

    - 初期状態はどれも未チェック（turn_key を key に含めてターンごとにリセット）。
    - 「何もしない」は排他で、最後に置く。それ以外は複数選択可。
    - 3つの行動の並び順は参加者ごとに固定で入れ替える。
    - 売却・購入はチェック時に金額入力ボックスを表示し、上限を超えられない。
    - 「積立設定を変更する」は 0〜monthly_budget で新しい積立額を指定する。

    戻り値の valid が False のときは「決定して次へ」を進めない。
    """
    st.subheader("行動選択")
    st.caption("この月の行動を選んでください。動かさない場合も「何もしない」を選びます。")

    # 並び順は参加者ごとに固定して入れ替える（上にある選択肢が選ばれやすい偏りを打ち消す）
    if "action_order" not in st.session_state:
        seed = st.session_state.get("session_id", "")
        st.session_state.action_order = sum(map(ord, seed)) % 3
    rot = st.session_state.action_order

    def _sell():
        s_ = st.checkbox("保有資産を売却する", key=f"sell_{turn_key}")
        amt = 0
        if s_:
            amt = st.number_input(
                "売却する金額（円）", min_value=0, max_value=int(investment_value),
                value=0, step=10000, key=f"sell_amt_{turn_key}",
                help="現在の投資資産額を超える金額は売却できません。")
        return s_, amt

    def _buy():
        b_ = st.checkbox("新たに投資信託を購入する", key=f"buy_{turn_key}")
        amt = 0
        if b_:
            amt = st.number_input(
                "購入する金額（円）", min_value=0, max_value=int(cash),
                value=0, step=10000, key=f"buy_amt_{turn_key}",
                help="現在の現金資産額を超える金額は購入できません。")
        return b_, amt

    def _change():
        c_ = st.checkbox("積立設定を変更する", key=f"change_{turn_key}")
        val = int(current_monthly_invest)
        if c_:
            val = st.number_input(
                "変更後の月々の積立額（円）", min_value=0, max_value=int(monthly_budget),
                value=int(current_monthly_invest), step=5000, key=f"monthly_{turn_key}")
        return c_, val

    fns = [_sell, _buy, _change]
    fns = fns[rot:] + fns[:rot]
    results = {}
    for fn in fns:
        results[fn.__name__] = fn()

    sell, sell_amount = results["_sell"]
    buy, buy_amount = results["_buy"]
    change, new_monthly = results["_change"]

    # 「何もしない」は最後に置く。他の選択肢を読んだうえでの選択にする
    hold = st.checkbox("何もしない", key=f"hold_{turn_key}")

    others = sell or change or buy

    valid = True
    error = None
    if not hold and not others:
        valid = False
        error = "行動を1つ以上選択してください。"
    elif hold and others:
        valid = False
        error = "「何もしない」を選ぶ場合は、他のチェックを外してください。"

    decision = {}
    labels = []
    if hold and not others:
        labels.append("何もしない")
    elif not hold:
        if sell:
            labels.append("売却")
            if sell_amount > 0:
                decision["sell_amount"] = sell_amount
        if change:
            labels.append("積立変更")
            decision["monthly_invest"] = new_monthly
        if buy:
            labels.append("購入")
            if buy_amount > 0:
                decision["buy_amount"] = buy_amount

    return {
        "decision": decision,
        "valid": valid,
        "error": error,
        "label": " + ".join(labels),
        "sell_amount": sell_amount if (not hold and sell) else 0,
        "buy_amount": buy_amount if (not hold and buy) else 0,
        "monthly_invest": new_monthly if (not hold and change) else None,
    }
