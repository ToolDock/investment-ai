"""米国市場ダッシュボードのチャートを Plotly の Figure として組み立てる。

Streamlit（market_board.py）と静的サイト（build_static.py）の両方から使うので、
このモジュールは streamlit に依存しない。色や高さの既定値もここに集約する。
"""

import math

import plotly.graph_objects as go

from utils import us_market as um

UP = "#2e7d32"
DOWN = "#c62828"
FLAT = "#78909c"
GRID = "rgba(128,128,128,0.22)"

MONTH_TICKS = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]
MONTH_LABELS = [f"{m}月" for m in range(1, 13)]


def dir_color(sign):
    return UP if sign > 0 else (DOWN if sign < 0 else FLAT)


def rgba(hex_color, alpha):
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha})"


def base_layout(height, margin=None):
    """背景は透明にして、文字色は表示側（Streamlitのテーマ／静的サイトのCSS）に委ねる。"""
    return dict(
        height=height,
        margin=margin or dict(l=0, r=0, t=4, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        hovermode="x unified",
    )


# ── 日中足（1・2段目のタイル） ────────────────────────────────
def intraday_chart(tile, color=None):
    """前日終値を基準線にした日中足。基準線との差を塗る。"""
    if color is None:
        color = dir_color(um.format_change(tile)[1])

    fig = go.Figure()
    base = tile["prev_close"]
    times, values = tile["times"], tile["values"]

    if base is not None:
        fig.add_trace(go.Scatter(
            x=times, y=[base] * len(times), mode="lines",
            line=dict(width=1, color=FLAT, dash="dot"),
            hoverinfo="skip",
        ))
    fig.add_trace(go.Scatter(
        x=times, y=values, mode="lines",
        line=dict(width=2, color=color),
        fill="tonexty" if base is not None else None,
        fillcolor=rgba(color, 0.16),
        hovertemplate="%{x|%H:%M}　%{y:,." + str(tile["digits"]) + "f}<extra></extra>",
    ))

    span = [v for v in values if v is not None] + ([base] if base is not None else [])
    low, high = min(span), max(span)
    pad = (high - low) * 0.15 or (abs(high) * 0.001 + 0.01)
    fig.update_layout(**base_layout(112))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False, range=[low - pad, high + pad])
    return fig


# ── 基準価額の年初来チャート（3段目） ──────────────────────────
def nav_chart(rows, height=300):
    days = [r[0] for r in rows]
    navs = [r[1] for r in rows]
    color = UP if navs[-1] >= navs[0] else DOWN

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=days, y=navs, mode="lines",
        line=dict(width=2.4, color=color),
        fill="tozeroy", fillcolor=rgba(color, 0.12),
        hovertemplate="%{x|%Y-%m-%d}　%{y:,.0f}円<extra></extra>",
    ))
    fig.add_hline(y=navs[0], line=dict(width=1, color=FLAT, dash="dot"),
                  annotation_text=f"年初 {navs[0]:,.0f}円",
                  annotation_position="bottom right",
                  annotation_font_size=11)

    # 月初の営業日を目盛りにして「◯月」で見せる
    tickvals, ticktext, seen = [], [], set()
    for day in days:
        if day.month not in seen:
            seen.add(day.month)
            tickvals.append(day)
            ticktext.append(f"{day.month}月")

    low, high = min(navs), max(navs)
    pad = (high - low) * 0.12
    fig.update_layout(**base_layout(height, margin=dict(l=0, r=0, t=10, b=0)))
    fig.update_xaxes(showgrid=False, tickmode="array", tickvals=tickvals, ticktext=ticktext)
    fig.update_yaxes(showgrid=True, gridcolor=GRID, tickformat=",d", ticksuffix="円",
                     range=[low - pad, high + pad])
    return fig


# ── 年初来ドローダウン（4段目） ───────────────────────────────
def drawdown_chart(series, this_year, last_year, height=360):
    fig = go.Figure()
    specs = [
        (last_year, FLAT, "dash", 2.0, False),
        (this_year, DOWN, "solid", 2.6, True),
    ]
    lowest = 0.0
    for year, color, dash, width, filled in specs:
        dd = um.drawdown_series(series, year)
        if not dd:
            continue
        lowest = min(lowest, min(v for _, v in dd))
        fig.add_trace(go.Scatter(
            x=[um.day_of_year(d) for d, _ in dd],
            y=[v for _, v in dd],
            name=f"{year}年",
            mode="lines",
            line=dict(width=width, color=color, dash=dash),
            fill="tozeroy" if filled else None,
            fillcolor=rgba(color, 0.10),
            hovertemplate=f"{year}年 " + "%{y:.2f}%<extra></extra>",
        ))
        worst, worst_day = um.max_drawdown(dd)
        fig.add_annotation(
            x=um.day_of_year(worst_day), y=worst,
            text=f"{year}年 最大 {worst:.1f}%", showarrow=True, arrowhead=0,
            arrowcolor=color, ax=0, ay=26, font=dict(size=11, color=color),
        )

    fig.add_hline(y=0, line=dict(width=1, color=FLAT))
    fig.update_layout(**base_layout(height, margin=dict(l=0, r=0, t=14, b=0)))
    fig.update_layout(
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1),
        hovermode="x unified",
    )
    fig.update_xaxes(tickmode="array", tickvals=MONTH_TICKS, ticktext=MONTH_LABELS,
                     range=[1, 366], showgrid=True, gridcolor=GRID)
    fig.update_yaxes(ticksuffix="%", showgrid=True, gridcolor=GRID,
                     range=[min(lowest * 1.35, -2), 1.5])
    return fig


# ── Fear & Greed（120度メーター） ────────────────────────────
FG_SPAN = 120.0          # メーターの開き角（度）
FG_R_OUT, FG_R_IN = 1.0, 0.78


