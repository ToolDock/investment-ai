# 本番アプリのスマホ対応：セットアップ手順（2026-09-23）

自分のPCを開かなくても、スマホ・タブレットのブラウザから本番の「今日の日報」
（`pages/10_today.py`）を毎日チェックできるようにするための手順。実験
（`TURSO_SETUP.md`）と考え方は同じだが、**別のTursoデータベース・別のStreamlit
Community Cloudアプリ**として独立させてある。理由は2つ。

1. 実験用の参加者データと、自分の実際の資産状況・対話ログを同じ場所に置きたくない
2. `pages/10_today.py` は実験の `app.py` と同じStreamlitアプリの中の1ページであり、
   ページを隠す仕組みが無いため、実験をそのまま公開すると本番ページにも誰でも
   たどり着けてしまう。**別デプロイに分離する**ことで、実験のURLを知っている人が
   本番の資産状況を見られる、という事態を防ぐ

以下の3つを組み合わせる。

1. **Turso**（無料の外部永続DB。実験用とは別のデータベースを新規作成）に、本番の
   `my_portfolio`（資産状況）・`dialogue_log`（対話AIとの会話）を保存する
   → アプリが再起動してもデータが消えない
2. **Streamlit Community Cloud**に、`production_app/app.py` を専用のエントリー
   ポイントとして新規デプロイする（実験の `app.py` とは別のアプリ・別のURL）
   → 自分のPCが起動していなくても、24時間アクセスできるURLができる。実験の
   01〜03のページには一切たどり着けない
3. 発行されたURLを、スマホ・タブレットのブラウザでホーム画面に追加する
   → アイコンをタップするだけでアプリのように開ける

コード側の変更（`utils/portfolio.py` の `_conn()`、`production_app/app.py`
新規作成、`requirements.txt`）はこちらで済ませてある。`pages/10_today.py` 自体は
一切変更していない（`production_app/app.py` がそのまま実行するだけの薄い
ブートストラップになっているので、このページの内容を直すときはこれまでどおり
`pages/10_today.py` を編集すればよい。二重管理にはならない）。

市況データ（`investment_ai.db` の `daily_report` 等、GitHub Actionsが毎朝
収集・生成するテーブル）は今回の変更対象外。あちらは引き続きGitHub Actions→
git commitの経路のままで、Streamlit Community Cloudは毎朝の新しいコミットを
検知して自動的にアプリを再起動し、最新の日報を反映する（この再起動で
`my_portfolio`・`dialogue_log`が消えないようにするのが、今回Tursoに移した理由）。

## 1. Tursoのアカウント作成とDB作成（実験用とは別に、もう1つ作る）

実験のときにすでにTursoアカウントを作っていれば、アカウント作成は不要。
「もう1つ、本番専用のデータベースを作る」だけでよい。

1. https://turso.tech/ のダッシュボードにログインする
2. 新しいデータベースを作成する（名前は `investment-ai-prod` 等、実験用と
   区別できる名前にする。任意）
3. 作成したDBの詳細画面で以下の2つを控える
   - **Database URL**（`libsql://xxxx.turso.io` のような形）
   - **認証トークン**（Create Token のようなボタンから発行。一度しか表示
     されないことが多いので、控えたら安全な場所に保存する。パスワードと
     同じ扱いにする）

実験用のURL・トークンとは別物になるので、混同しないよう分かる名前でメモして
おくとよい（環境変数名も `TURSO_CONNECTION_URL` ではなく
`TURSO_PROD_CONNECTION_URL` にしてあるので、取り違えて設定してもコード側は
正しく動く設計にはなっているが、念のため）。

## 2. ローカルでの接続確認（自分のPCで、デプロイ前に）

いきなりStreamlitを起動すると、接続まわりのエラーとStreamlit自体の問題の
どちらが原因か切り分けにくい。実験のとき（`test_turso_connection.py`）と同じ
考え方で、まず軽い単体テストスクリプト `test_turso_connection_prod.py` で疎通
確認してから、本体（Streamlit）を起動する2段構えにする。

### 2-1. 単体テストスクリプトでの疎通確認

PowerShellで環境変数を設定し、`test_turso_connection_prod.py` を実行する。

```powershell
$env:TURSO_PROD_CONNECTION_URL = "控えたDatabase URL"
$env:TURSO_PROD_AUTH_TOKEN = "控えた認証トークン"
venv\Scripts\python.exe test_turso_connection_prod.py
```

このスクリプトは `utils/portfolio.py` が実際に使っている形（CHECK制約つき
テーブル・`ON CONFLICT ... DO UPDATE`によるupsert）でTursoに書き込み・
読み出しを行う。最後に

    === すべて成功しました。本番用Turso(TURSO_PROD_*)への接続・CHECK制約・upsert・読み出しが
        正常に動いています。utils/portfolio.py の実際の書き方でも問題ないはずです。 ===

と出れば、`utils/portfolio.py` が実運用でつまずく可能性は低い。途中で
エラーが出たら、その内容をそのまま伝えてほしい（`auth_token`の引数名の
食い違いなど、実験のときに一度踏んだ種類のエラーであれば同じ直し方で
対応できる。§20-25-1参照）。

### 2-2. Streamlitでの動作確認

単体テストが通ったら、同じ環境変数を設定したまま普段どおりStreamlitを起動し、
マイポートフォリオの登録・対話AIとの1〜2往復を試してみる。

