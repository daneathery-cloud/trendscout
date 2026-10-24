"""Turns a finished scan into rows for the scan-history tables, so how each
section's picks (and the stocks that were NOT picked) fared afterward can be
analyzed later. Nothing here changes what the report shows."""
import store


def _num(v):
    """Float, or None for missing / NaN values (SQLite and CSV want blanks)."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    # 7 significant digits is all the precision the data has; it strips
    # float32 noise like 43.06050109863281 from the saved values.
    return None if f != f else float(f"{f:.7g}")


def _text(v):
    if v is None or (isinstance(v, float) and v != v):
        return None
    return str(v)


def _stock_row(section: str, rank, r) -> dict:
    return {
        "section": section, "rank": rank, "item_id": r["symbol"], "symbol": r["symbol"],
        "name": _text(r.get("Security")), "price": _num(r.get("last_close")),
        "pct_1d": _num(r.get("pct_1d")), "pct_5d": _num(r.get("pct_5d")), "pct_7d": None,
        "vol_ratio": _num(r.get("vol_ratio")),
        "hot_score": _num(r.get("hot_score")), "sleeper_score": _num(r.get("sleeper_score")),
        "sector": _text(r.get("SectorBucket")), "cap_tier": _text(r.get("CapTier")),
        "mcap_rank": None, "trending": int(bool(r.get("in_trending_feed", False))),
    }


def _crypto_row(section: str, rank, r) -> dict:
    # The crypto frames keep their 7-day change in a column called pct_5d.
    return {
        "section": section, "rank": rank, "item_id": r["id"], "symbol": _text(r.get("symbol_disp")),
        "name": _text(r.get("name")), "price": _num(r.get("current_price")),
        "pct_1d": _num(r.get("pct_1d")), "pct_5d": None, "pct_7d": _num(r.get("pct_5d")),
        "vol_ratio": _num(r.get("vol_ratio")),
        "hot_score": _num(r.get("hot_score")), "sleeper_score": _num(r.get("sleeper_score")),
        "sector": None, "cap_tier": None, "mcap_rank": _num(r.get("market_cap_rank")),
        "trending": int(bool(r.get("in_trending_feed", False))),
    }


def _fx_row(rank, r) -> dict:
    return {
        "section": "fx", "rank": rank, "item_id": r["ticker"], "symbol": _text(r.get("pair")),
        "name": _text(r.get("pair")), "price": _num(r.get("last")),
        "pct_1d": _num(r.get("pct_1d")), "pct_5d": _num(r.get("pct_5d")), "pct_7d": None,
        "vol_ratio": None, "hot_score": None, "sleeper_score": None,
        "sector": None, "cap_tier": None, "mcap_rank": None, "trending": 0,
    }


def _frame_rows(df, section, builder) -> list:
    if df is None or df.empty:
        return []
    return [builder(section, rank, r) for rank, (_, r) in enumerate(df.iterrows(), start=1)]


def rows_from_result(result: dict) -> list:
    """All saved items for one scan_runner.run_full_scan() result."""
    data = result["data"]
    stocks, crypto = data.get("stocks", {}), data.get("crypto", {})
    rows = []
    for section in ("hot", "sleeper", "under50", "penny"):
        rows += _frame_rows(stocks.get(section), section, _stock_row)
    rows += _frame_rows(crypto.get("hot"), "crypto_hot", _crypto_row)
    rows += _frame_rows(crypto.get("sleeper"), "crypto_sleeper", _crypto_row)
    fx = data.get("forex")
    if fx is not None and not fx.empty:
        rows += [_fx_row(rank, r) for rank, (_, r) in enumerate(fx.iterrows(), start=1)]
    # Every scored stock, picked or not: the baseline that picks get compared against.
    rows += _frame_rows(result.get("stock_metrics"), "universe", lambda s, _rank, r: _stock_row(s, None, r))
    return rows


def record(conn, result: dict, app_version: str, tech_percent: int) -> tuple:
    """Saves a finished scan. Returns (scan_id, rows_saved)."""
    scanned_at = result["generated_at"].strftime("%Y-%m-%d %H:%M:%S")
    return store.save_scan(conn, scanned_at, app_version, tech_percent, rows_from_result(result))
