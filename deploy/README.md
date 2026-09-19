# GitHub Pages への設置と自動更新

Streamlit（`market_board.py`）は Python のサーバーが要るので GitHub Pages では動きません。
Pages に置くのは `build_static.py` が出力する静的ファイルです。

## 1. Pages リポジトリに置くもの

```
<pages-repo>/
├── .github/workflows/
│   └── update-market.yml        ← deploy/update-market.yml をコピー
├── market/                      ← 公開されない。ビルド用のスクリプト一式
│   ├── build_static.py
│   ├── collect_us_market.py
│   ├── db.py
│   ├── requirements.txt         ← deploy/requirements.txt をコピー
│   ├── utils/
│   │   ├── us_market.py
│   │   └── us_market_figures.py
│   ├── web/
│   │   ├── index.html
│   │   ├── board.css
│   │   ├── board.js
│   │   └── README.md            ← デザイン変更のときはこれを読む
│   └── data/
│       └── fund_nav.csv         ← 基準価額の履歴。ワークフローが更新する
└── docs/us-market/              ← 公開ディレクトリ。ワークフローが上書きする
    ├── index.html
    ├── board.css
    ├── board.js
    └── market.json
```

`market/` に置くのは上記の7ファイル＋`web/`＋`data/` だけです。
`market_board.py` や `utils/components/` は Streamlit 専用なので不要です。
`investment_ai.db` も不要です（CI では毎回 `fund_nav.csv` から復元します）。

公開ディレクトリの場所は既存サイトの構成に合わせてください。参照はすべて相対パス
（`./board.css` / `./market.json`）なので、どの階層に置いても動きます。
変えた場合は `update-market.yml` の `env.OUT_DIR` を合わせてください。

## 2. 初回セットアップ

1. 上記のファイルを配置
2. `market/data/fund_nav.csv` を入れる（このリポジトリの `data/fund_nav.csv`。
   2025-01-01 以降の433営業日ぶんが入っています）
3. `docs/us-market/` に `dist/` の中身を入れる（初回の表示用）
4. リポジトリ設定 → Pages で公開ディレクトリを指定
5. Actions タブから `今日の米国市場を更新` を手動実行して、通ることを確認

`fund_nav.csv` を入れずに動かすと、初回だけ400回以上のAPI呼び出しが走ります。
入れておけば、毎回の取得は直近の数営業日ぶんだけで済みます。

ビルド中に `market/investment_ai.db` と `__pycache__/` が作られます。どちらも
中間ファイルなので、`.gitignore` に足しておいてください。

```gitignore
market/investment_ai.db
market/**/__pycache__/
```

## 3. 自動更新の挙動

- 平日 UTC 22:00（日本時間 翌07:00）に実行。米国市場が引けて、
  基準価額も公表されたあとの時間帯です。
- `--strict` を付けているので、データが1つでも欠けたらビルドを中止して
  終了コード1を返します。コミットは走らないので、公開中のページは壊れません。
- 出力に差分がないときはコミットしません。

### 気をつける点

**Yahoo Finance の API は GitHub の IP からだと 429 で弾かれることがあります。**
公式なAPIではなく、レート制限も公表されていません。収集側で0.8秒間隔＋
指数バックオフを入れていますが、失敗したら `--strict` が止めます。
連続して失敗するようなら、次のどちらかに切り替えてください。

- ローカルで `python build_static.py --refresh` を実行して `dist/` をコミットする
- Yahoo の代わりに、キーのある API（このプロジェクトの `.env` にある FMP や
  Finnhub など）へ `collect_us_market.py` を差し替える

MUFG のファンド情報APIと CNN の Fear & Greed は、CIからでも問題なく取れます。

## 4. 手動で更新する場合

ワークフローを使わず、手元でビルドしてコミットするだけでも動きます。

```bash
python build_static.py --refresh --out /path/to/pages-repo/docs/us-market
```

この場合 `market/` 一式や `fund_nav.csv` を Pages リポジトリに置く必要はありません。
`docs/us-market/` の4ファイルだけで完結します。

## 5. データの出どころと更新頻度

| 項目 | 出典 | 更新 |
|---|---|---|
| S&P500 / NASDAQ100 / FANG+ / ドル円 / ゴールド / 米10年債 / BTC / SOX / VIX | Yahoo Finance chart API | 5分足。取得時点の最終セッション |
| eMAXIS Slim 米国株式（S&P500）基準価額 | 三菱UFJアセットマネジメント ファンド情報API | 営業日の夜に前営業日分が確定 |
| Fear & Greed Index | CNN Business | 1日1回 |

週末・米国休場日は直近営業日の値が出ます。BTCだけは24時間動くので日付がずれることが
あり、各タイルにセッション日を表示しています。

デザインの変更方法と `market.json` の構造は `web/README.md` にまとめてあります。
