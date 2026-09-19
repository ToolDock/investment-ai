# 今日の米国市場 ── GitHub Pages 用の静的ダッシュボード

`build_static.py` が出力する `dist/` を、そのまま GitHub Pages に置けば動きます。
サーバー処理はなく、ブラウザが `market.json` を読んで描画するだけです。

```
dist/
  index.html    骨組み（このフォルダの index.html のコピー）
  board.css     見た目（同 board.css のコピー）
  board.js      market.json を読んで描画（同 board.js のコピー）
  market.json   数値・系列・Plotlyの図（ビルド時に生成）
```

`index.html` / `board.css` / `board.js` の編集は、この `web/` の方を直してください。
`dist/` はビルドのたびに上書きされます。

## ビルド

```bash
python build_static.py --refresh
```

`--refresh` を付けると先に最新データを取得します。付けなければ DB のキャッシュから
書き出すだけです。出力先を変えるときは `--out docs` のように指定します。

## 設置

`dist/` の中身を Pages リポジトリの公開ディレクトリ（`/` か `/docs`）に置くだけです。
サブディレクトリに置いても、参照はすべて相対パス（`./board.css` など）なので動きます。

外部リソースは `cdn.plot.ly` の Plotly.js（3.6.0）だけです。CDN を使いたくない場合は
`plotly-3.6.0.min.js` をリポジトリに置いて、`index.html` の `<script src>` を
そちらに向けてください（約4.5MB）。

## デザインを変えるとき

### 色・余白・角丸

`board.css` の `:root` にまとめてあります。ダークテーマは
`@media (prefers-color-scheme: dark)` のブロックです。

チャートの中の文字色だけは Plotly が持つので、CSS変数 `--chart-font-color` を
`board.js` の `applyChartTheme()` が読んで Plotly に渡しています。
`:root` の値を変えれば図の文字色も一緒に変わります。

### レイアウト

`index.html` はほぼ空の骨組みで、中身は `board.js` が `market.json` から流し込みます。
タイル1枚の構造は `<template id="tpl-tile">` にあるので、そこを書き換えれば
8枚すべてに反映されます。クラス名を変えた場合は `board.js` の
`setText(node, ".tile__label", ...)` のセレクタも合わせてください。

### 段組み

- 1・2段目のタイル … `.row__tiles`（`grid-template-columns: repeat(4, 1fr)`）
- 3段目の基準価額 … `.fund`（数値 : チャート ＝ `1fr : 2.4fr`）
- 5段目のセンチメント … `.sentiment`（左右2分割）

`@media (max-width: 1000px)` で2列、`560px` で1列に落としています。

### チャートそのもの

`market.json` の `figures` に Plotly の図（`{data, layout}`）がそのまま入っています。
`Plotly.newPlot(el, fig.data, fig.layout)` に渡すだけの形です。
図の中身を変えたい場合は、生成元の `utils/us_market_figures.py`（Python）を直すのが確実です。
Streamlit版（`market_board.py`）と同じ関数を使っているので、両方に反映されます。

## market.json の構造

```jsonc
{
  "title": "今日の米国市場",
  "generated_at": "2026-08-30T22:00:00+09:00",   // ISO8601
  "generated_at_text": "2026-08-30 22:00",

  "rows": [                                       // 1段目・2段目
    {
      "title": "主要指数・為替",
      "tiles": [
        {
          "symbol": "^GSPC",      // Yahoo Finance のシンボル
          "slug": "gspc",         // HTMLのid用
          "label": "S&P500",
          "session": "2026-08-28", // どのセッションの値か（取引所ローカル日付）
          "price": 7711.76,
          "price_text": "7,711.76",
          "prev_close": 7730.99,
          "change": -19.23,
          "change_pct": -0.25,
          "change_bp": -1923.0,    // 金利用（1bp = 0.01%）
          "change_mode": "pct",    // "pct" か "bp"
          "change_text": "-19.23（-0.25%）",
          "direction": -1,         // 1=上げ / -1=下げ / 0=変わらず
          "arrow": "▼"
        }
      ]
    }
  ],

  "fund_chart_title": "eMAXIS Slim 米国株式（S&P500）（円建て・基準価額）",
  "fund": {                                       // 3段目。データがなければ null
    "name": "eMAXIS Slim 米国株式（S&P500）",
    "fund_cd": "253266",
    "year": 2026,
    "date": "2026-08-28", "date_text": "2026年8月28日",
    "nav": 45344, "nav_text": "45,344",
    "change": 386, "change_pct": 0.86,
    "change_text": "+386円（+0.86%）", "direction": 1, "arrow": "▲",
    "start_date": "2026-01-05", "start_date_text": "1月5日", "start_nav": 39457,
    "ytd_pct": 14.92,                             // 年初来騰落率(%)
    "peak": 45727, "from_peak_pct": -0.84         // 年初来高値と、そこからの位置(%)
  },

  "drawdown": {                                   // 4段目
    "title": "年初来ドローダウンの推移（2026年 と 2025年）",
    "note": "…",
    "years": {
      "2026": {
        "dates":  ["2026-01-05", "…"],
        "values": [0.0, -0.31, "…"],              // 年初来高値からの下落率(%)、0以下
        "max": -8.35, "max_date": "2026-03-31"    // その年の最大ドローダウン
      },
      "2025": { "…": "同上" }
    }
  },

  "fear_greed": {                                 // 5段目左。なければ null
    "value": 54.4, "value_text": "54",
    "label_en": "Neutral", "label_ja": "中立", "color": "#fbc02d",
    "date": "2026-08-30",
    "history": [{ "label": "前営業日", "value": 54.4 }, "…"],
    "note": "…"
  },

  "vix": {                                        // 5段目右。なければ null
    "value": 14.43, "value_text": "14.43",
    "change_text": "-0.08（-0.55%）", "direction": -1,
    "session": "2026-08-28",
    "band_label": "落ち着き", "band_color": "#2e7d32",
    "note": "…"
  },

  "figures": {                                    // Plotly の {data, layout}
    "tiles": { "^GSPC": { "data": [], "layout": {} }, "…": {} },
    "nav": {}, "drawdown": {}, "fear_greed": {}, "vix": {}
  },

  "sources": ["…"],
  "disclaimer": "…"
}
```

数値は生の値と整形済みテキストの両方を入れてあるので、書式を変えたい場合は
`price` / `change_pct` などから作り直せます。

## データについて

| 項目 | 出典 | 更新のタイミング |
|---|---|---|
| 指数・為替・金利・コモディティ・BTC | Yahoo Finance chart API | 5分足。米国市場の最終セッション |
| eMAXIS Slim 米国株式（S&P500）基準価額 | 三菱UFJアセットマネジメント ファンド情報API | 営業日の夜に前営業日分が確定 |
| Fear & Greed | CNN Business | 1日1回 |

米国休場日・週末は、直近の営業日のデータが出ます。BTCだけは24時間動くので
別の日付になることがあり、各タイルにセッション日を明記しています。

`generated_at` はビルドを実行した時刻で、市場の最終更新時刻ではありません。

## 注意

- Yahoo Finance の API は公式のドキュメントがなく、連続アクセスすると 429 を返します。
  収集側で0.8秒間隔＋指数バックオフを入れていますが、頻繁なビルドは避けてください。
- 本ページは市況の把握を目的とした情報提供で、投資助言ではありません。
  フッターの `disclaimer` は消さないでください。
