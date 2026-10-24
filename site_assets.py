"""Static assets for the phone edition: the page script, service worker, web
manifest and app icons. site_builder.py writes them into the published site."""
import json
import os

# Runs after the shared page script (render.JS) and replaces the parts that talked
# to the desktop server: the watchlist lives in this device's own storage, the
# tech/non-tech mixes are all in the page, and free-version matches come from free.json.
STATIC_JS = r"""
const WL_KEY = 'trendscout.watchlist.v1', MIX_KEY = 'trendscout.mix.v1', ERR_KEY = 'trendscout.errors.v1';
const DEFAULT_MIX = 60;

function _lsGet(k, fallback) { try { const v = localStorage.getItem(k); return v === null ? fallback : JSON.parse(v); } catch (e) { return fallback; } }
function _lsSet(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); return true; } catch (e) { return false; } }

/* Recent errors, kept so the Diagnostics page can show them. */
function logError(msg) {
  const list = _lsGet(ERR_KEY, []);
  list.push(new Date().toISOString() + ' ' + String(msg).slice(0, 300));
  _lsSet(ERR_KEY, list.slice(-30));
}
window.addEventListener('error', e => logError('error: ' + e.message + ' @' + String(e.filename || '').split('/').pop() + ':' + e.lineno));
window.addEventListener('unhandledrejection', e => logError('promise: ' + ((e.reason && e.reason.message) || e.reason)));

/* ---------- watchlist, saved on this device ---------- */
const wlKey = (t, i) => t + ':' + i;
const wlLoad = () => _lsGet(WL_KEY, {});
const wlSave = m => _lsSet(WL_KEY, m);

function syncChecks(type, id, checked) {
  document.querySelectorAll('.track input').forEach(cb => {
    if (cb.dataset.type === type && cb.dataset.id === id) cb.checked = checked;
  });
}
function applyChecks() {
  const m = wlLoad();
  document.querySelectorAll('.track input').forEach(cb => { cb.checked = !!m[wlKey(cb.dataset.type, cb.dataset.id)]; });
}
function _saveCopy(holder) {
  // The card's own HTML is what gets saved, so the Watchlist looks exactly like the report.
  const c = holder.cloneNode(true);
  c.querySelectorAll('input[type=checkbox]').forEach(i => i.setAttribute('checked', ''));
  c.removeAttribute('style');
  return c.outerHTML;
}
function toggleWatch(el, removeOnUncheck) {
  const type = el.dataset.type, id = el.dataset.id, key = wlKey(type, id);
  const holder = el.closest('.card, .news-item, tr');
  const m = wlLoad();
  if (el.checked) {
    m[key] = {type: type, id: id, label: el.dataset.label || id, html: holder ? _saveCopy(holder) : '',
              added: new Date().toISOString(), asof: SCAN_LABEL};
  } else {
    delete m[key];
  }
  if (!wlSave(m)) {
    el.checked = !el.checked;
    alert('Could not save to this device (storage is full or blocked in this browser).');
    return;
  }
  syncChecks(type, id, el.checked);
  if (removeOnUncheck && !el.checked && holder) {
    holder.style.opacity = '0';
    setTimeout(renderWatchlist, 200);
  }
}

function _watchlistText(items) {
  const parts = items.map(it => {
    const b = new DOMParser().parseFromString(it.html || '', 'text/html').querySelector('.share-btn');
    const t = b ? (b.dataset.text || '') : (it.label || '');
    return t.replace(/\n*Shared from TrendScout[^\n]*$/, '').trim();
  });
  return 'TrendScout Watchlist - ' + new Date().toLocaleDateString() + '\n'
    + 'Prices are snapshots from the scan noted on each line.\n\n'
    + parts.join('\n\n') + '\n\nShared from TrendScout - informational only, not investment advice.';
}

function _watchlistNodes(items, forExport) {
  const groups = [['stock', '⭐ Stocks'], ['crypto', '⭐ Crypto'], ['fx', '⭐ Currencies'], ['news', '⭐ Stories']];
  const frag = document.createDocumentFragment();
  groups.forEach(([type, title]) => {
    const mine = items.filter(i => i.type === type);
    if (!mine.length) return;
    frag.appendChild(_el('h2', 'section', title));
    let holder;
    if (type === 'fx') {
      holder = document.createElement('table'); holder.className = 'fx';
      holder.innerHTML = '<thead><tr><th>Pair</th><th>Last</th><th>1d</th><th>5d</th>' + (forExport ? '' : '<th></th>') + '</tr></thead><tbody></tbody>';
    } else {
      holder = _el('div', type === 'news' ? 'news-list' : 'grid');
    }
    const body = type === 'fx' ? holder.querySelector('tbody') : holder;
    mine.forEach(it => {
      const t = document.createElement('template');
      t.innerHTML = (it.html || '').trim().replace('toggleWatch(this, false)', 'toggleWatch(this, true)');
      const node = t.content.firstElementChild;
      if (!node) return;
      const meta = '<div class="watch-meta">Snapshot: ' + (it.asof || '') + '</div>';
      if (type === 'stock' || type === 'crypto') {
        const anchor = node.querySelector('.badges');
        if (anchor) anchor.insertAdjacentHTML('afterend', meta); else node.insertAdjacentHTML('beforeend', meta);
      } else if (type === 'fx') {
        const first = node.querySelector('td'); if (first) first.insertAdjacentHTML('beforeend', meta);
      }
      if (forExport) node.querySelectorAll('.track, .share-btn, .free-btn, .remove-btn').forEach(x => x.remove());
      else node.querySelectorAll('.track input').forEach(i => { i.checked = true; });
      body.appendChild(node);
    });
    frag.appendChild(holder);
  });
  return frag;
}

function renderWatchlist() {
  const root = document.getElementById('wl-root');
  if (!root) return;
  const items = Object.values(wlLoad()).sort((a, b) => (b.added || '').localeCompare(a.added || ''));
  root.textContent = '';
  const shareSlot = document.getElementById('wl-share');
  if (shareSlot) shareSlot.textContent = '';
  if (!items.length) {
    root.appendChild(_el('div', 'empty-state', 'Nothing on your watchlist yet. Tick the small box at the bottom-right of any stock, coin, currency or headline on the Scan or Wire tabs to save it here.'));
    return;
  }
  if (shareSlot) {
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'share-btn page';
    b.dataset.title = 'TrendScout Watchlist';
    b.dataset.text = _watchlistText(items);
    b.dataset.download = '#export';
    b.onclick = ev => openShare(b, ev);
    b.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.6" y1="13.5" x2="15.4" y2="17.5"/><line x1="15.4" y1="6.5" x2="8.6" y2="10.5"/></svg><span>Share watchlist</span>';
    shareSlot.appendChild(b);
  }
  root.appendChild(_watchlistNodes(items, false));
}

/* "Download report" on the Watchlist: a self-contained copy, handed to the phone's share sheet when it can take files. */
function downloadReport(url) {
  if (url !== '#export') { window.location.href = url; return; }
  const items = Object.values(wlLoad()).sort((a, b) => (b.added || '').localeCompare(a.added || ''));
  const holder = document.createElement('div');
  holder.appendChild(_watchlistNodes(items, true));
  const css = (document.querySelector('style') || {}).textContent || '';
  const disc = (document.querySelector('.disclaimer') || {}).innerHTML || '';
  const html = '<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
    + '<title>TrendScout Watchlist Report</title><style>' + css + '</style></head><body>'
    + '<header class="top"><h1>⭐ TrendScout — Watchlist Report</h1><div class="meta">Generated ' + new Date().toLocaleString()
    + ' · ' + SITE_VERSION + '</div></header><div class="wrap"><div class="disclaimer">' + disc + '</div>'
    + '<p class="section-sub">Prices are snapshots from the scan date noted on each item, not live quotes.</p>'
    + holder.innerHTML + '<footer class="foot">Shared from TrendScout - informational only, not investment advice.</footer></div></body></html>';
  saveReport(html, 'TrendScout_Watchlist_' + new Date().toISOString().slice(0, 10) + '.html');
}
async function saveReport(html, filename) {
  const blob = new Blob([html], {type: 'text/html'});
  try {
    const file = new File([blob], filename, {type: 'text/html'});
    if (navigator.canShare && navigator.canShare({files: [file]})) {
      await navigator.share({files: [file], title: 'TrendScout Watchlist'});
      return;
    }
  } catch (e) { if (e && e.name === 'AbortError') return; }
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = filename;
  document.body.appendChild(a); a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1500);
}

/* ---------- tech / non-tech mix: every mix is already in the page ---------- */
function applyMix(pct) {
  const variants = document.querySelectorAll('.mix-variant');
  if (!variants.length) return;
  const have = Array.from(variants).some(v => v.dataset.mix === String(pct));
  const want = String(have ? pct : DEFAULT_MIX);
  variants.forEach(v => v.classList.toggle('active', v.dataset.mix === want));
}
function setMix(percent, btn) {
  _lsSet(MIX_KEY, percent);
  applyMix(percent);
}

/* ---------- find free versions: matches were looked up when the snapshot was built ---------- */
let _freeData = null;
async function getFreeData(title) {
  if (_freeData === null) {
    try {
      const r = await fetch('free.json?v=' + encodeURIComponent(BUILD_ID));
      _freeData = r.ok ? await r.json() : {};
    } catch (e) { _freeData = {}; }
  }
  const d = _freeData[title];
  if (d) return Object.assign({ok: true, error: null}, d);
  const clean = title.replace(/\s+-\s+[^-]{2,40}$/, '');
  return {ok: true, matches: [], error: null, notPrepared: true, keywords: clean.split(' ').slice(0, 4).join(' '),
          search_url: 'https://news.google.com/search?q=' + encodeURIComponent(clean + ' ' + FREE_EXCLUDE + ' when:7d') + '&hl=en-US&gl=US&ceid=US:en'};
}

/* ---------- freshness: banners, refresh, update detection ---------- */
function refreshNow() { location.reload(); }
async function checkVersion() {
  try {
    const r = await fetch('version.json', {cache: 'no-store'});
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const d = await r.json();
    window.__lastVersionCheck = new Date().toISOString() + ' - site build ' + d.build;
    if (d.build && d.build !== BUILD_ID) document.getElementById('update-banner').classList.add('show');
  } catch (e) { window.__lastVersionCheck = new Date().toISOString() + ' - could not check (' + e.message + ')'; }
}
function checkStale() {
  const hours = (Date.now() / 1000 - SCAN_EPOCH) / 3600;
  const b = document.getElementById('stale-banner');
  if (!b) return;
  if (hours > 30) {
    const age = hours >= 48 ? Math.floor(hours / 24) + ' days' : Math.round(hours) + ' hours';
    b.textContent = 'This snapshot is ' + age + ' old (scanned ' + SCAN_LABEL + '), so prices may have moved a lot.';
    b.classList.add('show');
  } else { b.classList.remove('show'); }
}

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('sw.js', {updateViaCache: 'none'}).then(reg => {
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) { reg.update().catch(() => {}); checkVersion(); checkStale(); }
    });
    window.addEventListener('pageshow', e => { if (e.persisted) { reg.update().catch(() => {}); checkVersion(); checkStale(); } });
  }).catch(e => logError('service worker: ' + e.message));
}

/* ---------- Diagnostics page ---------- */
async function renderDiagnostics() {
  const el = document.getElementById('diag');
  if (!el) return;
  await checkVersion();
  const wl = wlLoad(), errs = _lsGet(ERR_KEY, []);
  let sw = 'not supported';
  if ('serviceWorker' in navigator) {
    try {
      const regs = await navigator.serviceWorker.getRegistrations();
      sw = regs.length ? 'registered; controlling this page: ' + !!navigator.serviceWorker.controller : 'not registered';
    } catch (e) { sw = 'error: ' + e.message; }
  }
  let caches_ = 'n/a';
  try { caches_ = (await caches.keys()).join(', ') || '(none)'; } catch (e) {}
  let storage = 'n/a';
  try { const s = await navigator.storage.estimate(); storage = Math.round(s.usage / 1024) + ' KB used of ' + Math.round(s.quota / 1048576) + ' MB'; } catch (e) {}
  const hours = ((Date.now() / 1000 - SCAN_EPOCH) / 3600).toFixed(1);
  el.textContent = [
    '=== TrendScout phone diagnostics ===',
    'Generated:           ' + new Date().toString(),
    'Site build:          ' + BUILD_ID,
    'Snapshot scanned:    ' + SCAN_LABEL + '  (' + hours + ' hours ago)',
    'Page:                ' + location.href,
    'Online:              ' + navigator.onLine,
    'Installed app:       ' + (matchMedia('(display-mode: standalone)').matches || navigator.standalone === true),
    'Service worker:      ' + sw,
    'Caches:              ' + caches_,
    'Last version check: ' + (window.__lastVersionCheck || 'n/a'),
    'Watchlist items on this device: ' + Object.keys(wl).length,
    'Chosen tech mix:     ' + _lsGet(MIX_KEY, DEFAULT_MIX),
    'Storage:             ' + storage,
    'Browser:             ' + navigator.userAgent,
    'Screen:              ' + screen.width + 'x' + screen.height + ' @' + devicePixelRatio + 'x, viewport ' + innerWidth + 'x' + innerHeight,
    '',
    '--- Recent errors (' + errs.length + ') ---',
  ].concat(errs.length ? errs : ['(none)']).concat(['=== end of diagnostics ===']).join('\n');
}

/* ---------- start-up ---------- */
applyMix(_lsGet(MIX_KEY, DEFAULT_MIX));
applyChecks();
renderWatchlist();
renderDiagnostics();
checkStale();
checkVersion();
"""


