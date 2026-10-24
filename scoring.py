"""Shared scoring helpers: turn raw metrics into comparable 0-1 scores."""
import pandas as pd


def percentile_rank(series: pd.Series) -> pd.Series:
    """Rank values to 0..1, robust to NaNs and constant columns."""
    s = series.astype(float)
    if s.notna().sum() < 2:
        return pd.Series(0.5, index=s.index)
    ranked = s.rank(pct=True, na_option="bottom")
    return ranked.fillna(0.0)


def hot_score(df: pd.DataFrame) -> pd.Series:
    """Higher = more 'hot right now': price momentum + volume surge + buzz."""
    momentum = percentile_rank(df["pct_5d"])
    vol_surge = percentile_rank(df["vol_ratio"])
    buzz = df.get("buzz_bonus", pd.Series(0.0, index=df.index)).fillna(0.0)
    return 0.45 * momentum + 0.4 * vol_surge + 0.15 * buzz


def sleeper_score(df: pd.DataFrame) -> pd.Series:
    """Higher = rising attention (volume/news) without a big price move yet."""
    vol_surge = percentile_rank(df["vol_ratio"])
    quiet_price = 1.0 - percentile_rank(df["pct_5d"].abs())
    buzz = df.get("buzz_bonus", pd.Series(0.0, index=df.index)).fillna(0.0)
    return 0.5 * vol_surge + 0.3 * quiet_price + 0.2 * buzz
