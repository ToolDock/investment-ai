"""本番の日報を、実験アプリ(app.py)とは別のStreamlit Community Cloudデプロイとして
公開するための、専用エントリーポイント。

中身は一切ここに書かない。同じフォルダの 10_today.py をそのまま実行するだけの
薄いブートストラップにしてある(runpy.run_path)。理由:
- ロジックの二重管理を避ける(10_today.py を直接編集すれば、ローカルでの単独確認
  〈streamlit run production_app/app.py〉・この本番デプロイの両方に反映される)
- Streamlitの複数ページ機能は「実行中のスクリプトと同じディレクトリにある pages/
  フォルダ」を自動的にサイドバーへ出す。このファイルが置かれた production_app/
  には pages/ が無いので、実験側の 01/02/03 は一切辿り着けない構造になっている
  (サイドバーを隠すのではなく、そもそも同じアプリの中に存在しない)
- 10_today.py はもともと実験側の共有 pages/ フォルダに同居していたため、実験
  (app.py)を単独デプロイすると本番ページまでサイドバーに出てしまっていた
  (2026-09-26、本人指摘で発覚)。この production_app/ 配下に移設し、実験側の
  pages/ には 01〜03 しか残らないようにして解消した。

このエントリーポイントを Streamlit Community Cloud の「Main file path」に指定して
デプロイすると、実験(app.py)とは別のURLが発行される。手順は TURSO_SETUP_PROD.md
参照(2026-09-23)。
"""

import os
import runpy
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

runpy.run_path(os.path.join(_HERE, "10_today.py"), run_name="__main__")
