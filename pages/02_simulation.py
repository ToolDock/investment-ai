import streamlit as st
import streamlit.components.v1 as components

from utils.load_scenario import load_scenario
from utils.simulator import Simulator
from utils.storage import (
    save_response, finalize_participant, save_personalization, save_progress, get_progress_status,
)
from utils.personalization import build_overlay_block
from utils.components.chart import draw_chart, draw_market_chart
from utils.components.market_dashboard import show_market_dashboard
from utils.components.news import show_news
from utils.components.sns import show_sns
from utils.components.knowledge import show_reference
from utils.components.daily_report import show_daily_report
from utils.components.action import action_selector
from utils.components.questionnaire import show_questionnaire

MONTHLY_BUDGET = 50000                          # 毎月の余剰資金
EVENT_PHASES = {"暴落", "暴騰", "急回復"}         # 相場変動月＝行動選択を強制する局面

st.set_page_config(page_title="長期投資シミュレーション", layout="wide")

# サイドバーの自動ページ一覧から直接このページを開くと session_id が無いまま
# デフォルト値で進んでしまい、記録も再開コードも一切発行されない。それを防ぐガード
if "session_id" not in st.session_state:
    st.warning("実験がまだ開始されていません。「app」ページから始めてください。")
    if st.button("appページに戻る", width="stretch"):
        st.switch_page("app.py")
    st.stop()


def _scroll_to_top():
    # 月が変わったらページの先頭に戻す。描画が終わる前に走ると効かないので数回試す
    components.html(
        """<script>
        const sels = ['[data-testid="stMain"]', '[data-testid="stAppViewContainer"]',
                      '.stMainBlockContainer', 'section.main', '.main'];
        function toTop() {
          const d = window.parent.document;
          for (const s of sels) {
            const el = d.querySelector(s);
            if (el && el.scrollHeight > el.clientHeight) { el.scrollTop = 0; }
          }
          if (d.scrollingElement) d.scrollingElement.scrollTop = 0;
          window.parent.scrollTo(0, 0);
        }
        [0, 60, 200, 500].forEach(t => setTimeout(toTop, t));
        </script>""",
        height=0,
    )


if st.session_state.pop("scroll_top", False):
    _scroll_to_top()

scenario = load_scenario()
timeline = scenario["timeline"]
settings = scenario["settings"]
QITEMS = scenario["turns"][0]["questionnaire"]["items"]

# ── セッション状態 ───────────────────────
if "month_idx" not in st.session_state:
    st.session_state.month_idx = 0
if "group" not in st.session_state:
    st.session_state.group = 1
if "decisions" not in st.session_state:
    st.session_state.decisions = {}
if "history" not in st.session_state:
    st.session_state.history = []

initial_invest = st.session_state.get("initial_invest", settings["initial_cash"])
initial_monthly = st.session_state.get("monthly_invest", MONTHLY_BUDGET)

sim = Simulator(settings["initial_cash"], MONTHLY_BUDGET)
asset_history = sim.simulate(timeline, st.session_state.decisions, initial_invest, initial_monthly)

idx = st.session_state.month_idx
market = timeline[idx]
month = market["month"]
phase = market["phase"]
is_event = phase in EVENT_PHASES
state = asset_history[month]  # asset_history[0]=0か月目, [m]=m月目

# ── 資産・値動きの表示 ───────────────────
st.title("長期投資シミュレーション")
st.subheader(f"{month}か月目（全{len(timeline)}か月）")

resume_code = st.session_state.get("resume_code")
if resume_code:
    with st.sidebar:
        st.caption("中断・再開用の番号")
        st.code(resume_code)
        status = get_progress_status(st.session_state.get("session_id"))
        remaining_note = f"（期限まで残り{status[1]}日）" if status else ""
        st.caption(f"途中で閉じても、開始日から1週間以内ならこの番号で再開できます。{remaining_note}")

r = market["return"] * 100
r_color = "#2e7d32" if r > 0 else ("#c62828" if r < 0 else "#78909c")
st.markdown(
    "<div style='margin:6px 0 18px'>"
    "<span style='font-size:0.9rem;color:#888'>市場の値動き　／　局面："
    f"{phase}</span><br>"
    "<span style='font-size:1.35rem;font-weight:600'>今月のS&amp;P500　</span>"
    f"<span style='font-size:2.6rem;font-weight:800;color:{r_color};"
    f"vertical-align:-2px'>{r:+.1f}%</span>"
    "</div>",
    unsafe_allow_html=True,
)

draw_market_chart(timeline, month)

st.divider()

st.markdown("#### あなたの資産")

pl = state["pl_pct"]
pl_color = "#2e7d32" if pl > 0 else ("#c62828" if pl < 0 else "#78909c")
st.markdown(f"### 総資産　{state['total']:,} 円")
c1, c2, c3 = st.columns(3)
c1.metric("投資資産", f"{state['invest_value']:,} 円")
c2.metric("現金資産", f"{state['cash']:,} 円")
c3.markdown(
    "<div style='font-size:0.8rem;color:#888'>含み損益（取得原価に対して）</div>"
    f"<div style='font-size:1.6rem;font-weight:700;color:{pl_color}'>{pl:+.2f}%</div>"
    f"<div style='font-size:0.78rem;color:#888'>取得原価 {state['cost_basis']:,} 円</div>",
    unsafe_allow_html=True,
)

