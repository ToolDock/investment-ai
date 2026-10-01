"""本番の日報。実データから生成して保存したものを読んで表示するだけの画面。

生成はここではしない（scheduler.py が毎営業日の朝に回す）。
表示の作りは実験の日報とそろえてあり、違うのは中身のデータだけ。
"""

import json
from datetime import date

import streamlit as st

from utils.components.daily_report import show_daily_report
from utils.components.news import show_news
from utils.components.market_dashboard import show_market_dashboard, show_price_grid
from utils.components.reading_board import show_reading_board
from utils.providers import LiveProvider, closed_message, week_ja
from utils.dialogue import reply as dialogue_reply
from utils import portfolio as portfolio_store
from utils.visuals import fig_ytd_drawdown_yoy, ytd_drawdown_summary
from utils.components.ui_scale import render_scale_control, inject_scale_css

st.set_page_config(page_title="今日の日報", layout="wide")

# 画面の大きさ（対話AIの入力欄がある分、既定はやや小さめ。サイドバーで調整できる）
render_scale_control()
inject_scale_css()


@st.cache_data(ttl=600)
def _status():
    p = LiveProvider()
    return p.session_status()


@st.cache_data(ttl=600)
def _load(day=None):
    p = LiveProvider()
    p.init_store()
    conn = p._conn()
    try:
        if day:
            row = conn.execute("SELECT * FROM daily_report WHERE date = ?", (day,)).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM daily_report ORDER BY date DESC LIMIT 1").fetchone()
        days = [r["date"] for r in conn.execute(
            "SELECT date FROM daily_report ORDER BY date DESC LIMIT 60")]
    finally:
        conn.close()
    if row is None:
        return None, days, []
    ctx = json.loads(row["context"] or "{}")
    tl = p.timeline(row["date"]) if ctx else []
    hist = p.history(row["date"]) if ctx else {}
    ytd_years = p.ytd_drawdown_years(row["date"]) if ctx else {}
    return {
        "date": row["date"], "phase": row["phase"], "ret": row["ret"],
        "headline": row["headline"], "blocks": json.loads(row["blocks"] or "[]"),
        "ctx": ctx, "history": hist, "ytd_years": ytd_years,
        "links": json.loads(row["links"] or "[]") if "links" in row.keys() else [],
    }, days, tl


st.title("今日の日報")

# URLに ?demo=1 を付けたときだけの、紹介用の表示モード。
# マイポートフォリオ・対話履歴（どちらも個人の資産状況が写り込む）を隠す。
# 通常のURL（自分用のブックマーク）はこれまでどおり実データを表示する
# （2026-09-26、本人からの要望：見せて紹介するとき資産状況が見えてしまうのは困る）。
DEMO_MODE = st.query_params.get("demo") == "1"
if DEMO_MODE:
    st.caption("🔎 デモ表示中：マイポートフォリオ・対話履歴は個人情報のため表示していません。")

status = _status()
if status["state"] == "closed":
    st.info(f"{closed_message(status)}この日の日報はありません。"
            f"下に出ているのは直近の営業日ぶんです。")
elif status["state"] == "stale":
    st.warning(f"{closed_message(status)}データ収集が止まっている可能性があります。")
elif status.get("weekend"):
    st.info(closed_message(status))

rep, days, timeline = _load()
if rep is None:
    st.info("まだ日報がありません。データを集めたうえで "
            "`python generate_daily_report.py live` を実行してください。")
    st.stop()

st.caption(f"対象日：{rep['date']}（{week_ja(rep['date'])}）の米国市場")
if len(days) > 1:
    picked = st.selectbox("過去の日報", days, index=0)
    if picked != rep["date"]:
        rep, days, timeline = _load(picked)

ctx = rep["ctx"]
mc = ctx.get("market_context", {})
prov = LiveProvider()

c1, c2 = st.columns(2)
c1.metric("S&P500（前営業日比）", f"{rep['ret']*100:+.2f}%")
c2.metric("局面", rep["phase"])

dd = (mc.get("drawdown") or {}).get("current")
if dd is not None:
    st.caption(f"最高値からの下落幅 {dd:.1f}%"
               + (f"（{ctx['window']['start']} 以降で測定）" if ctx.get("window") else ""))

