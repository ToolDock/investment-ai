"""実行の出力を logs/ にも残す。

画面に出るものと同じ内容がファイルに残るので、
あとから読み返したり、そのまま人に渡したりできる。
"""

import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(ROOT, "logs")


class _Tee:
    def __init__(self, stream, fh):
        self.stream = stream
        self.fh = fh

    def write(self, s):
        self.stream.write(s)
        self.fh.write(s)
        self.fh.flush()

    def flush(self):
        self.stream.flush()
        self.fh.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)


def tee(name, keep=40):
    """標準出力と標準エラーを logs/ にも流す。

    実行中は logs/<name>_latest.txt に書き、終了時に日時付きで控えを残す。
    読む側は常に <name>_latest.txt を見ればよい。
    """
    import atexit
    import shutil

    os.makedirs(LOG_DIR, exist_ok=True)
    latest = os.path.join(LOG_DIR, f"{name}_latest.txt")
    fh = open(latest, "w", encoding="utf-8")
    sys.stdout = _Tee(sys.__stdout__, fh)
    sys.stderr = _Tee(sys.__stderr__, fh)
    _prune(name, keep)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    keep_path = os.path.join(LOG_DIR, f"{name}_{stamp}.txt")

    def _archive():
        try:
            fh.flush()
            shutil.copyfile(latest, keep_path)
        except OSError:
            pass

    atexit.register(_archive)
    return latest


def _prune(name, keep):
    # 古いログを溜めない
    files = sorted(f for f in os.listdir(LOG_DIR)
                   if f.startswith(name + "_") and f.endswith(".txt")
                   and not f.endswith("_latest.txt"))
    for f in files[:-keep] if len(files) > keep else []:
        try:
            os.remove(os.path.join(LOG_DIR, f))
        except OSError:
            pass
