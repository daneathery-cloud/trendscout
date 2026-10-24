"""Builds the phone edition of TrendScout: a static website (plain files) made from
one finished scan, ready to publish on GitHub Pages.

The phone can't run the scanner, so a scheduled job scans, calls build_site(), and
publishes the folder. The pages are the same ones the desktop app shows (render.py),
with every tech/non-tech mix embedded and the free-version matches looked up in advance.
Nothing personal goes in: the watchlist lives only on each phone."""
import concurrent.futures
import datetime as dt
import json
import os
import shutil

import config
import render
import scan_runner
import site_assets
from scanners import news

DEFAULT_REPO_URL = "https://github.com/daneathery-cloud/trendscout"


def check_quality(result: dict, universe_size: int) -> list:
    """Reasons a scan is too incomplete to publish (empty list = fine). A bad scan must
    never replace the last good snapshot."""
    problems = []
    metrics = result.get("stock_metrics")
    n_stocks = 0 if metrics is None else len(metrics)
    if n_stocks < 0.9 * universe_size:
        problems.append(f"only {n_stocks} of {universe_size} stocks priced (Yahoo may be blocking this server)")
    crypto = result["data"].get("crypto", {})
    if crypto.get("hot") is None or crypto["hot"].empty:
        problems.append("no crypto data")
    fx = result["data"].get("forex")
    if fx is None or len(fx) < 5:
        problems.append("fewer than 5 currency pairs")
    wire = result.get("wire_df")
    if wire is None or len(wire) < 100:
        problems.append(f"only {0 if wire is None else len(wire)} headlines")
    return problems


def _variants(result: dict) -> dict:
    """Hot / Sleeper / Under-$50 lists for every tech/non-tech mix, each with headlines."""
    cache = dict(result.get("stock_news_cache") or {})
    return {pct: scan_runner.repick_stocks(result["stock_metrics"], pct / 100, cache)
            for pct in config.TECH_SPLIT_OPTIONS}


def _paywalled_titles(variants: dict, data: dict, digest_df, wire_df) -> list:
    titles = set()

    def from_cards(df):
        if df is None or df.empty or "news" not in df.columns:
            return
        for items in df["news"]:
            for n in items or []:
                if render._is_paywalled_source(n.get("source")):
                    titles.add(n["title"])

    for v in variants.values():
        for key in ("hot", "sleeper", "under50"):
            from_cards(v[key])
    from_cards(data["stocks"].get("penny"))
    for key in ("hot", "sleeper"):
        from_cards(data["crypto"].get(key))
    for df in (digest_df, wire_df):
        if df is None or df.empty:
            continue
        for _, r in df.iterrows():
            snap = render.news_snapshot(r)
            if snap["is_paywalled_source"] or render._is_paywalled_source(snap["source"]):
                titles.add(snap["title"])
    return sorted(titles)


def _free_lookup(titles: list, progress=None) -> dict:
    """Pre-runs the 'find free versions' search for each paywalled story (the phone can't
    call Google News itself). Only what the popover needs is kept."""
    out = {}

    def one(title):
        r = news.find_free_versions(title)
        return title, {"keywords": r["keywords"], "search_url": r["search_url"], "error": r["error"],
                       "matches": [{"source": m["source"], "title": m["title"], "link": m["link"]} for m in r["matches"]]}

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for i, (title, info) in enumerate(pool.map(one, titles), start=1):
            out[title] = info
            if progress and i % 25 == 0:
                progress(f"  free-version lookups: {i}/{len(titles)}")
    return out


def _watchlist_page() -> str:
    body = f"""
<div class="disclaimer">{render._esc(config.DISCLAIMER)}</div>
<div class="page-actions">
  <p class="section-sub">Your watchlist is saved on <b>this device only</b> (it doesn't sync with your PC or other phones).
  Saved items keep the prices from the snapshot you saved them in. Untick the box to remove one.</p>
  <span id="wl-share"></span>
</div>
<div id="wl-root"></div>
"""
    return render._page_shell("watchlist", body)


