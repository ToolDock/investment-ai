import json
import math
import os
import random
import sqlite3
from datetime import datetime

# 実験結果は市場データ収集用DB(investment_ai.db)とは分けて保存する
DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "experiment_results.db"
)

# 中断からの再開は、開始（progress.created_at）からこの日数を過ぎたら無効にする
RESUME_EXPIRY_DAYS = 7
# 再開コードの文字種。0/O, 1/I など見間違えやすい文字は除く
_RESUME_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"

# クラウドワークス報酬（2026-09-16、本人と合意）：参加料 + 利益に応じたボーナス。
# 利益＝最終資産 − 投入した元本の総額（現金・投資の内訳によらず一定。現金は増えないので
# 多く残すほど利益は目減りする＝この不利は意図した設計として受け入れる）。
# 利益がプラスのときだけ、利益÷30,000円を四捨五入した額（円）をボーナスにする。マイナス・0なら参加料のみ。
# （2026-09-30、倫理審査の事前相談資料の「小数点以下四捨五入」に合わせた。以前は切り上げだった）
REWARD_BASE_FEE = 10
REWARD_BONUS_DIVISOR = 30000


def compute_reward(final_asset, total_contributed):
    """クラウドワークス報酬額（円）を返す。profit（利益）もあわせて返す。"""
    profit = final_asset - total_contributed
    # 四捨五入は「0.5は切り上げ」で行う（組み込みのround()は偶数丸めで、0.5の扱いが意図と変わる）
    bonus = math.floor(profit / REWARD_BONUS_DIVISOR + 0.5) if profit > 0 else 0
    return REWARD_BASE_FEE + bonus, profit


def get_connection():
    """参加者データの接続先を返す。

    TURSO_CONNECTION_URL が設定されていれば、外部の永続DB（Turso／libSQL）に
    つなぐ。Streamlit Community Cloud等、ローカルファイルシステムが再起動のたびに
    リセットされる環境に本番の実験アプリを置くための切り替え。ローカルでの開発・
    自分のPCでの動作確認（これまでどおりの使い方）では、この環境変数を設定しなければ
    従来どおりローカルの experiment_results.db を使う（挙動は一切変えていない）。

    Turso（libSQL）はSQLite自体のフォークで、SQL文はそのまま互換（AUTOINCREMENT・
    lastrowid・INSERT OR REPLACE・executemany、いずれもそのまま使える設計）。
    ただし実際にTursoへつないでの動作確認は、アカウント作成がこちらではできない
    ため未実施（TURSO_SETUP.md参照。本人の環境での確認が必要）。
    """
    turso_url = os.environ.get("TURSO_CONNECTION_URL")
    if turso_url:
        import turso_serverless
        return turso_serverless.connect(
            turso_url, auth_token=os.environ.get("TURSO_AUTH_TOKEN"))
    # 複数参加者の同時アクセスに備えてロック待ちを許可する（ローカルSQLiteのみの設定）
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


# init_results_db() をこのプロセスで実行済みか。Streamlit は操作のたびにページを再実行し、
# 各ページの先頭で init_results_db() が呼ばれる。Turso では CREATE TABLE が1文ごとに
# 通信になるので、毎回走らせると選択肢を1つ押すたびに数往復ぶん待たされていた
# （2026-09-30、事前アンケートで「選択肢を押すたびに読み込みが出る」と指摘）。
# テーブルは一度作れば残るので、プロセスごとに1回でよい
_results_db_ready = False


