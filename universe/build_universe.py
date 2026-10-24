"""One-time/occasional builder: pulls S&P 500 (large-cap) and S&P 400 (mid-cap)
constituent lists from Wikipedia's public pages, tags each ticker as Tech or
Non-Tech, and writes universe.csv. Re-run this occasionally to refresh the
ticker list; it is NOT part of the live scan (which reads universe.csv).
"""
import io
import requests
import pandas as pd

HEADERS = {"User-Agent": "Mozilla/5.0 (TrendScout research tool; personal use)"}

TECH_SECTORS = {"Information Technology"}
TECH_SUBINDUSTRIES = {"Interactive Media & Services", "Interactive Home Entertainment"}


def fetch_table(url: str) -> pd.DataFrame:
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    tables = pd.read_html(io.StringIO(r.text))
    return tables[0]


def classify(row) -> str:
    if row["GICS Sector"] in TECH_SECTORS:
        return "Tech"
    if row.get("GICS Sub-Industry") in TECH_SUBINDUSTRIES:
        return "Tech"
    return "Non-Tech"


def main():
    sp500 = fetch_table("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
    sp500 = sp500[["Symbol", "Security", "GICS Sector", "GICS Sub-Industry"]].copy()
    sp500["CapTier"] = "Large"

    sp400 = fetch_table("https://en.wikipedia.org/wiki/List_of_S%26P_400_companies")
    sp400 = sp400[["Symbol", "Security", "GICS Sector", "GICS Sub-Industry"]].copy()
    sp400["CapTier"] = "Mid"

    combined = pd.concat([sp500, sp400], ignore_index=True)
    combined["Symbol"] = combined["Symbol"].str.replace(".", "-", regex=False).str.strip()
    combined["SectorBucket"] = combined.apply(classify, axis=1)
    combined = combined.drop_duplicates(subset="Symbol").reset_index(drop=True)

    out_path = "universe.csv"
    combined.to_csv(out_path, index=False)
    print(f"Wrote {len(combined)} tickers to {out_path}")
    print(combined.groupby(["CapTier", "SectorBucket"]).size())


if __name__ == "__main__":
    main()
