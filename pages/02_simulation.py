import streamlit as st

from utils.load_scenario import load_scenario
from utils.simulator import Simulator
from utils.storage import (
    save_response, finalize_participant, save_personalization, save_progress, get_progress_status,
    save_dialogue_turn, load_dialogue_log, load_recent_dialogue_months,
)
from utils.personalization import build_overlay_block
from utils.dialogue import reply as dialogue_reply
from utils.components.chart import draw_chart, draw_market_chart
from utils.components.market_dashboard import show_market_dashboard
from utils.components.news import show_news
from utils.components.sns import show_sns
from utils.components.knowledge import show_reference
from utils.components.daily_report import show_daily_report
from utils.components.action import action_selector
from utils.components.questionnaire import show_questionnaire
from utils.components.ui_scale import render_scale_control, inject_scale_css

MONTHLY_BUDGET = 50000                          # 毎月の余剰資金
EVENT_PHASES = {"暴落", "暴騰", "急回復"}         # 相場変動月＝行動選択を強制する局面

st.set_page_config(page_title="長期投資シミュレーション", layout="wide")

# 画面の大きさ（対話AIの入力欄が増えて窮屈に感じやすいので、既定はやや小さめ。
# サイドバーからいつでも拡大・縮小できる）
render_scale_control()
inject_scale_css()

# サイドバーの自動ページ一覧から直接このページを開くと session_id が無いまま
# デフォルト値で進んでしまい、記録も再開コードも一切発行されない。それを防ぐガード
if "session_id" not in st.session_state:
    st.warning("実験がまだ開始されていません。「app」ページから始めてください。")
    if st.button("appページに戻る", width="stretch"):
        st.switch_page("app.py")
    st.stop()


