"""Forex scanner: major currency pairs via Yahoo Finance (yfinance).
No 'hot/sleeper' split here - just ranked by how much each pair has moved,
since currency trending doesn't map to the same momentum concept."""
import pandas as pd
import yfinance as yf

import config


def scan(progress_cb=None) -> pd.DataFrame:
    if progress_cb:
        progress_cb(f"Fetching {len(config.FX_PAIRS)} currency pairs...")
    tickers = [t for t, _ in config.FX_PAIRS]
    names = dict(config.FX_PAIRS)
    raw = yf.download(tickers, period="1mo", interval="1d", group_by="ticker",
                       threads=True, progress=False, auto_adjust=True)
    rows = []
    for t in tickers:
        try:
            closes = raw[t]["Close"].dropna()
            if len(closes) < 6:
                continue
            pct_1d = (closes.iloc[-1] / closes.iloc[-2] - 1) * 100
            pct_5d = (closes.iloc[-1] / closes.iloc[-6] - 1) * 100
            rows.append({
                "pair": names[t],
                "ticker": t,
                "last": closes.iloc[-1],
                "pct_1d": pct_1d,
                "pct_5d": pct_5d,
                "spark": closes.tolist()[-20:],
            })
        except Exception:
            continue
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.reindex(df["pct_5d"].abs().sort_values(ascending=False).index)
    return df
