"""Orchestrates all scanners into one dataset for app_server to serve."""
import datetime as dt
from concurrent.futures import ThreadPoolExecutor

import config
from scanners import stocks, crypto, forex, news

TOP_HOT_WITH_NEWS = 8
TOP_SLEEPER_WITH_NEWS = 6


def _top_symbols(picks: dict) -> list:
    hot, sleeper = picks.get("hot"), picks.get("sleeper")
    under50, penny = picks.get("under50"), picks.get("penny")
    out = []
    if hot is not None and not hot.empty:
        out += list(hot["symbol"].head(TOP_HOT_WITH_NEWS))
    if sleeper is not None and not sleeper.empty:
        out += list(sleeper["symbol"].head(TOP_SLEEPER_WITH_NEWS))
    # The two newer, shorter lists get headlines on every card.
    if under50 is not None and not under50.empty:
        out += list(under50["symbol"])
    if penny is not None and not penny.empty:
        out += list(penny["symbol"])
    return out


def _fetch_missing_stock_news(symbols: list, news_cache: dict) -> None:
    """Fetches headlines for any symbol not already cached (in parallel)."""
    missing = [s for s in dict.fromkeys(symbols) if s not in news_cache]
    if not missing:
        return
    with ThreadPoolExecutor(max_workers=6) as pool:
        for sym, items in zip(missing, pool.map(lambda s: news.search_ticker_news(f"{s} stock"), missing)):
            news_cache[sym] = items


def repick_stocks(metrics, tech_split: float, news_cache: dict) -> dict:
    """Re-selects the Hot/Sleeper stock lists at a new tech/non-tech mix from
    the already-scored universe - no rescan. Only names that weren't shown
    before need a headline lookup."""
    picks = stocks.select_picks(metrics, tech_split)
    _fetch_missing_stock_news(_top_symbols(picks), news_cache)
    return {key: _attach_news(picks[key], "symbol", news_cache) for key in ("hot", "sleeper", "under50")}


def run_full_scan(progress_cb=None, tech_split: float = None) -> dict:
    def log(msg):
        if progress_cb:
            progress_cb(msg)

    log("Starting scan...")

    log("Scanning stocks (this is the slow part - ~2-4 min for ~900 tickers)...")
    stock_results = stocks.scan(progress_cb=log, tech_split=tech_split)
    stock_metrics = stock_results.pop("metrics")

    log("Scanning for hot penny stocks (under $5)...")
    stock_results["penny"] = stocks.penny_scan(progress_cb=log)

    log("Scanning crypto markets...")
    crypto_results = crypto.scan(progress_cb=log)

    log("Scanning currency pairs...")
    fx_df = forex.scan(progress_cb=log)

    log("Reading news feeds (WSJ, Reuters, Barron's, MarketWatch, CNBC, CoinDesk, etc.)...")
    wire_df = news.fetch_all_feeds(progress_cb=log)
    digest_df = news.diverse_digest(wire_df, config.TOP_NEWS_DIGEST_COUNT)

    log("Fetching per-ticker headlines for top movers...")
    stock_news = {}
    _fetch_missing_stock_news(_top_symbols(stock_results), stock_news)

    id_to_query = {}
    for df in (crypto_results["hot"], crypto_results["sleeper"]):
        for _, r in df.iterrows():
            id_to_query[r["id"]] = f'"{r["name"]}" {r["symbol_disp"]} cryptocurrency'
    top_crypto_ids = list(crypto_results["hot"]["id"].head(8)) + list(crypto_results["sleeper"]["id"].head(6))
    crypto_news = {cid: news.search_ticker_news(id_to_query.get(cid, f"{cid} crypto")) for cid in top_crypto_ids}

    generated_at = dt.datetime.now()
    as_of = generated_at.strftime("%b %d, %Y %I:%M %p")
    # Stamp the scored universe too, so re-picks after a mix change carry the scan time.
    if stock_metrics is not None and not stock_metrics.empty:
        stock_metrics["as_of"] = as_of

    stock_results["hot"] = _attach_news(stock_results["hot"], "symbol", stock_news)
    stock_results["sleeper"] = _attach_news(stock_results["sleeper"], "symbol", stock_news)
    stock_results["under50"] = _attach_news(stock_results["under50"], "symbol", stock_news)
    stock_results["penny"] = _attach_news(stock_results["penny"], "symbol", stock_news)
    crypto_results["hot"] = _attach_news(crypto_results["hot"], "id", crypto_news)
    crypto_results["sleeper"] = _attach_news(crypto_results["sleeper"], "id", crypto_news)

    for df in (stock_results["hot"], stock_results["sleeper"], stock_results["under50"],
               stock_results["penny"], crypto_results["hot"], crypto_results["sleeper"], fx_df):
        if df is not None and not df.empty:
            df["as_of"] = as_of

    log("Done.")
    return {
        "data": {"stocks": stock_results, "crypto": crypto_results, "forex": fx_df,
                 "under50_info": (stocks.band_info(stock_metrics)
                                  if stock_metrics is not None and not stock_metrics.empty else None)},
        "digest_df": digest_df,
        "wire_df": wire_df,
        "generated_at": generated_at,
        "stock_metrics": stock_metrics,
        "stock_news_cache": stock_news,
    }


def _attach_news(df, key_col, news_map):
    if df is None or df.empty:
        return df
    df = df.copy()
    df["news"] = df[key_col].map(lambda k: news_map.get(k, []))
    return df
