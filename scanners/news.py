"""News scanner: public RSS feeds only.

For subscription outlets (WSJ, Barron's, Bloomberg, etc.) this reads ONLY the
headline + teaser summary those outlets themselves publish in their public
RSS feeds for syndication - the same text a non-subscriber sees on the
homepage. No paywalled page is ever fetched or bypassed.

It also flags headlines from free outlets that explicitly reference one of
those paywalled outlets (e.g. "...according to a Wall Street Journal report"),
since that's a legitimate, publicly available way to learn what a paywalled
piece said without a subscription.
"""
import calendar
import re
import time
from urllib.parse import quote

import feedparser
import pandas as pd

import config

_MARKER_RE = re.compile(
    "|".join(re.escape(m) for m in config.PAYWALLED_OUTLET_MARKERS), re.IGNORECASE
)


def _mentions_paywalled_outlet(text: str) -> str | None:
    m = _MARKER_RE.search(text or "")
    return m.group(0) if m else None


def _entry_time(e):
    """Publish time as a UTC epoch, or None if the entry has no usable date."""
    parsed = e.get("published_parsed") or e.get("updated_parsed")
    return calendar.timegm(parsed) if parsed else None


def fetch_feed(name: str, url: str, limit: int = 25) -> tuple:
    """Returns (items, raw_entry_count). Items older than MAX_NEWS_AGE_DAYS are
    dropped and the rest are ordered newest-first, so a feed that has quietly
    stopped updating (as WSJ's old feed addresses did) yields nothing instead
    of ancient headlines."""
    items = []
    raw_count = 0
    try:
        d = feedparser.parse(url)
        entries = list(d.entries)
        raw_count = len(entries)
        is_google = "news.google.com" in url
        cutoff = time.time() - config.MAX_NEWS_AGE_DAYS * 86400
        dated = [(_entry_time(e), e) for e in entries]
        fresh = [(t, e) for t, e in dated if t is None or t >= cutoff]
        fresh.sort(key=lambda te: te[0] or 0, reverse=True)
        for _, e in fresh[:limit]:
            title = e.get("title", "").strip()
            summary = re.sub("<[^<]+?>", "", e.get("summary", "")).strip()
            if is_google:
                # Google appends " - Outlet" to titles and its "summary" is just
                # the headline again, so drop both.
                title = re.sub(rf"\s+-\s+{re.escape(name)}\s*$", "", title)
                summary = ""
            items.append({
                "source": name,
                "title": title,
                "summary": summary[:300],
                "link": e.get("link", ""),
                "published": e.get("published", ""),
            })
    except Exception:
        pass
    return items, raw_count


def _tag_paywall_columns(df: pd.DataFrame) -> pd.DataFrame:
    df["is_paywalled_source"] = df["source"].str.contains("WSJ|Barron", case=False, na=False)
    df["secondary_mention"] = df.apply(
        lambda r: None if r["is_paywalled_source"]
        else _mentions_paywalled_outlet(r["title"] + " " + r["summary"]),
        axis=1,
    )
    return df


def fetch_all_feeds(progress_cb=None, limit_per_feed: int = None) -> pd.DataFrame:
    limit_per_feed = limit_per_feed or config.WIRE_PER_FEED_LIMIT
    all_items = []
    for name, url in config.NEWS_FEEDS:
        if progress_cb:
            progress_cb(f"Reading {name} headlines...")
        items, raw_count = fetch_feed(name, url, limit=limit_per_feed)
        if progress_cb and not items:
            progress_cb(f"  {name}: skipped - " + (
                f"nothing newer than {config.MAX_NEWS_AGE_DAYS} days (feed may be discontinued)"
                if raw_count else "no response"))
        all_items.extend(items)
    df = pd.DataFrame(all_items)
    if df.empty:
        return df
    return _tag_paywall_columns(df)


def diverse_digest(df: pd.DataFrame, count: int, per_source_cap: int = None) -> pd.DataFrame:
    """Round-robin picks across sources so one heavily-updated feed can't
    crowd out the short curated digest. Each outlet's items arrive
    newest-first, so the digest is the most recent headlines per outlet -
    not ranked by web traffic or popularity."""
    if df is None or df.empty:
        return df
    per_source_cap = per_source_cap or config.DIGEST_PER_SOURCE_CAP
    by_source = {src: grp.reset_index(drop=True) for src, grp in df.groupby("source", sort=False)}
    # Preserve the source order as configured, not groupby's alphabetical order
    source_order = [name for name, _ in config.NEWS_FEEDS if name in by_source]
    picked_rows = []
    counts = {src: 0 for src in source_order}
    idx = {src: 0 for src in source_order}
    while len(picked_rows) < count:
        progressed = False
        for src in source_order:
            if len(picked_rows) >= count:
                break
            if counts[src] >= per_source_cap:
                continue
            pool = by_source[src]
            if idx[src] >= len(pool):
                continue
            picked_rows.append(pool.iloc[idx[src]])
            idx[src] += 1
            counts[src] += 1
            progressed = True
        if not progressed:
            break
    return pd.DataFrame(picked_rows).reset_index(drop=True) if picked_rows else df.head(0)