def init_results_db():
    global _results_db_ready
    if _results_db_ready:
        return
    conn = get_connection()
    cur = conn.cursor()

    # 参加者番号(participant_no)は内部で自動採番する
    cur.execute("""
        CREATE TABLE IF NOT EXISTS participants (
            participant_no    INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id        TEXT UNIQUE,
            group_no          INTEGER,
            age               INTEGER,
            gender            TEXT,
            invest_experience TEXT,
            invest_years      TEXT,
            fin_self_rank     TEXT,
            fin_score         INTEGER,
            fin_conf_mean     REAL,
            overconfidence    REAL,
            initial_invest    INTEGER,
            monthly_invest    INTEGER,
            created_at        TEXT,
            completed_at      TEXT,
            final_asset       INTEGER,
            profit            INTEGER,
            reward_yen        INTEGER
        )
    """)

    # 既存DB（この2列が無い状態で作られたもの）へのマイグレーション。
    # CREATE TABLE IF NOT EXISTS は既存テーブルに新しい列を足してくれないため必要
    existing_cols = {row[1] for row in cur.execute("PRAGMA table_info(participants)")}
    if "profit" not in existing_cols:
        cur.execute("ALTER TABLE participants ADD COLUMN profit INTEGER")
    if "reward_yen" not in existing_cols:
        cur.execute("ALTER TABLE participants ADD COLUMN reward_yen INTEGER")

    # 金融リテラシーの生回答（設問ごと）
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fin_literacy (
            participant_no INTEGER,
            qid            TEXT,
            answer         TEXT,
            is_correct     INTEGER,
            confidence     INTEGER,
            PRIMARY KEY (participant_no, qid)
        )
    """)

    # 全月1行記録（観察のみの月も残す）。is_event=相場変動月, engaged=行動フェーズに入ったか
    cur.execute("""
        CREATE TABLE IF NOT EXISTS responses (
            session_id       TEXT,
            month            INTEGER,
            phase            TEXT,
            return_rate      REAL,
            is_event         INTEGER,
            engaged          INTEGER,
            action_label     TEXT,
            total            INTEGER,
            cash             INTEGER,
            investment_value INTEGER,
            pl_pct           REAL,
            sell_amount      INTEGER,
            buy_amount       INTEGER,
            monthly_invest   INTEGER,
            anxiety          INTEGER,
            sell_impulse     INTEGER,
            continue_invest  INTEGER,
            created_at       TEXT,
            PRIMARY KEY (session_id, month)
        )
    """)

    # 群3で、どの参加者に・いつ・どの個人化枠が発火したか（操作チェック用）
    cur.execute("""
        CREATE TABLE IF NOT EXISTS personalization_log (
            session_id TEXT,
            month      INTEGER,
            slot_id    TEXT,
            created_at TEXT,
            PRIMARY KEY (session_id, month)
        )
    """)

    # 事後アンケート。設問idごとに1行（設問を足しても構造が変わらない）
    cur.execute("""
        CREATE TABLE IF NOT EXISTS post_survey (
            session_id TEXT,
            qid        TEXT,
            answer     INTEGER,
            text       TEXT,
            created_at TEXT,
            PRIMARY KEY (session_id, qid)
        )
    """)

    # 中断・再開用の進捗スナップショット。st.session_state の再構築に必要な情報を
    # まとめて state_json に持つ（型ごとに列を増やさず、復元側で dict として展開する）。
    # created_at は最初の保存時刻のまま更新しない＝再開の期限判定の基準にする。
    cur.execute("""
        CREATE TABLE IF NOT EXISTS progress (
            session_id  TEXT PRIMARY KEY,
            resume_code TEXT UNIQUE,
            state_json  TEXT,
            created_at  TEXT,
            updated_at  TEXT
        )
    """)

    # 同意の記録と、実験の完了（事後アンケート送信）の記録。participants にALTERをかけずに
    # 済むよう別表にしてある（公開中のTursoの既存表を触らない）。2026-10-01
    cur.execute("""
        CREATE TABLE IF NOT EXISTS participant_status (
            session_id      TEXT PRIMARY KEY,
            consented_at    TEXT,
            consent_version TEXT,
            survey_done_at  TEXT
        )
    """)

    # 群3「提案AI対話」の会話ログ。本番（investment_ai.db の dialogue_log、report_date区切り）
    # と同じ役割を、実験では session_id・month区切りで持つ（1参加者が60か月を通しでプレイする
    # ため、区切りは日付ではなく月）。本番用の utils.dialogue.reply() をそのまま再利用できるよう、
    # 読み出し側で本番と同じ dict の形（{"role":..., "content":...}）に整える。
    cur.execute("""
        CREATE TABLE IF NOT EXISTS dialogue_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            month      INTEGER,
            role       TEXT,
            content    TEXT,
            created_at TEXT
        )
    """)

    # 対話AIの1回ごとの利用量（トークン数と概算費用）。費用の実測用（2026-10-01）。
    # dialogue_log を変更せず別表にしたのは、公開中のTursoの既存表にALTERをかけずに済ませるため
    cur.execute("""
        CREATE TABLE IF NOT EXISTS llm_usage (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT,
            month       INTEGER,
            input       INTEGER,
            output      INTEGER,
            cache_write INTEGER,
            cache_read  INTEGER,
            cost_usd    REAL,
            created_at  TEXT
        )
    """)

    conn.commit()
    conn.close()
    _results_db_ready = True


def save_post_survey(session_id, answers, texts):
    """answers: {qid: 1-5}, texts: {qid: 自由記述}"""
    now = datetime.now().isoformat()
    rows = [(session_id, q, v, None, now) for q, v in answers.items()]
    rows += [(session_id, q, None, t, now) for q, t in texts.items() if (t or "").strip()]
    conn = get_connection()
    conn.executemany(
        """INSERT OR REPLACE INTO post_survey
           (session_id, qid, answer, text, created_at) VALUES (?, ?, ?, ?, ?)""", rows)
    conn.commit()
    conn.close()


def create_participant(session_id, group_no, age, gender,
                       invest_experience, invest_years,
                       fin_self_rank, fin_score, fin_conf_mean, overconfidence,
                       initial_invest, monthly_invest):
    """参加者を登録し、自動採番された participant_no を返す。"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO participants
            (session_id, group_no, age, gender, invest_experience, invest_years,
             fin_self_rank, fin_score, fin_conf_mean, overconfidence,
             initial_invest, monthly_invest, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (session_id, group_no, age, gender, invest_experience, invest_years,
         fin_self_rank, fin_score, fin_conf_mean, overconfidence,
         initial_invest, monthly_invest, datetime.now().isoformat())
    )
    participant_no = cur.lastrowid
    conn.commit()
    conn.close()
    return participant_no