```powershell
$env:TURSO_PROD_CONNECTION_URL = "控えたDatabase URL"
$env:TURSO_PROD_AUTH_TOKEN = "控えた認証トークン"
venv\Scripts\python.exe -m streamlit run production_app/app.py
```

この2つの環境変数を設定しない限り、これまでどおりローカルの `investment_ai.db`
が使われる（挙動は変えていない）。環境変数を設定した状態でポートフォリオを
登録・対話AIと数往復し、エラーが出ないか、Turso側のダッシュボードに
`my_portfolio`・`dialogue_log`の行が実際に増えているかを確認してほしい。

**ここは私の環境からは確認できていない。** `production_app/app.py`
自体はこちらでStreamlit標準のテスト機能（`AppTest`）を使って例外なく動く
ことを確認済みだが、実際にTursoへ書き込めるかはアカウント作成後にしか検証
できない（実験のときと同じ制約。§20-25-1で実験側は`auth_token`の引数名
エラーが一度出ているので、同じエラーが出た場合はそちらの対応と同じ修正で
直る）。

## 3. Streamlit Community Cloudへのデプロイ（実験とは別アプリとして）

1. https://share.streamlit.io/ にアクセスし、実験のときと同じGitHubアカウントで
   サインインする
2. 「New app」から、**同じリポジトリ・同じブランチ**を選び、「Main file path」に
   `production_app/app.py` を指定してデプロイする（実験の `app.py` を指定した
   デプロイとは別に、もう1つアプリを作る形になる。2つ目のデプロイなので
   「New app」をもう一度押すところから始める）
3. デプロイ設定の中の「Secrets」に、Turso関連とLLM関連の環境変数をTOML形式で
   入力する

```toml
TURSO_PROD_CONNECTION_URL = "控えたDatabase URL"
TURSO_PROD_AUTH_TOKEN = "控えた認証トークン"
ANTHROPIC_API_KEY = "既存の.envと同じ値"
LLM_BACKEND = "既存の.envと同じ値（設定していれば）"
```

（対話AIで使っている他の環境変数が `.env` にあれば、それも同じ形で追加する。
`FRED_API_KEY`等の市況データ収集用のキーは、このアプリでは収集を行わない
ため不要）

4. デプロイが終わると、実験のものとは別に `https://yyyy.streamlit.app`
   のようなURLが発行される

## 4. 公開範囲

実験と同じく、まずは**「Public」のままURLをどこにも貼らず、自分だけが知っている
状態にする**運用でよい。ただし今回は自分の実際の資産状況・対話内容が乗る
ため、実験よりも一段階慎重にしたければ、アプリの設定画面（右下の「⋮」→
「Settings」）から「Private」に切り替え、Googleアカウントでの招待制にする
こともできる（自分ひとりしか使わないので、招待の手間は増えない）。どちらに
するかは本人の判断。

## 5. スマホ・タブレットのホーム画面に追加する

発行されたURLを、スマホ・タブレットのブラウザで開いてから、ホーム画面に
追加するとアプリのように使える。

**iPhone / iPad（Safari）**
1. URLをSafariで開く
2. 下部（iPadは上部）の共有ボタン（□に↑の矢印）をタップ
3. 「ホーム画面に追加」を選ぶ
4. 名前を確認して「追加」

**Android（Chrome）**
1. URLをChromeで開く
2. 右上の「⋮」をタップ
3. 「ホーム画面に追加」または「アプリをインストール」を選ぶ
4. 名前を確認して「追加」

どちらも、ホーム画面のアイコンをタップすると全画面でアプリのように開く
（URLバー等が表示されない、いわゆるPWA的な見た目になる）。

## 6. 動作確認チェックリスト

- [ ] `test_turso_connection_prod.py`を実行し、「すべて成功しました」の
      メッセージまで到達した（2-1）
- [ ] ローカルでTurso（本番用）環境変数を設定して`production_app/app.py`を
      起動し、ポートフォリオ登録・対話AIとのやり取りでTurso側に行が増える
      ことを確認した
- [ ] Streamlit Community Cloudに`production_app/app.py`をデプロイし、
      実験とは別のURLでアプリが開けることを確認した
- [ ] そのURLのサイドバーに、実験の01〜03のページが**出てこない**ことを
      確認した（別デプロイとして分離できていることの確認）
- [ ] デプロイ後のアプリでポートフォリオ登録・対話AIと数往復し、Turso側に
      そのやり取りが記録されることを確認した
- [ ] PCをスリープ・シャットダウンした状態でも、そのURLから引き続き
      アクセスできることを確認した
- [ ] 翌朝、GitHub Actionsが`investment_ai.db`を更新したあと（アプリが自動
      再起動するはず）も、前日までのポートフォリオ登録・対話ログが消えて
      いないことを確認した（ここがローカルSQLiteのままだと消えていた
      問題点。Tursoに移した効果を確かめる本丸）
- [ ] スマホ・タブレットのホーム画面にアイコンを追加し、タップして開けることを
      確認した

## 7. 注意点

- `pages/10_today.py` 自体のロジックは変更していない。画面の中身を直したい
  ときは、これまでどおりこのファイルを編集すればよい
  （`production_app/app.py`はそれを読んで実行するだけの薄いラッパー）
- 市況データ（`daily_report`等）はTursoに移していない。GitHub Actions→
  git commitの経路のまま、Streamlit Community Cloud側の自動再起動で
  最新化される
- Turso無料枠は月500M行読み取り・1000万行書き込み・5GBストレージで、
  自分ひとりが毎日使う分には十分すぎる余裕がある