month = timeline[-1]["month"] if timeline else None

# 主要指数・コモディティの値動きを、本文より前・一番最初に置く。
# 局面によってAI日報側の図が選べない・選ばれないことがあっても、ここだけは常に出る。
# 1日・1週間・1か月・年初来・1年・5年をカードごとに切り替えられる（ToolDock風）。
# ドル円・金利はここではなく、下の「為替と金利」の数値表示のままにしてある
st.markdown("**主要指数・コモディティ**")
show_price_grid(prov, rep["date"])

# VIX・Fear & Greed・主要指数・セクター別を、実験側（群3等）と同じダッシュボードで見せる。
# これまでは簡易な数値表示だけだったが、既存のコンポーネントをそのまま流用できるので揃えた
show_market_dashboard(mc, prov, rep["date"], history=rep.get("history"))

ytd_fig = fig_ytd_drawdown_yoy(rep.get("ytd_years") or {})
if ytd_fig is not None:
    years = sorted(rep["ytd_years"])
    st.markdown(f"**年初来ドローダウンの推移（{years[-1]}年 と {years[0]}年）**")
    st.plotly_chart(ytd_fig, width="stretch", config={"displayModeBar": False})
    summary = ytd_drawdown_summary(rep["ytd_years"])
    if summary:
        st.caption("　".join(f"{s['year']}年 最大 {s['dd']:.1f}%（{s['date']}）" for s in summary))
    st.caption("その年の年初からの最高値を更新するたびに基準を引き上げ、そこからの下落率を"
              "日ごとに描いたもの。0%の線に張り付いているときは高値圏、下に伸びているときは"
              "高値から下げている局面。")

st.markdown("---")
show_daily_report(
    {"blocks": rep["blocks"], "headline": rep["headline"]},
    group=2, timeline=timeline, month=month,
    unit="day", history=rep.get("history") or {},
)

heads = (ctx.get("news") or {}).get("headlines") or []
show_news(heads)

st.markdown("---")
show_reading_board(ctx, rep.get("history") or {},
                   links=rep.get("links") or None)

fx, rates = ctx.get("fx"), ctx.get("rates")
if fx or rates:
    st.markdown("#### 為替と金利")
    cols = st.columns(2)
    if fx:
        ytd = "" if fx.get("ytd_yen") is None else f"／年初来 {fx['ytd_yen']:+.2f}円"
        cols[0].metric("ドル円", f"{fx['level']:.2f}円",
                       f"{fx['day_yen']:+.2f}円{ytd}")
    if rates:
        cols[1].metric("米10年債利回り", f"{rates['level']:.2f}%",
                       f"{rates['day_bp']:+.1f}bp")

gap = (date.today() - date.fromisoformat(rep["date"])).days
if gap > 3 and status["state"] == "open":
    st.warning(f"この日報は {gap} 日前のものです。データ収集が止まっている可能性があります。")

# ── マイポートフォリオ（対話AIのパーソナライズに使う。任意入力） ──
portfolio_store.init_store()

st.markdown("---")
if DEMO_MODE:
    st.caption("💰 マイポートフォリオ（デモ表示のため非表示）")
else:
    with st.expander("💰 マイポートフォリオ（対話AIが参照します。空欄のままでもOK）"):
        pf = portfolio_store.get_portfolio() or {}
        with st.form("portfolio_form"):
            cash_in = st.number_input("現金（円）", min_value=0, step=1000,
                                      value=pf.get("cash") or 0)
            invested_in = st.number_input("投資評価額（円）", min_value=0, step=1000,
                                          value=pf.get("invested_value") or 0)
            cost_in = st.number_input("取得原価・積立累計額（円）", min_value=0, step=1000,
                                      value=pf.get("cost_basis") or 0)
            units_in = st.number_input("保有口数（口）", min_value=0, step=1000,
                                       value=pf.get("units") or 0,
                                       help="証券口座に表示される保有口数。基準価額は1万口あたりの値段です")
            if st.form_submit_button("更新"):
                portfolio_store.save_portfolio(cash_in, invested_in, cost_in)
                portfolio_store.save_units(int(units_in))
                st.success("更新しました")
                st.rerun()
        _fund_now = ctx.get("fund") or {}
        _nav = _fund_now.get("nav")
        if pf.get("units"):
            _line = f"保有口数 {pf['units']:,} 口"
            if pf.get("cost_basis"):
                _line += f"　／　平均取得単価 {pf['cost_basis'] / pf['units'] * 10000:,.0f} 円（1万口あたり）"
            if _nav:
                _line += (f"　／　基準価額 {_nav:,.0f} 円（{_fund_now.get('date', '')}）"
                          f"　／　口数×基準価額 {pf['units'] * _nav / 10000:,.0f} 円")
            st.caption(_line)
        if pf.get("updated_at"):
            st.caption(f"最終更新：{pf['updated_at']}")
        else:
            st.caption("未登録。登録すると、対話AIが自分の含み損益を踏まえて答えられるようになります。")

