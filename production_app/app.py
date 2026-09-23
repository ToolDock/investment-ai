"""本番の日報を、実験アプリ(app.py)とは別のStreamlit Community Cloudデプロイとして
公開するための、専用エントリーポイント。

中身は一切ここに書かない。pages/10_today.py をそのまま実行するだけの薄いブート
ストラップにしてある(runpy.run_path)。理由:
- ロジックの二重管理を避ける(pages/10_today.py を直接編集すれば、ローカル開発時の
  多ページアプリ(streamlit run app.py)・この本番専用デプロイの両方に反映される)
- Streamlitの複数ページ機能は「実行中のスクリプトと同じディレクトリにある pages/
  フォルダ」を自動的にサイドバーへ出す。このファイルは pages/ を持たない
  production_app/ 配下に置くことで、実験側の 01/02/03 は一切辿り着けない構造に
  なっている(サイドバーを隠すのではなく、そもそも同じアプリの中に存在しない)

このエントリーポイントを Streamlit Community Cloud の「Main file path」に指定して
デプロイすると、実験(app.py)とは別のURLが発行される。手順は TURSO_SETUP_PROD.md
参照(2026-09-23)。
"""

import os
import runpy
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

runpy.run_path(os.path.join(_ROOT, "pages", "10_today.py"), run_name="__main__")
