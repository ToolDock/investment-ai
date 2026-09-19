# クラウド自動実行の導入手順（investment_ai.db 自動更新）

## これは何か
GitHub Actions を使って、PCを開いていなくても毎朝（平日 JST 07:00ごろ）自動で
データ収集・日報生成が走るようにする仕組み。ToolDockと同じく「開かなくても勝手に動く」
状態を、今の本番アプリ（Streamlit + investment_ai.db）に対して実現するもの。

## 全体の流れ
1. GitHubで **プライベート** リポジトリを作る（自分の手で）
2. リポジトリに、APIキーを「Secrets」として登録する（自分の手で。値は誰にも見えない）
3. このフォルダをそのリポジトリに初めてpushする（自分の手で、内容を確認しながら）
4. 以降は毎朝 GitHub Actions が自動で動き、investment_ai.db を更新してコミットしてくれる
5. 手元のPCで最新データを見たいときは `sync_from_cloud.py` を実行する

## 何がリポジトリに含まれるか／含まれないか
含まれる（追跡される）:
- ソースコード全体（.pyファイル）
- investment_ai.db（bot が書き込む部分のみ。my_portfolio・dialogue_logは初回コミット時に
  空にしてからpushする。以降もbot側のスクリプトはこの2テーブルに一切書き込まない）
- requirements.txt、.github/workflows/ など

含まれない（.gitignore で除外・絶対にpushされない）:
- .env（APIキーの実体。これはSecretsに登録するので、そもそもファイルごと不要）
- experiment_results.db（被験者の実験データ）
- venv/, __pycache__/, logs/ など

## Step 1: プライベートリポジトリを作る
1. https://github.com/new を開く
2. Repository name: 好きな名前（例: investment-ai-private）
3. **Private** を選ぶ（← ここ重要。Publicにしない）
4. 「Create repository」をクリック
5. README等は追加せず、空のリポジトリのままにする

## Step 2: APIキーをSecretsに登録する
作成したリポジトリの Settings → Secrets and variables → Actions →
「New repository secret」から、以下を1つずつ登録する（.env に書いてある値をそのまま
コピーする。値は登録後、自分自身も含めて誰も見返せなくなる）:
- FRED_API_KEY
- FINNHUB_API_KEY
- FMP_API_KEY
- ESTAT_API_KEY
- ANTHROPIC_API_KEY
- OPENROUTER_API_KEY（使っていなければ登録しなくてもよい。その場合ワークフローの
  該当行はそのままで問題ない＝空文字が渡るだけ）

## Step 3: 初めてのpush（自分のPCで、PowerShellから）
このフォルダで、以下を順番に自分の手で実行する:

```powershell
cd C:\Users\okira\investment_ai

# 自分専用データ（ポートフォリオ・会話履歴）を一時的に空にしてからコミットする
venv\Scripts\python.exe prepare_initial_commit.py clear

git init
git add .
git status   # ← ここで何がコミットされるか必ず目で確認する
git commit -m "初回コミット"
git branch -M main
git remote add origin https://github.com/【自分のユーザー名】/【リポジトリ名】.git
git push -u origin main

# 自分専用データを元に戻す
venv\Scripts\python.exe prepare_initial_commit.py restore
```

`git status` の結果に `.env` や `experiment_results.db` が含まれていないことを
必ず確認してから `git commit` に進んでください。含まれていた場合は commit せずに
声をかけてください。

## Step 4: 動作確認
1. GitHubのリポジトリページ → 「Actions」タブを開く
2. 「日次データ収集・日報生成」というワークフローが表示されているはず
3. 右側の「Run workflow」から手動で一度実行してみる（cronの時刻を待たなくてよい）
4. 数分待って緑のチェックが付けば成功。investment_ai.db が自動コミットされているはず

## Step 5: 毎朝の使い方
- 何もしなくても、平日朝7時ごろに自動で最新化される
- 手元のPCで最新データを見たいときは:
  ```powershell
  venv\Scripts\python.exe sync_from_cloud.py
  ```
  を実行してからStreamlitアプリを開く。自分のポートフォリオ・AIとの会話履歴はそのまま残る。

## セキュリティについて
- リポジトリは必ず Private のまま維持する（Publicへの変更は絶対にしない）
- .env ファイル自体はリポジトリに含めない。APIキーはGitHubのSecretsとしてのみ存在する
- 被験者の実験データ（experiment_results.db）は .gitignore で完全に除外されている
- 自分のポートフォリオ・チャット履歴は初回コミット時に空にした上でpushしており、
  以降もbot側のスクリプトはこの2テーブルに一切書き込まない
- プライベートリポジトリであっても、GitHub社のインフラ上にデータが存在する点には留意
  （一般的なクラウドサービス利用と同じ扱い）
