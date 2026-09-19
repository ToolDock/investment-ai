import random

import plotly.graph_objects as go
import streamlit as st

TRADING_DAYS = 21  # 1か月あたりの営業日

RANGES = {"1か月": 1, "1年": 12, "5年": None}  # None は全期間


def _range_tabs(key, default="1か月"):
    left, right = st.columns([1, 1.1])
    with right:
        return st.radio(
            "表示期間", list(RANGES), index=list(RANGES).index(default),
            horizontal=True, key=key, label_visibility="collapsed")


def _slice(x, y, view):
    """表示期間で切り取る。切り取り開始位置も返す（他の系列を揃えるため）。"""
    months = RANGES[view]
    i0 = 0
    if months:
        keep = months * TRADING_DAYS
        if len(x) - 1 > keep:
            i0 = len(x) - (keep + 1)
    x, y = x[i0:], y[i0:]
    if view == "1か月":
        return list(range(len(x))), y, "営業日（今月）", i0
    return [d / TRADING_DAYS for d in x], y, "経過月数", i0


def _interp_series(values, seed):
    """月末値の系列を、月内の営業日に補間する。"""
    rng = random.Random(seed)
    x, y = [0], [values[0]]
    day = 0
    for i in range(1, len(values)):
        start, end = values[i - 1], values[i]
        for d in range(1, TRADING_DAYS + 1):
            v = start + (end - start) * (d / TRADING_DAYS)
            v *= (1 + rng.uniform(-0.015, 0.015))
            if d == TRADING_DAYS:
                v = end
            day += 1
            x.append(day)
            y.append(v)
    return x, y


def draw_market_chart(timeline, month):
    """S&P500の推移。開始時を100とする。"""
    levels, lv = [100.0], 100.0
    for m in timeline:
        if m["month"] > month:
            break
        lv *= (1 + m["return"])
        levels.append(lv)

    x, y = _interp_series(levels, seed=7)
    view = _range_tabs(f"mkt_range_{month}")
    xs, ys, xtitle, _ = _slice(x, y, view)

    now = levels[-1]
    peak = max(levels)
    color = "#1f6feb"

    fig = go.Figure(go.Scatter(
        x=xs, y=ys, mode="lines", line=dict(width=3, color=color),
        hovertemplate="S&P500 %{y:.1f}<extra></extra>"))
    fig.add_scatter(x=[xs[-1]], y=[ys[-1]], mode="markers+text",
                    marker=dict(color=color, size=10, line=dict(color="#ffffff", width=2)),
                    text=[f" {now:.0f}（開始から{now - 100:+.1f}%）"],
                    textposition="middle left" if len(xs) > 40 else "middle right",
                    textfont=dict(size=14), hoverinfo="skip", showlegend=False)
    if view != "1か月" and peak > now * 1.005:
        fig.add_hline(y=peak, line=dict(color="#9aa4ae", width=1, dash="dot"),
                      annotation_text=f"最高値 {peak:.0f}",
                      annotation_position="top left",
                      annotation_font=dict(color="#9aa4ae", size=12))

    fig.update_layout(
        height=430, margin=dict(l=15, r=15, t=25, b=15),
        xaxis_title=xtitle, yaxis_title="S&P500（開始時＝100）",
        hovermode="x", showlegend=False,
    )
    st.plotly_chart(fig, width="stretch", key=f"mkt_chart_{month}_{view}")


def _interpolate(history):
    random.seed(42)
    x, y = [0], [history[0]["total"]]
    day = 0

    for i in range(1, len(history)):
        start = history[i - 1]["total"]
        end = history[i]["total"]
        for d in range(1, TRADING_DAYS + 1):
            t = d / TRADING_DAYS
            value = start + (end - start) * t
            value *= (1 + random.uniform(-0.015, 0.015))
            if d == TRADING_DAYS:
                value = end
            day += 1
            x.append(day)
            y.append(round(value))

    return x, y


def draw_chart(history, month, initial_cash=None, monthly_budget=None):
    # history[0] は0か月目（初期資産）。0か月目から現在の月までを表示する
    history = history[:month + 1]
    x, y = _interpolate(history)

    view = _range_tabs(f"chart_range_{month}", default="1年")
    x_full = list(x)
    xs, y, xtitle, i0 = _slice(x, y, view)

    fig = go.Figure()

    # 累計元本（初期資産＋積立の累計）を重ねる。
    # 毎月の入金で総資産は相場と無関係に増えるので、線が1本だと損益が見えない
    if initial_cash is not None and monthly_budget is not None:
        base = [initial_cash + monthly_budget * (d / TRADING_DAYS)
                for d in x_full[i0:]]
        fig.add_scatter(x=xs, y=base, mode="lines", name="投入した金額",
                        line=dict(color="#9aa4ae", width=2, dash="dot"),
                        hovertemplate="投入した金額 %{y:,.0f}円<extra></extra>")

    fig.add_scatter(x=xs, y=y, mode="lines", name="総資産",
                    line=dict(width=3, color="#1f6feb"),
                    hovertemplate="総資産 %{y:,.0f}円<extra></extra>")

    if initial_cash is not None and monthly_budget is not None:
        gain = y[-1] - base[-1]
        g_color = "#2e7d32" if gain > 0 else ("#c62828" if gain < 0 else "#78909c")
        fig.add_annotation(
            x=xs[-1], y=y[-1], xanchor="right", yanchor="bottom",
            text=f"投入額との差 {gain:+,.0f}円", showarrow=False,
            font=dict(color=g_color, size=13))

    # 今月の始まりに区切りを入れて、どこが今月分かを示す
    if view != "1か月" and len(x) > TRADING_DAYS:
        fig.add_vline(x=xs[-(TRADING_DAYS + 1)], line=dict(color="#9aa4ae", width=1, dash="dot"),
                      annotation_text="今月", annotation_position="top left",
                      annotation_font=dict(size=12))

    fig.update_layout(
        height=300,
        margin=dict(l=15, r=15, t=25, b=15),
        xaxis_title=xtitle,
        yaxis_title="資産額（円）",
        hovermode="x",
        showlegend=True,
        legend=dict(orientation="h", y=1.12, x=0, font=dict(size=12)),
    )
    st.plotly_chart(fig, width="stretch", key=f"asset_chart_{month}_{view}")