def sw_js(build_id: str) -> str:
    """Service worker, built on the pattern proven in the HLSA app: the page and data
    are fetched network-first with a throwaway query param (GitHub Pages' CDN ignores
    cache-bypass headers), the cache is only the offline fallback, and version.json is
    never cached."""
    return f"""const CACHE = "trendscout-{build_id}";
function bust(url) {{ return url + (url.indexOf("?") === -1 ? "?" : "&") + "_sw=" + Date.now(); }}
const APP_SHELL = ["./", "./index.html", "./wire.html", "./watchlist.html", "./diagnostics.html",
  "./manifest.webmanifest", "./free.json", "./icons/icon-192.png", "./icons/icon-512.png",
  "./icons/apple-touch-icon.png", "./icons/favicon-32.png"];

self.addEventListener("install", (event) => {{
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(APP_SHELL)).then(() => self.skipWaiting()));
}});

self.addEventListener("activate", (event) => {{
  event.waitUntil(
    // Every app on this github.io address shares one cache store (HLSA included), so only ever
    // clear TrendScout's own older caches.
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k.startsWith("trendscout-") && k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
}});

self.addEventListener("fetch", (event) => {{
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // The update check itself must never come from a cache.
  if (url.pathname.endsWith("version.json")) {{
    event.respondWith(fetch(bust(req.url), {{ cache: "no-store" }}));
    return;
  }}

  const pathname = url.pathname;
  const isFresh = req.mode === "navigate" || pathname.endsWith(".webmanifest") || pathname.endsWith("free.json");
  if (isFresh) {{
    // Network-first so a newly published snapshot shows on the very next open; the cache
    // (stored under the clean URL) is only the offline fallback.
    const key = req.url.split("#")[0].split("?")[0];
    event.respondWith(
      fetch(bust(req.url), {{ cache: "no-store" }})
        .then((response) => {{
          if (response.ok) {{
            const copy = response.clone();
            caches.open(CACHE).then((cache) => cache.put(key, copy));
          }}
          return response;
        }})
        .catch(() => caches.match(key).then((hit) => hit || caches.match("./index.html")))
    );
    return;
  }}

  // Icons: cache-first, refreshed in the background.
  event.respondWith(
    caches.match(req).then((cached) => {{
      const network = fetch(req).then((response) => {{
        if (response.ok) {{
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(req, copy));
        }}
        return response;
      }}).catch(() => cached);
      return cached || network;
    }})
  );
}});
"""


