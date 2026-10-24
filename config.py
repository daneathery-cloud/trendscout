"""Shared configuration for TrendScout."""
import os
import sys


def resource_path(relative_path: str) -> str:
    """Resolves a bundled resource path both when run from source and when
    frozen into a PyInstaller onefile exe (which extracts data to _MEIPASS)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative_path)


UNIVERSE_CSV = resource_path(os.path.join("universe", "universe.csv"))

# Report composition
TECH_SPLIT = 0.6          # default fraction of stock slots given to Tech (users can change it in the app)
TECH_SPLIT_OPTIONS = [40, 50, 60, 70, 80]   # tech % choices offered in the Scan Report
HOT_STOCKS_COUNT = 15
SLEEPER_STOCKS_COUNT = 12
HOT_UNDER50_STOCKS_COUNT = 12
UNDER50_PRICE_MAX = 50.0   # "hot stocks under $50" covers PENNY_PRICE_MAX..this; below $5 is the penny section
HOT_PENNY_STOCKS_COUNT = 10
PENNY_PRICE_MAX = 5.0   # SEC general penny-stock threshold; catches the $1-5 range too
HOT_CRYPTO_COUNT = 12
SLEEPER_CRYPTO_COUNT = 10
NEWS_PER_TICKER = 3
TOP_NEWS_DIGEST_COUNT = 12

# yfinance history window used for scoring
PRICE_HISTORY_PERIOD = "2mo"
PRICE_HISTORY_INTERVAL = "1d"

# Forex majors (Yahoo Finance FX tickers)
FX_PAIRS = [
    ("EURUSD=X", "EUR/USD"),
    ("GBPUSD=X", "GBP/USD"),
    ("USDJPY=X", "USD/JPY"),
    ("USDCHF=X", "USD/CHF"),
    ("AUDUSD=X", "AUD/USD"),
    ("USDCAD=X", "USD/CAD"),
    ("NZDUSD=X", "NZD/USD"),
    ("USDCNY=X", "USD/CNY"),
    ("USDMXN=X", "USD/MXN"),
    ("USDINR=X", "USD/INR"),
]

# RSS feeds. WSJ/Barron's are subscription sites; these feeds are the
# headline+teaser text those outlets publish openly for syndication -
# no login or paywall bypass involved.
def _google_site_feed(site: str, terms: str = "") -> str:
    """Reuters and Barron's publish no usable public RSS feed, so their
    headlines come from a Google News search restricted to that site
    (headline + link only, no article text)."""
    from urllib.parse import quote
    query = f"site:{site} {terms} when:3d".replace("  ", " ")
    return f"https://news.google.com/rss/search?q={quote(query)}&hl=en-US&gl=US&ceid=US:en"


# Order here is the order outlets take turns in the Scan Report digest.
NEWS_FEEDS = [
    # WSJ's old feeds.a.dj.com addresses are frozen at Jan 2025; these are the live ones.
    ("WSJ Markets", "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain"),
    ("Reuters", _google_site_feed("reuters.com", "(markets OR stocks OR economy OR business)")),
    ("Barron's", _google_site_feed("barrons.com")),
    ("WSJ World News", "https://feeds.content.dowjones.io/public/rss/RSSWorldNews"),
    ("MarketWatch Top Stories", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    ("MarketWatch Bulletins", "https://feeds.content.dowjones.io/public/rss/mw_bulletins"),
    # Yahoo's own RSS (news/rssindex, rss/topstories) stopped updating as of
    # 2026-09-30 - both sat stuck at 7+ days old. Same Google News workaround
    # already used for Reuters/Barron's, which have no reliable feed either.
    ("Yahoo Finance", _google_site_feed("finance.yahoo.com", "(stock OR stocks OR market)")),
    ("CNBC", "https://www.cnbc.com/id/10000664/device/rss/rss.html"),
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss"),
    ("Investing.com Stocks", "https://www.investing.com/rss/news_25.rss"),
    ("Forbes Business", "https://www.forbes.com/business/feed/"),
    ("Benzinga", "https://www.benzinga.com/feed"),
]

# Cap per-source items in the short curated digest on the Scan Report tab,
# so one heavily-updated feed can't crowd out everything else.
DIGEST_PER_SOURCE_CAP = 3
MAX_NEWS_AGE_DAYS = 5  # headlines older than this are dropped; a feed with nothing newer is reported as stale
WIRE_PER_FEED_LIMIT = 30  # how many entries to pull per feed for the Headline Wire tab

# Outlets we specifically flag when *other* free sources are discussing /
# quoting them, since the outlets themselves sit behind a paywall.
PAYWALLED_OUTLET_MARKERS = [
    "Wall Street Journal", "WSJ", "Barron's", "Barrons",
    "Bloomberg", "Financial Times", "The Information",
]

# Outlets the "find free versions" search leaves out: hard-paywalled sites, by
# domain (used in the Google News link) and by outlet name (used to filter results).
# Free access at any outlet can still change - some give a few free articles a month.
FREE_SEARCH_EXCLUDED_DOMAINS = [
    "wsj.com", "barrons.com", "bloomberg.com", "ft.com", "theinformation.com",
    "nytimes.com", "washingtonpost.com", "economist.com", "businessinsider.com",
]
FREE_SEARCH_EXCLUDED_OUTLETS = [
    "Wall Street Journal", "WSJ", "Barron", "Bloomberg", "Financial Times", "The Information",
    "New York Times", "Washington Post", "The Economist", "Business Insider",
]

GOOGLE_NEWS_SEARCH ="https://news.google.com/rss/search?q={query}+when:3d&hl=en-US&gl=US&ceid=US:en"

REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (TrendScout personal research tool)"}
REQUEST_TIMEOUT = 20

DISCLAIMER = (
    "TrendScout is a personal research aggregator. It summarizes publicly available "
    "market data, headlines, and social/search signals into one report. It is NOT "
    "financial advice, and nothing in this report is a recommendation to buy, sell, "
    "or hold any security, cryptocurrency, or currency. Data comes from free/public "
    "sources (Yahoo Finance, CoinGecko, StockTwits, public RSS feeds) and may be "
    "delayed, incomplete, or wrong. Always verify independently before making any "
    "financial decision."
)