def search_ticker_news(query: str, limit: int = None) -> list:
    """Per-ticker headlines via Google News RSS search - free, no key.
    Surfaces both free-outlet coverage and paywalled-outlet headlines/teasers
    (Google indexes the public headline+snippet, never the full paywalled body)."""
    limit = limit or config.NEWS_PER_TICKER
    url = config.GOOGLE_NEWS_SEARCH.format(query=quote(query))
    items = []
    try:
        d = feedparser.parse(url)
        for e in d.entries[:limit]:
            source = e.get("source", {}).get("title", "") if hasattr(e, "get") else ""
            title = e.get("title", "")
            items.append({
                "title": title,
                "source": source,
                "link": e.get("link", ""),
                "paywalled_outlet": _mentions_paywalled_outlet(f"{title} {source}"),
            })
    except Exception:
        pass
    return items


# ---------------------------------------------------------------------------
# "Find free versions": look for the same story at outlets without a hard paywall
# ---------------------------------------------------------------------------
import requests

_EXCLUDED_OUTLET_RE = re.compile(
    "|".join(re.escape(m) for m in config.FREE_SEARCH_EXCLUDED_OUTLETS), re.IGNORECASE)

_STOP = set("""a an the of to in on for and or at as by is are be been with from after amid how why what who whom
which its it's his her their this that these those up down off out over under into than then just still more most
next could would should may might will can says say said here's heres new now not no yes our your you we they he she i
vs""".split())
_GENERIC = set("stock stocks share shares market markets wall street opinion talk roundup recap today week "
               "investors investor analysts analyst".split())
# Headline action words: other outlets use different verbs, so they only narrow the search.
_FILLER = set("""sink sinks soar soars jump jumps fall falls rise rises rally rallies slide slides slump slumps surge
surges plunge plunges climb climbs drop drops gain gains tumble tumbles rebound rebounds slash slashes cut cuts raise
raises lift lifts hike hikes pass passes test tests help helps snap race races look looks offer offers explain explains
get gets set sets make makes take takes show shows keep keeps turn turns hit hits beat beats miss misses top tops ahead
head heads push pushes pull pulls drive drives send sends leave leaves""".split())

# Words that make a headline identifiable on their own (a company, a coin, a country...).
# Without one, a headline is only matched when ALL its key words appear, so everyday phrases
# like "defensive plays" can't pull in sports stories.
_EXTRA_ENTITIES = set("""bitcoin ethereum solana dogecoin xrp binance coinbase tether stablecoin fed fomc opec nato
china russia ukraine israel iran iraq gaza japan india europe eu mexico canada taiwan korea saudi venezuela trump
biden powell musk altman nvidia tesla apple amazon google alphabet microsoft meta openai anthropic spacex
france germany britain uk spain italy brazil argentina turkey egypt syria lebanon pakistan afghanistan australia
africa asia greenland cuba nigeria indonesia vietnam philippines thailand singapore london paris berlin beijing moscow
tehran kyiv washington congress senate pentagon treasury opec wall""".split())
_CORP_WORDS = set("""inc corp corporation company holdings group ltd plc technologies technology international financial
systems solutions industries partners trust bancorp bank class common stock health energy capital power first american
global united general services resources brands""".split())
_entity_cache: dict = {}


def _known_entities() -> frozenset:
    if "names" not in _entity_cache:
        names = set(_EXTRA_ENTITIES)
        try:
            for company in pd.read_csv(config.UNIVERSE_CSV)["Security"].astype(str):
                for tok in re.findall(r"[a-z0-9&]+", company.lower()):
                    if len(tok) >= 4 and tok not in _CORP_WORDS and tok not in _STOP and tok not in _GENERIC:
                        names.add(tok)
        except Exception:
            pass
        _entity_cache["names"] = frozenset(names)
    return _entity_cache["names"]


def _is_entity(word: str) -> bool:
    return ((word.isupper() and len(word) >= 2) or "&" in word
            or (any(c.isupper() for c in word[1:]) and not word.isupper())
            or word.lower() in _known_entities())


_free_cache: dict = {}
_FREE_CACHE_SECONDS = 1800
_MIN_SCORE = 0.66   # at least two of three identifying words (or two thirds of a generic phrase) must match


def story_keywords(title: str, limit: int = 5, keep_generic: bool = False) -> list:
    """The few words that identify a story, whatever an outlet's wording:
    names and tickers first (CamelCase / ALL-CAPS), then other content words.
    Filler like 'soars' is dropped, and so is generic market vocabulary
    ('stock', 'market') unless keep_generic is set. Works on Title Case headlines."""
    title = re.sub(r"\s+-\s+[^-]{2,40}$", "", title or "").replace("’", "'")
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9&'.\-]*", title)
    seen, entities, rest = set(), [], []
    for tok in tokens:
        clean = re.sub(r"'s$", "", tok).strip(".'-")
        low = clean.lower()
        if len(low) < 2 or low in seen or low in _STOP or low in _FILLER:
            continue
        if low in _GENERIC and not keep_generic:
            continue
        seen.add(low)
        is_entity = (clean.isupper() and len(clean) >= 2) or "&" in clean or \
                    (any(c.isupper() for c in clean[1:]) and not clean.isupper())
        (entities if is_entity else rest).append(clean)
    return (entities + rest)[:limit]


