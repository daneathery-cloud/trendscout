"""Crypto scanner: CoinGecko's free public API (no key required)."""
import time
import requests
import pandas as pd

import config
import scoring

BASE = "https://api.coingecko.com/api/v3"


def fetch_trending_ids() -> set:
    try:
        r = requests.get(f"{BASE}/search/trending", headers=config.REQUEST_HEADERS,
                          timeout=config.REQUEST_TIMEOUT)
        r.raise_for_status()
        return {c["item"]["id"] for c in r.json().get("coins", [])}
    except Exception:
        return set()


def fetch_markets(pages: int = 3, per_page: int = 250, progress_cb=None) -> pd.DataFrame:
    rows = []
    for page in range(1, pages + 1):
        if progress_cb:
            progress_cb(f"Fetching crypto market data (page {page}/{pages})...")
        try:
            r = requests.get(f"{BASE}/coins/markets", params={
                "vs_currency": "usd", "order": "market_cap_desc",
                "per_page": per_page, "page": page,
                "price_change_percentage": "24h,7d", "sparkline": "true",
            }, headers=config.REQUEST_HEADERS, timeout=config.REQUEST_TIMEOUT)
            r.raise_for_status()
            rows.extend(r.json())
        except Exception:
            break
        time.sleep(1.2)  # be polite to the free public tier
    return pd.DataFrame(rows)


def compute_metrics(df: pd.DataFrame, trending_ids: set) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df["pct_1d"] = df["price_change_percentage_24h_in_currency"].fillna(0.0)
    df["pct_5d"] = df["price_change_percentage_7d_in_currency"].fillna(df["pct_1d"])
    df["vol_to_mcap"] = df["total_volume"] / df["market_cap"].replace(0, pd.NA)
    df["vol_ratio"] = (df["vol_to_mcap"] / df["vol_to_mcap"].median()).fillna(1.0)
    df["in_trending_feed"] = df["id"].isin(trending_ids)
    df["buzz_bonus"] = df["in_trending_feed"].map({True: 1.0, False: 0.0}).fillna(0.0)
    df["symbol_disp"] = df["symbol"].str.upper()
    df["spark"] = df["sparkline_in_7d"].apply(
        lambda s: s.get("price", [])[-30:] if isinstance(s, dict) else []
    )
    df["hot_score"] = scoring.hot_score(df)
    df["sleeper_score"] = scoring.sleeper_score(df)
    return df


def scan(progress_cb=None) -> dict:
    trending_ids = fetch_trending_ids()
    if progress_cb:
        progress_cb(f"Found {len(trending_ids)} coins on CoinGecko's trending feed.")

    markets = fetch_markets(pages=3, progress_cb=progress_cb)
    metrics = compute_metrics(markets, trending_ids)
    if metrics.empty:
        return {"hot": pd.DataFrame(), "sleeper": pd.DataFrame()}

    hot = metrics.sort_values("hot_score", ascending=False).head(config.HOT_CRYPTO_COUNT)

    # Sleepers: outside the top 100 by market cap (i.e. not already
    # mainstream), ranked by the sleeper score (volume surge, buzz, quiet price)
    sleeper_pool = metrics[
        (~metrics["id"].isin(hot["id"])) & (metrics["market_cap_rank"].fillna(9999) > 100)
    ]
    sleeper = sleeper_pool.sort_values("sleeper_score", ascending=False).head(config.SLEEPER_CRYPTO_COUNT)

    return {"hot": hot, "sleeper": sleeper}