draw_chart(asset_history, month,
           initial_cash=settings["initial_cash"], monthly_budget=MONTHLY_BUDGET)

st.caption("上の大きなチャートは市場（S&P500）の推移、こちらはあなたの資産の推移です。"
           "灰色の点線が投入した金額の累計で、青い線との差が相場での損益です。")

# ── 市況・ニュース・SNS・参考書・日報（全群共通の情報） ──
show_market_dashboard(market.get("market_context"))
show_news(market["news"])
show_sns(market["sns"])
show_reference(phase, timeline=timeline, month=month)

overlay = None
if st.session_state.group == 3:
    # 層2（状態の翻訳）用に当月の資産状態を渡す。総資産・含み損益は毎月必ず存在するので、
    # 層3/4（行動履歴・属性）のスロットとは別に、この一文だけは常に追加される。
    # asset_history / timeline は節目（指数の最高値更新・含み損からの復帰）の判定に使う
    overlay, slot_id = build_overlay_block(
        st.session_state.get("overconfidence"), st.session_state.history, month,
        state={"total": state["total"], "pl_pct": state["pl_pct"]},
        asset_history=asset_history, timeline=timeline)
    if "session_id" in st.session_state:
        save_personalization(st.session_state.session_id, month, slot_id)

show_daily_report(market["daily_report"], st.session_state.group,
                  timeline=timeline, month=month, overlay=overlay)

st.divider()

# ── 行動フェーズ ─────────────────────────
# 「最後のアンケートに進む」ボタンが if proceed: の中でしか存在しないと、
# それ自体をクリックした再実行では proceed が False に戻り、ボタンごと消えて
# 何も起きない（＝押しても反応しない）バグになる。完了状態を session_state に
# 持たせ、以後の再実行でも完了画面を出し続けるようにする
if st.session_state.get("simulation_done"):
    st.success("シミュレーション終了")
    st.metric("最終資産", f"{st.session_state.final_asset:,} 円")
    if st.button("最後のアンケートに進む", width="stretch"):
        st.switch_page("pages/03_post_survey.py")
    with st.expander("実験ログを見る"):
        st.dataframe(st.session_state.history)
else:
    # 毎月かならず行動を選ばせる。「何もしない」も明示的な選択として記録する
    if is_event:
        st.info("相場が大きく動いています。今回の行動を選んでください。")

    action = action_selector(
        idx,
        state["invest_value"],
        state["cash"],
        state["monthly_invest"],
        MONTHLY_BUDGET,
    )
    engaged = bool(action["decision"])          # 「何もしない」以外を選んだか
    answers = {}

    # 心理アンケートは相場変動月のみ（毎月聞くと疲労で答えが崩れる）
    if is_event:
        st.divider()
        answers = show_questionnaire(QITEMS, key_suffix=str(idx))

    st.divider()

    # ── 次へ進むボタン ───────────────────────
    q_done = all(v is not None for v in answers.values())
    ready = action["valid"] and q_done
    if action["error"]:
        st.warning(action["error"])
    if is_event and not q_done:
        st.caption("アンケートにすべて回答すると先に進めます。")
    proceed = st.button("決定して次へ", width="stretch", disabled=not ready)

    if proceed:
        if action["decision"]:
            st.session_state.decisions[month] = action["decision"]

        st.session_state.history.append({
            "month": month,
            "phase": phase,
            "is_event": is_event,
            "engaged": engaged,
            "action": action["label"] or "何もしない",
            "total": state["total"],
            "cash": state["cash"],
            "investment": state["invest_value"],
            "pl_pct": state["pl_pct"],
            **answers,
        })

        if "session_id" in st.session_state:
            save_response(
                st.session_state.session_id,
                month,
                phase,
                market["return"],
                is_event,
                engaged,
                action,
                state,
                answers,
            )

        if idx < len(timeline) - 1:
            st.session_state.month_idx += 1
            st.session_state.scroll_top = True

            if "session_id" in st.session_state:
                save_progress(st.session_state.session_id, {
                    "nickname": st.session_state.get("nickname"),
                    "age": st.session_state.get("age"),
                    "overconfidence": st.session_state.get("overconfidence"),
                    "initial_invest": initial_invest,
                    "monthly_invest": initial_monthly,
                    "group": st.session_state.group,
                    "participant_no": st.session_state.get("participant_no"),
                    "month_idx": st.session_state.month_idx,
                    "decisions": st.session_state.decisions,
                    "history": st.session_state.history,
                })

            st.rerun()
        else:
            final_history = sim.simulate(
                timeline, st.session_state.decisions, initial_invest, initial_monthly
            )
            final_asset = final_history[-1]["total"]
            if "session_id" in st.session_state:
                # 元本総額は現金・投資の配分によらず一定（毎月の余剰資金は選択にかかわらず
                # 全員に渡っているため）。報酬計算はここを基準にする
                total_contributed = settings["initial_cash"] + MONTHLY_BUDGET * len(timeline)
                finalize_participant(st.session_state.session_id, final_asset, total_contributed)

            st.session_state.final_asset = final_asset
            st.session_state.simulation_done = True
            st.rerun()
