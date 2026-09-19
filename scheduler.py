import logging
from apscheduler.schedulers.blocking import BlockingScheduler
from collect_fred import init_fred_table, fetch_series, save_series, SERIES
from collect_finnhub import init_quotes_table, fetch_quote, save_quote
from collect_fmp import init_sector_table, fetch_sector_performance, save_sector_performance, get_latest_trading_day
from collect_fng import init_fng_table, fetch_stock_fng, fetch_crypto_fng, save_fng
from collect_news import init_news_table, fetch_news, save_news
from collect_estat import init_estat_table, fetch_estat, save_estat, SERIES as ESTAT_SERIES
from datetime import date

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

def collect_all():
    log.info("=== データ収集開始 ===")
    today = date.today().isoformat()

    # FRED
    try:
        for series_id, series_name in SERIES.items():
            obs = fetch_series(series_id)
            save_series(obs, series_name)
        log.info("FRED: 完了")
    except Exception as e:
        log.error(f"FRED: 失敗 {e}")

    # Finnhub
    try:
        from collect_finnhub import symbols
        for name, symbol in symbols.items():
            value = fetch_quote(symbol)
            if value:
                save_quote(today, name, value)
        log.info("Finnhub: 完了")
    except Exception as e:
        log.error(f"Finnhub: 失敗 {e}")

    # 米国市場（Yahoo のクオート・日中足・円建て基準価額）
    # FMP より先に回す。get_latest_trading_day() は market_quote の
    # ^GSPC セッションを見て「最後に引けた日」を決めるため、ここが
    # 先に最新化されていないと、FMP が前回のセッション日でセクターを
    # 取りに行ってしまい、対象日とずれて日報側で使われなくなる
    try:
        import collect_us_market as um
        um.init_tables()
        um.refresh_all()
        log.info("米国市場: 完了")
    except Exception as e:
        log.error(f"米国市場: 失敗 {e}")

    # FMP
    try:
        target_date = get_latest_trading_day()
        data = fetch_sector_performance(target_date)
        if data:
            save_sector_performance(data)
        log.info("FMP: 完了")
    except Exception as e:
        log.error(f"FMP: 失敗 {e}")

    # F&G
    try:
        stock_value, stock_label = fetch_stock_fng()
        save_fng(today, "stock", stock_value, stock_label)
        crypto_value, crypto_label = fetch_crypto_fng()
        save_fng(today, "crypto", crypto_value, crypto_label)
        log.info("F&G: 完了")
    except Exception as e:
        log.error(f"F&G: 失敗 {e}")

    # ニュース
    try:
        articles = fetch_news()
        save_news(articles)
        log.info("ニュース: 完了")
    except Exception as e:
        log.error(f"ニュース: 失敗 {e}")

    # e-Stat
    try:
        for series_name, stats_id in ESTAT_SERIES.items():
            data = fetch_estat(stats_id)
            save_estat(data, series_name)
        log.info("e-Stat: 完了")
    except Exception as e:
        log.error(f"e-Stat: 失敗 {e}")

    log.info("=== データ収集完了 ===")


def make_report():
    """収集のあとに日報を1本作る。データが古ければ生成側が自分で止まる。"""
    log.info("=== 日報生成 ===")
    try:
        from generate_daily_report import run_live
        run_live(["live"])
    except Exception as e:
        log.error(f"日報生成: 失敗 {e}")


def morning():
    collect_all()
    make_report()


if __name__ == "__main__":
    from utils.runlog import tee
    tee("scheduler")

    # 起動時に即時実行
    morning()

    # 毎朝7時（米国市場の引け後）に収集して日報を作る
    scheduler = BlockingScheduler(timezone="Asia/Tokyo")
    scheduler.add_job(morning, "cron", hour=7, minute=0)
    log.info("スケジューラー起動 (毎朝7:00実行)")
    scheduler.start()