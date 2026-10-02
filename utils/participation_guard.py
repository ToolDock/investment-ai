"""二度目の参加を防ぐ仕組み（1ブラウザ1参加）。

参加者は匿名なので、本人を特定して止めることはできない。ここでは、同じブラウザでの
やり直しを止める。Cookie（ie_pid）に参加時のセッションIDを残し、開始画面で見つけたら
新しい参加を受け付けず、再開番号の入力（続き・完了画面）へ案内する。
別のブラウザ・シークレットウィンドウ・Cookie削除は防げない。その場合の備えは、
クラウドワークス側の「1人1回の提出」と、提出された完了コードのセッションだけを
分析・支払いの対象にすることで補う（payout_report.py）。

動作確認では URL に ?test=1 を付けると、この判定を通らずに何度でも始められる。
そのセッションには印が付き（storage.mark_test_session）、集計と報酬から除く。
"""

import streamlit as st

COOKIE = "ie_pid"
COOKIE_DAYS = 60


def is_test_mode():
    """?test=1 で始めたセッションか。一度立てたら、そのセッションのあいだ保つ。"""
    if st.query_params.get("test") == "1":
        st.session_state["test_mode"] = True
    return bool(st.session_state.get("test_mode"))


def prior_participant_sid():
    """このブラウザで以前に参加したセッションID。無ければ None。テストモードでは常に None。"""
    if is_test_mode():
        return None
    sid = st.session_state.get("session_id")
    if sid:
        return sid
    try:
        v = st.context.cookies.get(COOKIE)
    except Exception:
        return None
    # 文字列以外（テスト環境の代替オブジェクトなど）は無視する
    return v if isinstance(v, str) and v else None


def remember_participation(sid):
    """参加したことをブラウザに残す（Cookie）。1セッションにつき一度だけ描画する。"""
    if not sid or is_test_mode() or st.session_state.get("_cookie_set") == sid:
        return
    st.session_state["_cookie_set"] = sid
    st.iframe(
        f"""<script>
        try {{
          window.parent.document.cookie =
            "{COOKIE}={sid}; max-age={COOKIE_DAYS * 86400}; path=/; SameSite=Lax; Secure";
        }} catch (e) {{}}
        </script>""",
        height=1,
    )
