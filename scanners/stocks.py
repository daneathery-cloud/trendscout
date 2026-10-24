"""Stock scanner: pulls price/volume history for the ticker universe and
cross-references Yahoo Finance's and StockTwits' free trending-symbol feeds."""
import datetime as dt
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import yfinance as yf

import config
import scoring

_ET = ZoneInfo("America/New_York")
_MARKET_OPEN = dt.time(9, 30)
_MARKET_CLOSE = dt.time(16, 0)


def _session_elapsed_fraction() -> float | None:
    """If US markets are open right now, returns how far through today's
    regular session we are (0..1). Returns None outside market hours, so
    callers know today's volume bar (if any) represents a full session."""
    now_et = dt.datetime.now(_ET)
    if now_et.weekday() >= 5:
        return None
    now_t = now_et.time()
    if now_t < _MARKET_OPEN or now_t > _MARKET_CLOSE:
        return None
    open_dt = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    close_dt = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    frac = (now_et - open_dt).total_seconds() / (close_dt - open_dt).total_seconds()
    return max(frac, 0.05)  # avoid huge multipliers in the first few minutes


def fetch_trending_symbols() -> set:
    """Symbols currently flagged as trending by Yahoo Finance and StockTwits
    (both free, keyless endpoints). Used as a buzz cross-check, not the
    primary signal."""
    symbols = set()
    try:
        r = requests.get(
            "https://query1.finance.yahoo.com/v1/finance/trending/US",
            headers=config.REQUEST_HEADERS, timeout=config.REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        quotes = r.json()["finance"]["result"][0]["quotes"]
        symbols.update(q["symbol"] for q in quotes)
    except Exception:
        pass
    try:
        r = requests.get(
            "https://api.stocktwits.com/api/2/trending/symbols.json",
            headers=config.REQUEST_HEADERS, timeout=config.REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        for s in r.json().get("symbols", []):
            symbols.add(s["symbol"])
    except Exception:
        pass
    return symbols


def load_universe() -> pd.DataFrame:
    return pd.read_csv(config.UNIVERSE_CSV)


def fetch_price_history(tickers: list, progress_cb=None) -> dict:
    """Batch-downloads history and returns {symbol: DataFrame[Close, Volume]}."""
    if progress_cb:
        progress_cb(f"Downloading price history for {len(tickers)} stocks...")
    raw = yf.download(
        tickers, period=config.PRICE_HISTORY_PERIOD,
        interval=config.PRICE_HISTORY_INTERVAL, group_by="ticker",
        threads=True, progress=False, auto_adjust=True,
    )
    out = {}
    for t in tickers:
        try:
            sub = raw[t][["Close", "Volume"]].dropna()
            if len(sub) >= 10:
                out[t] = sub
        except Exception:
            continue
    return out


def compute_metrics(price_data: dict, universe: pd.DataFrame, trending: set) -> pd.DataFrame:
    session_frac = _session_elapsed_fraction()
    today_et = dt.datetime.now(_ET).date()
    rows = []
    for symbol, hist in price_data.items():
        closes = hist["Close"]
        vols = hist["Volume"]
        if len(closes) < 10:
            continue
        last_close = closes.iloc[-1]
        pct_1d = (closes.iloc[-1] / closes.iloc[-2] - 1) * 100 if len(closes) >= 2 else 0.0
        pct_5d = (closes.iloc[-1] / closes.iloc[-6] - 1) * 100 if len(closes) >= 6 else pct_1d
        avg_vol20 = vols.iloc[-21:-1].mean() if len(vols) >= 21 else vols.iloc[:-1].mean()
        last_vol = vols.iloc[-1]
        # If the most recent bar is today's still-forming session, its volume
        # is a partial-day figure - project it to a full-day pace before
        # comparing against the (full-day) 20-day average, otherwise every
        # ticker looks artificially "quiet" until the close.
        last_bar_date = closes.index[-1].date() if hasattr(closes.index[-1], "date") else None
        if session_frac is not None and last_bar_date == today_et:
            last_vol = last_vol / session_frac
        vol_ratio = (last_vol / avg_vol20) if avg_vol20 and avg_vol20 > 0 else 1.0
        rows.append({
            "symbol": symbol,
            "last_close": last_close,
            "pct_1d": pct_1d,
            "pct_5d": pct_5d,
            "vol_ratio": vol_ratio,
            "in_trending_feed": symbol in trending,
            "spark": closes.tolist()[-20:],
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.merge(universe, left_on="symbol", right_on="Symbol", how="left")
    df["buzz_bonus"] = df["in_trending_feed"].map({True: 1.0, False: 0.0}).fillna(0.0)
    df["hot_score"] = scoring.hot_score(df)
    df["sleeper_score"] = scoring.sleeper_score(df)
    return df


def _split_by_sector(df: pd.DataFrame, count: int, score_col: str, tech_split: float = None) -> pd.DataFrame:
    """Picks `count` rows from df ranked by score_col, targeting the given
    Tech/Non-Tech split (default: config.TECH_SPLIT) while filling remaining
    slots regardless of sector if one bucket runs short."""
    tech_split = config.TECH_SPLIT if tech_split is None else tech_split
    tech_n = round(count * tech_split)
    nontech_n = count - tech_n
    tech_rows = df[df["SectorBucket"] == "Tech"].sort_values(score_col, ascending=False)
    nontech_rows = df[df["SectorBucket"] == "Non-Tech"].sort_values(score_col, ascending=False)

    picked = pd.concat([tech_rows.head(tech_n), nontech_rows.head(nontech_n)])
    if len(picked) < count:
        remaining = df.drop(picked.index).sort_values(score_col, ascending=False)
        picked = pd.concat([picked, remaining.head(count - len(picked))])
    return picked.sort_values(score_col, ascending=False).head(count)


def band_info(metrics: pd.DataFrame) -> dict:
    """How many scanned stocks sit in the under-$50 price band, and how many
    of them are tech - shown on the page to explain why that section is
    mostly non-tech."""
    in_band = (metrics["last_close"] >= config.PENNY_PRICE_MAX) & (metrics["last_close"] < config.UNDER50_PRICE_MAX)
    band = metrics[in_band]
    return {"total": int(len(band)), "tech": int((band["SectorBucket"] == "Tech").sum())}


def select_picks(metrics: pd.DataFrame, tech_split: float = None) -> dict:
    """Chooses the Hot, Sleeper and Under-$50 lists from already-scored metrics,
    so the tech/non-tech mix can be changed without rescanning."""
    hot = _split_by_sector(metrics, config.HOT_STOCKS_COUNT, "hot_score", tech_split)

    # Sleepers: prefer mid-cap, exclude anything already picked as "hot"
    sleeper_pool = metrics[~metrics["symbol"].isin(hot["symbol"])].copy()
    mid_pool = sleeper_pool[sleeper_pool["CapTier"] == "Mid"]
    if len(mid_pool) >= config.SLEEPER_STOCKS_COUNT:
        sleeper_pool = mid_pool
    sleeper = _split_by_sector(sleeper_pool, config.SLEEPER_STOCKS_COUNT, "sleeper_score", tech_split)

    # Hot under $50: same hot_score ranking, restricted to the price band, and
    # skipping names already shown in the sections above so the page never
    # lists one stock twice (and this section adds new names). Deliberately
    # NOT split by the tech/non-tech mix: only ~7% of stocks in this band are
    # tech, so a tech-heavy target would force weak tech names in ahead of
    # hotter ones.
    shown = set(hot["symbol"]) | set(sleeper["symbol"])
    in_band = (metrics["last_close"] >= config.PENNY_PRICE_MAX) & (metrics["last_close"] < config.UNDER50_PRICE_MAX)
    under50_pool = metrics[in_band & ~metrics["symbol"].isin(shown)]
    under50 = under50_pool.sort_values("hot_score", ascending=False).head(config.HOT_UNDER50_STOCKS_COUNT)
    return {"hot": hot, "sleeper": sleeper, "under50": under50}


def fetch_penny_candidates(progress_cb=None) -> pd.DataFrame:
    """Pulls Yahoo's free predefined screeners (small/aggressive-cap gainers
    and most-actives) and keeps only equities under PENNY_PRICE_MAX. These
    screeners are Yahoo's own curated, already-scored lists, so this avoids
    downloading price history for thousands of NASDAQ/NYSE tickers just to
    find the handful under $5."""
    if progress_cb:
        progress_cb("Pulling penny-stock candidates from small-cap screeners...")
    screener_ids = ["aggressive_small_caps", "small_cap_gainers", "most_actives", "day_gainers"]
    rows = {}
    for scr_id in screener_ids:
        try:
            r = requests.get(
                "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved",
                params={"scrIds": scr_id, "count": 250},
                headers=config.REQUEST_HEADERS, timeout=config.REQUEST_TIMEOUT,
            )
            r.raise_for_status()
            quotes = r.json()["finance"]["result"][0]["quotes"]
        except Exception:
            continue
        for q in quotes:
            price = q.get("regularMarketPrice")
            symbol = q.get("symbol")
            if (q.get("quoteType") != "EQUITY" or not symbol or not price
                    or not (0 < price < config.PENNY_PRICE_MAX)):
                continue
            rows[symbol] = q.get("shortName") or q.get("longName") or symbol
    return pd.DataFrame([{"Symbol": s, "Security": name} for s, name in rows.items()])


def penny_scan(progress_cb=None) -> pd.DataFrame:
    candidates = fetch_penny_candidates(progress_cb)
    if candidates.empty:
        if progress_cb:
            progress_cb("No penny-stock candidates found this run.")
        return candidates

    trending = fetch_trending_symbols()
    tickers = candidates["Symbol"].tolist()
    if progress_cb:
        progress_cb(f"Downloading price history for {len(tickers)} penny-stock candidates...")
    price_data = fetch_price_history(tickers, progress_cb=None)

    mini_universe = candidates.copy()
    mini_universe["SectorBucket"] = "Penny"
    mini_universe["CapTier"] = "Micro"

    metrics = compute_metrics(price_data, mini_universe, trending)
    if metrics.empty:
        return metrics
    # A screener candidate's live quote price can have since crept over the
    # threshold by the time yfinance's own daily bar is fetched - re-check.
    metrics = metrics[metrics["last_close"] < config.PENNY_PRICE_MAX]
    return metrics.sort_values("hot_score", ascending=False).head(config.HOT_PENNY_STOCKS_COUNT)


def scan(progress_cb=None, tech_split: float = None) -> dict:
    universe = load_universe()
    trending = fetch_trending_symbols()
    if progress_cb:
        progress_cb(f"Found {len(trending)} symbols on live trending feeds.")

    tickers = universe["Symbol"].tolist()
    price_data = fetch_price_history(tickers, progress_cb)
    if progress_cb:
        progress_cb(f"Got price history for {len(price_data)}/{len(tickers)} tickers.")

    metrics = compute_metrics(price_data, universe, trending)
    if metrics.empty:
        return {"hot": pd.DataFrame(), "sleeper": pd.DataFrame(), "under50": pd.DataFrame(), "metrics": metrics}

    picks = select_picks(metrics, tech_split)
    picks["metrics"] = metrics
    return picks