def save_fin_literacy(participant_no, detail):
    # detail: [{"qid","answer","is_correct","confidence"}, ...]
    conn = get_connection()
    conn.executemany(
        """
        INSERT OR REPLACE INTO fin_literacy
            (participant_no, qid, answer, is_correct, confidence)
        VALUES (?, ?, ?, ?, ?)
        """,
        [(participant_no, d["qid"], d["answer"], d["is_correct"], d["confidence"])
         for d in detail]
    )
    conn.commit()
    conn.close()


def save_response(session_id, month, phase, return_rate, is_event, engaged,
                  action, state, answers):
    # action: action_selector の戻り値（観察のみの月は空）/ state: その月の資産状態 / answers: アンケート回答
    conn = get_connection()
    conn.execute(
        """
        INSERT OR REPLACE INTO responses
            (session_id, month, phase, return_rate, is_event, engaged, action_label,
             total, cash, investment_value, pl_pct,
             sell_amount, buy_amount, monthly_invest,
             anxiety, sell_impulse, continue_invest, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id, month, phase, return_rate,
            1 if is_event else 0, 1 if engaged else 0,
            action.get("label") if engaged else "観察のみ",
            state["total"], state["cash"], state["invest_value"], state["pl_pct"],
            action.get("sell_amount", 0),
            action.get("buy_amount", 0),
            action.get("monthly_invest"),
            answers.get("anxiety"),
            answers.get("sell_impulse"),
            answers.get("continue_invest"),
            datetime.now().isoformat(),
        )
    )
    conn.commit()
    conn.close()


def save_personalization(session_id, month, slot_id):
    """群3で今月どの個人化枠を出したかを記録する。操作チェックの根拠になる。"""
    conn = get_connection()
    conn.execute(
        """
        INSERT OR REPLACE INTO personalization_log
            (session_id, month, slot_id, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (session_id, month, slot_id, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def _generate_resume_code(cur, length=6, max_tries=20):
    """他の再開コードと衝突しないコードを作る。紛らわしい文字は最初から除いてある。"""
    for _ in range(max_tries):
        code = "".join(random.choices(_RESUME_ALPHABET, k=length))
        cur.execute("SELECT 1 FROM progress WHERE resume_code = ?", (code,))
        if not cur.fetchone():
            return code
    raise RuntimeError("再開コードの生成に失敗しました（衝突が続きました）")


def save_progress(session_id, state):
    """中断・再開用のスナップショットを保存する。

    state は st.session_state から再開に必要な項目だけを抜き出した dict
    （nickname / age / overconfidence / initial_invest / monthly_invest /
    group / participant_no / decisions / history / month_idx）。
    2回目以降の呼び出しでは中身だけ更新し、resume_code と created_at
    （＝再開期限の起点）は最初の保存時のまま変えない。

    戻り値: resume_code（新規なら発行したもの、既存なら変わらず同じもの）
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT resume_code FROM progress WHERE session_id = ?", (session_id,))
    row = cur.fetchone()
    now = datetime.now().isoformat()
    state_json = json.dumps(state, ensure_ascii=False)
    if row:
        resume_code = row[0]
        cur.execute(
            "UPDATE progress SET state_json = ?, updated_at = ? WHERE session_id = ?",
            (state_json, now, session_id)
        )
    else:
        resume_code = _generate_resume_code(cur)
        cur.execute(
            """INSERT INTO progress (session_id, resume_code, state_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (session_id, resume_code, state_json, now, now)
        )
    conn.commit()
    conn.close()
    return resume_code


def load_progress_by_code(resume_code):
    """再開コードから進捗を探す。

    戻り値: 見つからなければ None。見つかれば (state, session_id, is_expired) の
    タプル。is_expired は開始（created_at）から RESUME_EXPIRY_DAYS 日を過ぎているか。
    期限切れかどうかの判断は呼び出し側に委ね、ここでは削除も無効化もしない
    （何日過ぎていたかを画面に出せるように、判定材料だけ返す）。
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT session_id, state_json, created_at FROM progress WHERE resume_code = ?",
        ((resume_code or "").strip().upper(),)
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    session_id, state_json, created_at = row
    age_days = (datetime.now() - datetime.fromisoformat(created_at)).days
    is_expired = age_days > RESUME_EXPIRY_DAYS
    return json.loads(state_json), session_id, is_expired


def get_progress_status(session_id):
    """今のセッションの再開コードと、期限までの残り日数を返す（appページの表示用）。

    戻り値: 見つからなければ None。見つかれば (resume_code, remaining_days) のタプル。
    remaining_days は 0 未満にはならない（期限当日は 0 日として表示する）。
    """
    if not session_id:
        return None
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT resume_code, created_at FROM progress WHERE session_id = ?",
        (session_id,)
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    resume_code, created_at = row
    age_days = (datetime.now() - datetime.fromisoformat(created_at)).days
    remaining_days = max(RESUME_EXPIRY_DAYS - age_days, 0)
    return resume_code, remaining_days


def finalize_participant(session_id, final_asset, total_contributed):
    """完了時に最終資産と報酬を確定して保存する。

    total_contributed は「参加者に渡した元本の総額」（初期資産＋毎月の余剰資金×月数）。
    現金のまま残した分も含めて一定なので、呼び出し側の初期設定・積立変更の選択によらず
    settings["initial_cash"] + MONTHLY_BUDGET * len(timeline) で計算したものを渡す。
    """
    reward_yen, profit = compute_reward(final_asset, total_contributed)
    conn = get_connection()
    conn.execute(
        """
        UPDATE participants
        SET completed_at = ?, final_asset = ?, profit = ?, reward_yen = ?
        WHERE session_id = ?
        """,
        (datetime.now().isoformat(), final_asset, profit, reward_yen, session_id)
    )
    conn.commit()
    conn.close()


def save_dialogue_turn(session_id, month, role, content):
    """群3の対話AIの1発話を記録する（本番の utils.portfolio.log_turn に相当）。"""
    conn = get_connection()
    conn.execute(
        "INSERT INTO dialogue_log (session_id, month, role, content, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (session_id, month, role, content, datetime.now().isoformat(timespec="seconds"))
    )
    conn.commit()
    conn.close()


def save_llm_usage(session_id, month, usage):
    """対話AI1回ぶんの利用量を記録する。記録に失敗しても対話は止めない。"""
    try:
        u = usage or {}
        conn = get_connection()
        conn.execute(
            "INSERT INTO llm_usage (session_id, month, input, output, cache_write, "
            "cache_read, cost_usd, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, month, u.get("input", 0), u.get("output", 0),
             u.get("cache_write", 0), u.get("cache_read", 0), u.get("cost_usd", 0.0),
             datetime.now().isoformat(timespec="seconds"))
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def load_dialogue_log(session_id, month):
    """今月ぶんの対話ログを発話順で返す（本番の utils.portfolio.load_today_log に相当）。"""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT role, content FROM dialogue_log "
            "WHERE session_id = ? AND month = ? ORDER BY id",
            (session_id, month)
        ).fetchall()
    finally:
        conn.close()
    return [{"role": r[0], "content": r[1]} for r in rows]


def load_recent_dialogue_months(session_id, before_month, n_months=3):
    """今月より前で、実際にやり取りのあった直近 n_months か月ぶんの対話ログを、
    月の古い順・各月はやり取りの順で返す（本番の utils.portfolio.load_recent_days に相当。
    本番は暦日区切り・こちらは月区切りという違いだけで、会話の連続性という役割は同じ）。

    utils.dialogue.reply() の recent_days 引数がそのまま使える形（[{"date":..., "turns":[...]}, ...]）
    で返す。"date" キーには日付の代わりに「37か月目」のような月ラベルを入れる
    （dialogue.py 側はラベルとして表示するだけで、日付かどうかを判定してはいないため、
    dialogue.py 自体は変更不要）。
    """
    conn = get_connection()
    try:
        months = [r[0] for r in conn.execute(
            "SELECT DISTINCT month FROM dialogue_log WHERE session_id = ? AND month < ? "
            "ORDER BY month DESC LIMIT ?", (session_id, before_month, n_months)).fetchall()]
        months.reverse()  # 古い順に並べ直す
        out = []
        for m in months:
            rows = conn.execute(
                "SELECT role, content FROM dialogue_log "
                "WHERE session_id = ? AND month = ? ORDER BY id",
                (session_id, m)).fetchall()
            out.append({"date": f"{m}か月目",
                       "turns": [{"role": r[0], "content": r[1]} for r in rows]})
    finally:
        conn.close()
    return out


# 同意の説明文（app.py）を変えたら、この版の名前も変える。どの文面に同意したかを後から辿れるようにする
CONSENT_VERSION = "2026-10-pilot-v1"


def record_consent(session_id, consented_at=None):
    """同意した日時を記録する。記録に失敗しても実験は止めない。"""
    try:
        conn = get_connection()
        conn.execute(
            """INSERT INTO participant_status (session_id, consented_at, consent_version)
               VALUES (?, ?, ?)
               ON CONFLICT(session_id) DO UPDATE SET
                   consented_at = excluded.consented_at,
                   consent_version = excluded.consent_version""",
            (session_id, consented_at or datetime.now().isoformat(), CONSENT_VERSION))
        conn.commit()
        conn.close()
    except Exception:
        pass


def mark_survey_done(session_id):
    """事後アンケートの送信（＝実験の完了）を記録する。最初の1回の日時だけ残す。"""
    conn = get_connection()
    conn.execute(
        """INSERT INTO participant_status (session_id, survey_done_at) VALUES (?, ?)
           ON CONFLICT(session_id) DO UPDATE SET
               survey_done_at = COALESCE(participant_status.survey_done_at, excluded.survey_done_at)""",
        (session_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_completion_info(session_id):
    """完了状況と結果をまとめて返す（完了画面と、完了済みの番号での再開の判定に使う）。

    sim_done: シミュレーションを最後まで終えたか（participants.completed_at）
    survey_done: 事後アンケートまで送信したか
    見つからなければ None。
    """
    if not session_id:
        return None
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT completed_at, final_asset, profit, reward_yen FROM participants WHERE session_id = ?",
        (session_id,))
    p = cur.fetchone()
    cur.execute("SELECT survey_done_at FROM participant_status WHERE session_id = ?", (session_id,))
    st_row = cur.fetchone()
    cur.execute("SELECT resume_code FROM progress WHERE session_id = ?", (session_id,))
    pr = cur.fetchone()
    conn.close()
    if not p:
        return None
    return {
        "sim_done": p[0] is not None,
        "survey_done": bool(st_row and st_row[0]),
        "final_asset": p[1], "profit": p[2], "reward_yen": p[3],
        "resume_code": pr[0] if pr else None,
    }