def identifying_words(title: str) -> list:
    """Story keywords; for headlines with very few (e.g. WSJ's 'Health Care
    Roundup: Market Talk' series) the generic words ARE the identity, so keep them."""
    kw = story_keywords(title, 5)
    return kw if len(kw) >= 3 else story_keywords(title, 5, keep_generic=True)


def _tokens(text: str) -> set:
    text = re.sub(r"\s+-\s+[^-]{2,40}$", "", text or "").replace("’", "'")
    return {re.sub(r"'s$", "", w) for w in re.findall(r"[a-z0-9$%&']+", text.lower())}


def _score(identity: list, original: str, candidate: str) -> float:
    """Share of the story's (up to three) identifying words found in the
    candidate headline, plus a small overall-overlap tiebreak."""
    # Normally the three most identifying words. But when the identity includes generic
    # market words (a series title like "Health Care Roundup: Market Talk"), the whole
    # phrase is the identity, so all of it must match.
    generic_headline = any(w.lower() in _GENERIC for w in identity)
    ident = [w.lower() for w in (identity if generic_headline else identity[:3])]
    if not ident:
        return 0.0
    cand = _tokens(candidate)
    coverage = sum(w in cand for w in ident) / len(ident)
    if coverage < (0.66 if any(_is_entity(w) for w in identity) else 0.99):
        return 0.0
    orig = {w for w in _tokens(original) if w not in _STOP}
    cand_content = {w for w in cand if w not in _STOP}
    jaccard = len(orig & cand_content) / max(1, len(orig | cand_content))
    return coverage + 0.1 * jaccard


def free_search_url(keywords: list) -> str:
    """A Google News search (opens in the user's browser) for the keywords with
    the hard-paywalled outlets excluded."""
    excl = " ".join(f"-site:{d}" for d in config.FREE_SEARCH_EXCLUDED_DOMAINS)
    query = f"{' '.join(keywords)} {excl} when:7d"
    return f"https://news.google.com/search?q={quote(query)}&hl=en-US&gl=US&ceid=US:en"


def _is_excluded_outlet(entry) -> bool:
    src = entry.get("source", {}) or {}
    if _EXCLUDED_OUTLET_RE.search(src.get("title", "")):
        return True
    host = re.sub(r"^https?://(www\.)?", "", src.get("href", "")).split("/")[0].lower()
    return any(host == d or host.endswith("." + d) for d in config.FREE_SEARCH_EXCLUDED_DOMAINS)


def _search_rss(query: str) -> list:
    url = f"https://news.google.com/rss/search?q={quote(query + ' when:5d')}&hl=en-US&gl=US&ceid=US:en"
    r = requests.get(url, headers=config.REQUEST_HEADERS, timeout=10)
    r.raise_for_status()
    return feedparser.parse(r.content).entries


def _rank(entries, title: str, identity: list, seen_links: set, seen_sources: set) -> list:
    out = []
    for e in entries:
        if _is_excluded_outlet(e):
            continue
        link, src = e.get("link", ""), (e.get("source", {}) or {}).get("title", "")
        if not link or link in seen_links or src in seen_sources:
            continue
        score = _score(identity, title, e.get("title", ""))
        if score < _MIN_SCORE:
            continue
        seen_links.add(link)
        seen_sources.add(src)
        out.append({
            "source": src, "link": link, "published": e.get("published", ""), "score": round(score, 2),
            "title": re.sub(rf"\s+-\s+{re.escape(src)}\s*$", "", e.get("title", "")) if src else e.get("title", ""),
        })
    return sorted(out, key=lambda m: -m["score"])


def find_free_versions(title: str, max_results: int = 5) -> dict:
    """Best-effort search for the same story at outlets that aren't hard-paywalled.
    Always returns the keywords and a Google News link; 'matches' may be empty."""
    identity = identifying_words(title)
    result = {"keywords": " ".join(identity), "search_url": free_search_url(identity[:3]),
              "matches": [], "error": None}
    if not identity:
        return result
    cached = _free_cache.get(title)
    if cached and time.time() - cached[0] < _FREE_CACHE_SECONDS:
        return cached[1]
    seen_links, seen_sources, matches = set(), set(), []
    try:
        matches += _rank(_search_rss(" ".join(identity)), title, identity, seen_links, seen_sources)
        if len(matches) < 2 and len(identity) > 2:
            # Too narrow: other outlets word it differently. Retry on the most identifying words.
            matches += _rank(_search_rss(" ".join(identity[:2])), title, identity, seen_links, seen_sources)
    except Exception as e:  # network trouble must never break the page
        result["error"] = f"{type(e).__name__}: {e}"
        return result
    matches.sort(key=lambda m: -m["score"])
    result["matches"] = matches[:max_results]
    _free_cache[title] = (time.time(), result)
    return result