def _fg_angle(value):
    return math.radians((max(0.0, min(100.0, value)) / 100.0 - 0.5) * FG_SPAN)


def _fg_point(theta, radius):
    return radius * math.sin(theta), radius * math.cos(theta)


def fg_gauge(value, label_en, label_ja, color, height=250):
    """SVGは埋め込み先によってサニタイズされるので、メーターもPlotlyの図形で描く。"""
    fig = go.Figure()

    # 5つの色帯を、外周と内周の円弧で挟んだ多角形として塗る
    for low, high, _en, _ja, band_color in um.FG_BANDS:
        steps = max(2, int((high - low) / 2))
        outer = [_fg_point(_fg_angle(low + (high - low) * i / steps), FG_R_OUT)
                 for i in range(steps + 1)]
        inner = [_fg_point(_fg_angle(low + (high - low) * i / steps), FG_R_IN)
                 for i in range(steps, -1, -1)]
        ring = outer + inner
        fig.add_trace(go.Scatter(
            x=[p[0] for p in ring], y=[p[1] for p in ring],
            mode="lines", line=dict(width=0), fill="toself",
            fillcolor=band_color, hoverinfo="skip",
        ))

    # 針
    theta = _fg_angle(value)
    tip = _fg_point(theta, FG_R_IN - 0.06)
    base_left = _fg_point(theta - math.pi / 2, 0.045)
    base_right = _fg_point(theta + math.pi / 2, 0.045)
    tail = _fg_point(theta + math.pi, 0.10)
    needle = [tip, base_left, tail, base_right, tip]
    fig.add_trace(go.Scatter(
        x=[p[0] for p in needle], y=[p[1] for p in needle],
        mode="lines", line=dict(width=0), fill="toself",
        fillcolor="rgba(120,144,156,0.95)", hoverinfo="skip",
    ))
    fig.add_shape(type="circle", x0=-0.07, x1=0.07, y0=-0.07, y1=0.07,
                  fillcolor="rgba(120,144,156,1)", line=dict(width=0))

    # 目盛りと数値
    for tick in (0, 50, 100):
        tx, ty = _fg_point(_fg_angle(tick), FG_R_OUT + 0.13)
        fig.add_annotation(x=tx, y=ty, text=str(tick), showarrow=False,
                           font=dict(size=12), opacity=0.65)
    fig.add_annotation(x=0, y=-0.30, text=f"<b>{value:.0f}</b>", showarrow=False,
                       font=dict(size=46))
    fig.add_annotation(x=0, y=-0.62, text=f"{label_ja}／{label_en}", showarrow=False,
                       font=dict(size=15, color=color))

    fig.update_layout(**base_layout(height, margin=dict(l=6, r=6, t=6, b=6)))
    fig.update_layout(hovermode=False)
    fig.update_xaxes(visible=False, range=[-1.22, 1.22], fixedrange=True)
    fig.update_yaxes(visible=False, range=[-0.80, 1.18], fixedrange=True,
                     scaleanchor="x", scaleratio=1)
    return fig


# ── VIX（縦メーター） ────────────────────────────────────────
def vix_meter(value, change_text, sign, band_label, band_color,
              scale_max=50.0, height=280):
    """縦向きのメーター。y軸をそのままVIXの目盛りとして使う。"""
    fig = go.Figure()
    bar_left, bar_right = 0.6, 2.4

    for low, high, _label, color in um.VIX_BANDS:
        fig.add_shape(type="rect", x0=bar_left, x1=bar_right,
                      y0=low, y1=min(high, scale_max),
                      fillcolor=color, opacity=0.85, line=dict(width=0), layer="below")
    fig.add_shape(type="rect", x0=bar_left, x1=bar_right, y0=0, y1=scale_max,
                  fillcolor="rgba(0,0,0,0)", line=dict(width=1, color=FLAT))

    clipped = max(0.0, min(scale_max, value))
    fig.add_shape(type="line", x0=bar_left - 0.25, x1=bar_right + 0.45,
                  y0=clipped, y1=clipped, line=dict(width=3, color=FLAT))
    fig.add_trace(go.Scatter(
        x=[bar_right + 0.45], y=[clipped], mode="markers",
        marker=dict(symbol="triangle-right", size=13, color=FLAT), hoverinfo="skip",
    ))

    change_color = UP if sign > 0 else (DOWN if sign < 0 else FLAT)
    fig.add_annotation(x=bar_right + 0.7, y=clipped, text=f"<b>{value:,.2f}</b>",
                       showarrow=False, xanchor="left", yanchor="bottom", font=dict(size=34))
    fig.add_annotation(x=bar_right + 0.75, y=clipped, text=change_text,
                       showarrow=False, xanchor="left", yanchor="top",
                       font=dict(size=14, color=change_color))
    fig.add_annotation(x=bar_right + 0.7, y=1.5, text=f"<b>{band_label}</b>",
                       showarrow=False, xanchor="left", yanchor="bottom",
                       font=dict(size=15, color=band_color))
    fig.add_annotation(x=(bar_left + bar_right) / 2, y=scale_max, text="高いほど警戒",
                       showarrow=False, yanchor="bottom", font=dict(size=12), opacity=0.6)

    fig.update_layout(**base_layout(height, margin=dict(l=0, r=0, t=18, b=6)))
    fig.update_layout(hovermode=False)
    fig.update_xaxes(visible=False, range=[0, 9], fixedrange=True)
    fig.update_yaxes(range=[0, scale_max], fixedrange=True, showgrid=False,
                     tickmode="array", tickvals=list(range(0, int(scale_max) + 1, 10)),
                     zeroline=False, ticklen=4)
    return fig