# ── 対話AI（本日の日報について聞く） ──────────
st.markdown("---")
st.markdown("#### 💬 今日の日報について聞く")
st.caption("今日の日報・長期投資の知識（登録していればあなたの資産状況も）をもとに答えます。"
          "個別銘柄の売買判断はしません。")

# 2026-09-24: 入力欄を、対話欄の中に固定する方式（page全体を追いかけない）から、
# Streamlit標準の「ページ下部に追従する」チャット入力欄に戻した（本人要望）。
# ただし標準のままだと入力欄の上下の余白がやや大きいので、CSSで高さを抑える。
st.markdown(
    """<style>
    [data-testid="stBottomBlockContainer"] { padding-top: 0.5rem; padding-bottom: 0.5rem; }
    [data-testid="stChatInput"] textarea { min-height: 2.2rem; }
    </style>""",
    unsafe_allow_html=True,
)

# ログ表示用の入れ物だけ先に確保しておき、後で（chat_inputの処理後にも）
# 同じ入れ物にメッセージを足せるようにする（chat_inputはページ直下でしか
# 下部固定にならないため、containerの外に出す必要があった）。
_log_box = st.container(height=360, border=True)
_log_key = f"dialogue_{rep['date']}"
if _log_key not in st.session_state:
    # デモ表示では過去の実際の会話（個人の資産状況が写り込みうる）を出さず、空の状態から始める
    st.session_state[_log_key] = [] if DEMO_MODE else portfolio_store.load_today_log(rep["date"])

with _log_box:
    for _turn in st.session_state[_log_key]:
        with st.chat_message(_turn["role"]):
            st.write(_turn["content"])

_user_q = st.chat_input("質問を入力（例：今日はなぜ下がったの？）")
if _user_q:
    st.session_state[_log_key].append({"role": "user", "content": _user_q})
    if not DEMO_MODE:
        portfolio_store.log_turn(rep["date"], "user", _user_q)
    with _log_box:
        with st.chat_message("user"):
            st.write(_user_q)
        with st.chat_message("assistant"):
            with st.spinner("考え中…"):
                _report_for_ai = {"headline": rep["headline"], "blocks": rep["blocks"]}
                # デモ表示では個人のポートフォリオ・直近の会話を対話AIに渡さない
                _pf_now = None if DEMO_MODE else portfolio_store.get_portfolio()
                if _pf_now and _pf_now.get("units") and (ctx.get("fund") or {}).get("nav"):
                    _pf_now["nav"] = ctx["fund"]["nav"]
                _history = st.session_state[_log_key][:-1]   # 今回の発話は除く（今日ぶん）
                _recent_days = None if DEMO_MODE else portfolio_store.load_recent_days(
                    rep["date"], n_days=5)
                try:
                    _answer, _usage = dialogue_reply(_history, _user_q, _report_for_ai, _pf_now,
                                                     _recent_days, market_context=mc)
                except Exception as e:
                    _answer = f"すみません、うまく答えられませんでした（{e}）。少し時間をおいて試してください。"
            st.write(_answer)
    st.session_state[_log_key].append({"role": "assistant", "content": _answer})
    if not DEMO_MODE:
        portfolio_store.log_turn(rep["date"], "assistant", _answer)