def _scroll_to_top():
    # 月が変わったらページの先頭に戻す。描画が終わる前に走ると効かないので数回試す。
    # 対話AI（st.chat_input）を追加してから、決まったセレクタだけでは実際にスクロール
    # している要素を取りこぼすことがあると分かったため、(1) 既知のセレクタに加えて
    # 全要素を走査して実際にスクロールしているものを探す、(2) chat_input側にフォーカスが
    # 残っているとブラウザがそちらへスクロールを戻すことがあるのでフォーカスも外す、
    # (3) 試行回数・期間を増やす、の3点で堅牢にした
    st.iframe(
        """<script>
        const sels = ['[data-testid="stMain"]', '[data-testid="stAppViewContainer"]',
                      '[data-testid="stMainViewContainer"]',
                      '[data-testid="stMainBlockContainer"]',
                      '.stMainBlockContainer', 'section.main', '.main'];
        function toTop() {
          const d = window.parent.document;
          if (d.activeElement && typeof d.activeElement.blur === 'function') {
            d.activeElement.blur();
          }
          for (const s of sels) {
            d.querySelectorAll(s).forEach(el => {
              if (el.scrollHeight > el.clientHeight) el.scrollTop = 0;
            });
          }
          // 上のセレクタで取りこぼした場合の保険：実際にスクロールしている要素を全体から探す
          d.querySelectorAll('*').forEach(el => {
            if (el.scrollTop > 0 && el.scrollHeight > el.clientHeight) el.scrollTop = 0;
          });
          if (d.scrollingElement) d.scrollingElement.scrollTop = 0;
          if (d.documentElement) d.documentElement.scrollTop = 0;
          if (d.body) d.body.scrollTop = 0;
          window.parent.scrollTo(0, 0);
        }
        [0, 60, 200, 500, 900, 1500].forEach(t => setTimeout(toTop, t));
        </script>""",
        # st.iframe は 0 を受け付けない版がある（1.64で確認: StreamlitInvalidHeightError）。
        # 月を進めた直後の再実行でこの例外が出ないよう、最小の1pxにしておく（2026-09-30）
        height=1,
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
        # 期限の残り日数は1日単位でしか変わらないので、操作のたびにDBへ聞かず初回だけ取る
        # （Tursoは通信が発生するため、毎回の問い合わせが読み込みの待ちになっていた。2026-09-30）
        if "progress_status" not in st.session_state:
            st.session_state.progress_status = get_progress_status(
                st.session_state.get("session_id"))
        status = st.session_state.progress_status
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

# ── 市況・SNS・参考書・日報（全群共通の情報） ──
# VIXの推移は本番のようにLiveProvider.history()を持たないので、
# timeline（月次の台本データ）から直近ぶんのVIXを取り出して代用する
# （本人要望のVIXミニチャートを、本番だけでなく実験にも一応そろえる）。
_vix_hist = [m["market_context"]["vix"] for m in timeline[:month]
            if m.get("market_context", {}).get("vix") is not None][-20:]
show_market_dashboard(market.get("market_context"),
                      history={"vix": _vix_hist} if _vix_hist else None)
show_sns(market["sns"])
show_reference(phase, timeline=timeline, month=month, situation=market.get("situation"))

overlay = None
if st.session_state.group == 3:
    # 層2（状態の翻訳）用に当月の資産状態を渡す。総資産・含み損益は毎月必ず存在するので、
    # 層3/4（行動履歴・属性）のスロットとは別に、この一文だけは常に追加される。
    # asset_history / timeline は節目（指数の最高値更新・含み損からの復帰）の判定に使う
    overlay, slot_id = build_overlay_block(
        st.session_state.get("overconfidence"), st.session_state.history, month,
        state={"invest_value": state["invest_value"], "pl_pct": state["pl_pct"]},
        asset_history=asset_history, timeline=timeline)
    # 同じ月の再実行（チェックボックス操作など）のたびに書き込まず、月または枠が変わったときだけ書く
    if ("session_id" in st.session_state
            and st.session_state.get("_pers_saved") != (month, slot_id)):
        save_personalization(st.session_state.session_id, month, slot_id)
        st.session_state["_pers_saved"] = (month, slot_id)

show_daily_report(market["daily_report"], st.session_state.group,
                  timeline=timeline, month=month, overlay=overlay)

# ニュース見出しは日報のあと。本番（production_app/10_today.py）と同じ並び順に揃えた
# （本番は「日報が参照した報道をあとで確認する」という設計で日報のあとに置いており、
# 実験側もそれに合わせた。2026-09-23）
show_news(market["news"].get("headlines") or [])

# ── 対話AI（群2・群3）───────────────────────
# 本番（production_app/10_today.py）で鍛えた対話AIを、実験の月次データでそのまま再利用する。
# utils.dialogue.reply() は report/portfolio/recent_days をただの辞書として受け取る
# 作りにしてあるため、dialogue.py 自体は一切変更していない（実験・本番で1本にする、
# という設計原則どおり）。会話ログは experiment_results.db 側に session_id・month
# 区切りで保存する（本番は investment_ai.db に report_date区切りで保存している）。
# 群2は研究計画上「非パーソナライズの汎用AI対話」が必須だが未実装だった抜けを、
# 2026-09-27に発見して追加。群3との差はパーソナライズの有無だけにするため、
# ポートフォリオ・行動履歴・過去の対話ログは群2には渡さない（overlayが無いのは
# 元々の分岐のまま。市況データは全群共通の情報なのでそのまま渡す）。
if st.session_state.group in (2, 3):
    st.markdown("---")
    st.markdown("#### 💬 今月の日報について聞く")
    st.caption("今月の日報・長期投資の知識・あなたの資産状況をもとに答えます。"
              "個別銘柄の売買判断はしません。")

    with st.container(height=420, border=True):  # 対話欄の中だけで固定表示にする（ページ全体を追いかけない）
        _sid = st.session_state.get("session_id")
        _log_key = f"dialogue_{_sid}_{month}"
        if _log_key not in st.session_state:
            st.session_state[_log_key] = load_dialogue_log(_sid, month) if _sid else []

        for _turn in st.session_state[_log_key]:
            with st.chat_message(_turn["role"]):
                st.write(_turn["content"])

        _user_q = st.chat_input("質問を入力（例：今月はなぜ下がったの？）", key=f"chat_input_{month}")
        if _user_q:
            st.session_state[_log_key].append({"role": "user", "content": _user_q})
            if _sid:
                save_dialogue_turn(_sid, month, "user", _user_q)
            with st.chat_message("user"):
                st.write(_user_q)
            with st.chat_message("assistant"):
                with st.spinner("考え中…"):
                    # 画面に実際に表示しているのと同じ内容（overlayを含む）を対話AIにも渡す。
                    # show_daily_report() 内のブロック組み立てと同じロジック
                    _raw_report = market["daily_report"] or {}
                    _report_blocks = _raw_report.get("blocks")
                    if not _report_blocks:
                        _text = (_raw_report.get("group2") or "").strip()
                        _report_blocks = [{"text": t, "chart": None}
                                          for t in _text.split("\n") if t.strip()]
                    if overlay and _report_blocks:
                        _report_blocks = _report_blocks[:-1] + [overlay] + _report_blocks[-1:]
                    _report_for_ai = {"headline": _raw_report.get("headline", ""),
                                      "blocks": _report_blocks}
                    _is_personalized = st.session_state.group == 3
                    # ポートフォリオは本番と違い自己申告ではなく、シミュレーターが計算した
                    # 実際の値をそのまま渡す（§20-1で「実際の資産状況を踏まえるほうが良い」
                    # とした方針どおり、実験では既に正確な値を持っているのでそれを使う）。
                    # 群2はパーソナライズ無し条件のため、資産状況・行動履歴・過去ログは渡さない
                    _pf_for_ai = {
                        "cash": state["cash"],
                        "invested_value": state["invest_value"],
                        "cost_basis": state["cost_basis"],
                    } if _is_personalized else None
                    _history = st.session_state[_log_key][:-1]   # 今回の発話は除く（今月ぶん）
                    _recent_months = ((load_recent_dialogue_months(_sid, month, n_months=3)
                                      if _sid else []) if _is_personalized else [])
                    # 実際に選んだ行動（買い増し・売却・積立変更など）を、会話ログとは別に
                    # 明示的に渡す。st.session_state.history は前月までの決定が積み上がって
                    # いる（今月ぶんはまだ行動選択前）ので、直近3か月ぶんを拾えばよい。
                    # これが無いと、直近の追加投資にAIが気づけず無反応だったり、下落局面での
                    # 買い増しを「上がったから買った」と取り違えたりする（2026-09-21発見）。
                    # 群2では_is_personalizedがFalseなのでNoneのまま渡る
                    _recent_actions = [
                        {"label": f"{h['month']}か月目", "phase": h.get("phase"),
                         "action": h.get("action")}
                        for h in st.session_state.history[-3:]
                    ] if _is_personalized else None
                    try:
                        _answer, _usage = dialogue_reply(_history, _user_q, _report_for_ai,
                                                         _pf_for_ai, _recent_months, unit="month",
                                                         recent_actions=_recent_actions,
                                                         market_context=market.get("market_context"))
                    except Exception as e:
                        _answer = f"すみません、うまく答えられませんでした（{e}）。少し時間をおいて試してください。"
                st.write(_answer)
            st.session_state[_log_key].append({"role": "assistant", "content": _answer})
            if _sid:
                save_dialogue_turn(_sid, month, "assistant", _answer)

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
    # 行動選択・アンケート・「決定して次へ」を1つのフラグメントにまとめる。
    # チェックボックスや金額入力を操作するたびにページ全体（チャート・市況・日報・対話欄）を
    # 描き直していたのが、読み込みの待ちとして気になっていた（2026-09-30、本人の指摘）。
    # フラグメントにすると、この中の操作ではここだけが再実行される。月を進める処理では
    # st.rerun()（既定はアプリ全体）を呼ぶので、次の月の画面はこれまでどおり全体が更新される
    @st.fragment
    def _action_phase():
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

    _action_phase()