def _diagnostics_page() -> str:
    body = f"""
<h2 class="section">🩺 Diagnostics</h2>
<p class="section-sub">If something looks wrong, tap Copy and paste the result into your chat with Claude. It lists the
site version, when the snapshot was scanned, this device's browser, how many watchlist items are saved here, and any recent errors.</p>
<div class="page-actions"><button type="button" class="share-btn page" onclick="copyDiag(this)">{render._SHARE_ICON}<span>Copy diagnostics</span></button></div>
<pre class="diag" id="diag">Gathering...</pre>
"""
    return render._page_shell("diagnostics", body, title_suffix=" - Diagnostics")


def build_site(result: dict, out_dir: str, repo_url: str = DEFAULT_REPO_URL, progress=print,
               look_up_free_versions: bool = True, tz_label: str = "CT") -> dict:
    """Writes the whole phone site into out_dir (replacing its contents)."""
    generated = result["generated_at"]
    scan_label = generated.strftime("%b %d, %Y %I:%M %p").replace(" 0", " ") + f" {tz_label}"
    build_id = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    data = result["data"]

    progress("Preparing every tech/non-tech mix...")
    variants = _variants(result)
    digest_df, wire_df = result["digest_df"], result["wire_df"]

    free = {}
    if look_up_free_versions:
        titles = _paywalled_titles(variants, data, digest_df, wire_df)
        progress(f"Looking up free versions for {len(titles)} paywalled stories...")
        free = _free_lookup(titles, progress)

    render.configure_static(
        version_label=f"Phone edition · scanned {scan_label}", scan_label=scan_label,
        scan_epoch=generated.timestamp(), build_id=build_id, repo_url=repo_url)
    try:
        default_pct = int(round(config.TECH_SPLIT * 100))
        page_data = {
            "stocks": {"penny": data["stocks"].get("penny")},
            "crypto": data["crypto"], "forex": data.get("forex"),
            "under50_info": data.get("under50_info"), "digest": digest_df,
            "tech_percent": default_pct,
            "footer_html": (
                f'<div class="history-bar">Phone edition. This snapshot was scanned <b>{render._esc(scan_label)}</b> '
                f'and is refreshed automatically a few times a day. Your watchlist is saved on this device only. '
                f'<a href="{render._esc(repo_url)}/actions/workflows/scan.yml">Run a new scan now</a> '
                f'(needs a GitHub sign-in).</div>'),
        }
        pages = {
            "index.html": render.build_scan_page(page_data, set(), generated_at=generated, variants=variants),
            "wire.html": render.build_wire_page(wire_df, set()),
            "watchlist.html": _watchlist_page(),
            "diagnostics.html": _diagnostics_page(),
        }
    finally:
        render.STATIC["on"] = False

    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)
    for name, html in pages.items():
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as f:
            f.write(html)
    with open(os.path.join(out_dir, "free.json"), "w", encoding="utf-8") as f:
        json.dump(free, f, separators=(",", ":"))
    with open(os.path.join(out_dir, "version.json"), "w", encoding="utf-8") as f:
        json.dump({"build": build_id, "scan_epoch": generated.timestamp(), "scan_label": scan_label}, f)
    with open(os.path.join(out_dir, "manifest.webmanifest"), "w", encoding="utf-8") as f:
        f.write(site_assets.manifest_json())
    with open(os.path.join(out_dir, "sw.js"), "w", encoding="utf-8") as f:
        f.write(site_assets.sw_js(build_id))
    open(os.path.join(out_dir, ".nojekyll"), "w").close()
    with open(os.path.join(out_dir, "robots.txt"), "w") as f:
        f.write("User-agent: *
Disallow: /
")
    site_assets.write_icons(out_dir)

    sizes = {name: os.path.getsize(os.path.join(out_dir, name)) for name in list(pages) + ["free.json"]}
    return {"build_id": build_id, "scan_label": scan_label, "free_stories": len(free), "sizes": sizes,
            "mixes": sorted(variants)}