def manifest_json() -> str:
    return json.dumps({
        "name": "TrendScout",
        "short_name": "TrendScout",
        "description": "Personal research aggregator for stocks, crypto and currencies. Informational only - not investment advice.",
        "start_url": "./index.html",
        "scope": "./",
        "display": "standalone",
        "orientation": "any",
        "background_color": "#0f1420",
        "theme_color": "#0f1420",
        "icons": [
            {"src": "icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": "icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": "icons/maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }, indent=2)


def write_icons(out_dir: str) -> None:
    """Draws the app icon (a rising trend line on the dark theme colour) at the sizes
    phones ask for. Drawn large and scaled down so the edges stay smooth."""
    from PIL import Image, ImageDraw

    def draw(size: int, safe: float) -> "Image.Image":
        big = 1024
        img = Image.new("RGB", (big, big), "#0f1420")
        d = ImageDraw.Draw(img)
        # the artwork sits inside the central `safe` fraction (maskable icons get cropped to a circle)
        lo, hi = big * (1 - safe) / 2, big * (1 + safe) / 2
        span = hi - lo
        pts = [(lo + span * x, lo + span * y) for x, y in
               [(0.02, 0.78), (0.24, 0.58), (0.42, 0.68), (0.66, 0.34), (0.98, 0.12)]]
        # soft area under the line
        area = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        ImageDraw.Draw(area).polygon(pts + [(pts[-1][0], hi), (pts[0][0], hi)], fill=(62, 207, 142, 38))
        img = Image.alpha_composite(img.convert("RGBA"), area).convert("RGB")
        d = ImageDraw.Draw(img)
        d.line(pts, fill="#3ecf8e", width=int(big * 0.055), joint="curve")
        r = big * 0.05
        for x, y in (pts[0], pts[-1]):
            d.ellipse((x - r, y - r, x + r, y + r), fill="#3ecf8e")
        return img.resize((size, size), Image.LANCZOS)

    icons = os.path.join(out_dir, "icons")
    os.makedirs(icons, exist_ok=True)
    draw(512, 0.78).save(os.path.join(icons, "icon-512.png"))
    draw(192, 0.78).save(os.path.join(icons, "icon-192.png"))
    draw(512, 0.56).save(os.path.join(icons, "maskable-512.png"))
    draw(180, 0.70).save(os.path.join(icons, "apple-touch-icon.png"))
    draw(32, 0.86).save(os.path.join(icons, "favicon-32.png"))
