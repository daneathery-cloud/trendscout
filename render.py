"""Renders TrendScout's pages: Scan Report, Watchlist, Headline Wire.
Served live by app_server.py rather than written to a static file, so the
Watchlist checkboxes can persist instantly to store.py."""
import base64
import io
import json
import re
import html as html_lib
import hashlib
import datetime as dt
from urllib.parse import quote

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import config
from version import VERSION

# Phone edition: the same pages written out as a static site (see site_builder.py).
# Off for the desktop app; configure_static() turns it on for a site build.
STATIC = {"on": False, "version_label": "", "scan_label": "", "scan_epoch": 0, "build_id": "", "repo_url": ""}


def configure_static(version_label: str, scan_label: str, scan_epoch: float, build_id: str, repo_url: str = ""):
    STATIC.update(on=True, version_label=version_label, scan_label=scan_label,
                  scan_epoch=scan_epoch, build_id=build_id, repo_url=repo_url)

CSS = """
:root{
  --bg:#0f1420; --panel:#161d2e; --panel-2:#1c2438; --border:#2a3550;
  --text:#e8ecf6; --muted:#8b95ad; --green:#3ecf8e; --red:#ff6b6b;
  --tech:#6c8fff; --nontech:#f2b84b; --accent:#7c9cff;
}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;
     margin:0;padding:0 0 60px;}
.wrap{max-width:1180px;margin:0 auto;padding:0 20px 28px;}
header.top{padding:20px;border-bottom:1px solid var(--border);}
header.top h1{margin:0 0 4px;font-size:26px;}
header.top .meta{color:var(--muted);font-size:13px;}
nav.tabs{display:flex;gap:4px;padding:0 20px;border-bottom:1px solid var(--border);background:var(--panel-2);}
nav.tabs a{color:var(--muted);text-decoration:none;font-size:13.5px;font-weight:600;padding:14px 16px;
           border-bottom:2px solid transparent;}
nav.tabs a.active{color:var(--text);border-bottom-color:var(--accent);}
nav.tabs a:hover{color:var(--text);}
.disclaimer{background:#241a1a;border:1px solid #4a2f2f;color:#f2b8b8;border-radius:8px;
            padding:12px 16px;font-size:12.5px;margin:18px 0;line-height:1.5;}
h2.section{font-size:19px;margin:34px 0 6px;padding-bottom:8px;border-bottom:2px solid var(--border);
           display:flex;align-items:center;gap:10px;}
p.section-sub{color:var(--muted);font-size:13px;margin:0 0 16px;}
.badge{font-size:10.5px;padding:2px 8px;border-radius:20px;font-weight:600;letter-spacing:.3px;}
.badge.tech{background:rgba(108,143,255,.15);color:var(--tech);}
.badge.nontech{background:rgba(242,184,75,.15);color:var(--nontech);}
.badge.penny{background:rgba(255,107,107,.15);color:var(--red);}
.note{background:var(--panel);border:1px solid var(--border);color:var(--muted);border-radius:8px;
      padding:10px 14px;font-size:12.5px;margin:0 0 14px;line-height:1.5;}
.note b{color:var(--text);}
.free-btn{display:inline-block;margin:6px 0 0 6px;background:none;border:1px solid var(--border);
          color:var(--muted);font-size:10.5px;padding:2px 9px;border-radius:20px;cursor:pointer;}
.free-btn:hover{border-color:var(--accent);color:var(--accent);}
.free-btn.mini{margin:0 0 0 4px;padding:0 5px;font-size:11px;line-height:1.4;flex-shrink:0;}
.card .news .news-row{display:flex;align-items:flex-start;margin-bottom:4px;}
.card .news .news-row a{margin-bottom:0;flex:1;}
.free-pop{width:340px;max-width:calc(100vw - 16px);padding:10px 12px;font-size:12px;color:var(--muted);line-height:1.45;}
.free-pop .fp-head{font-weight:600;color:var(--text);margin-bottom:6px;}
.free-pop a.hit{display:block;color:var(--accent);text-decoration:none;padding:5px 0;border-top:1px solid var(--border);}
.free-pop a.hit:hover{text-decoration:underline;}
.free-pop a.hit .fs{display:block;color:var(--muted);font-size:10.5px;text-transform:uppercase;letter-spacing:.3px;}
.free-pop .fp-foot{margin-top:6px;padding-top:6px;border-top:1px solid var(--border);}
.free-pop .fp-foot a{color:var(--accent);text-decoration:none;}
.free-pop .fp-note{font-size:10.5px;margin-top:4px;}
pre.diag{background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:14px;font-size:11.5px;
         line-height:1.5;overflow:auto;white-space:pre-wrap;word-break:break-word;color:var(--muted);max-height:70vh;}
.meta a{color:inherit;}
.history-bar{margin:34px 0 0;padding:10px 14px;border:1px dashed var(--border);border-radius:8px;
             font-size:12.5px;color:var(--muted);line-height:1.6;}
.history-bar b{color:var(--text);}
.history-bar a{color:var(--accent);text-decoration:none;}
.history-bar a:hover{text-decoration:underline;}
.spark svg{display:block;width:100%;height:55px;}
.mix-variant{display:none;}
.mix-variant.active{display:block;}
.banner{border-radius:8px;padding:10px 14px;margin:14px 0 0;font-size:12.5px;line-height:1.45;display:none;}
.banner.show{display:block;}
.banner.warn{background:#2a2316;border:1px solid #5a4a22;color:#f2d38a;}
.banner.info{background:#16233a;border:1px solid #2f4a7a;color:#b9d0ff;}
.banner button{margin-left:8px;background:var(--accent);color:#0f1420;border:none;border-radius:14px;
               padding:4px 13px;font-weight:700;font-size:12px;cursor:pointer;}
header.top .hdr-row{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;}
.refresh-btn{background:var(--panel);border:1px solid var(--border);color:var(--text);border-radius:18px;
             padding:7px 13px;font-size:12.5px;cursor:pointer;white-space:nowrap;}
.refresh-btn:hover{border-color:var(--accent);}
@media (pointer: coarse), (max-width:640px){
  /* finger-sized tap targets on any touch screen (tablet or phone) */
  .card{padding-bottom:56px;}
  .news-item{padding-right:14px;padding-bottom:46px;}
  .track{bottom:3px;right:3px;width:42px;height:42px;display:flex;align-items:center;justify-content:center;}
  .track input{width:100%;height:100%;left:0;top:0;}
  .track .mark{width:21px;height:21px;}
  .track input:checked + .mark::after{line-height:20px;font-size:13px;}
  .share-btn{bottom:3px;right:46px;width:42px;height:42px;}
  .share-btn svg{width:18px;height:18px;}
  .share-btn.page{width:auto;height:auto;}
  .free-btn{padding:6px 12px;font-size:12px;}
  .free-btn.mini{padding:4px 9px;font-size:14px;}
  .mix-ctl button{padding:6px 11px;font-size:12px;}
  .wire-filters button{padding:7px 13px;font-size:12.5px;}
  .remove-btn{padding:6px 12px;}
  .card .news a{font-size:12.5px;}
  table.fx td,table.fx th{padding:8px 6px;}
}
@media (max-width:640px){
  header.top{padding:14px 14px 12px;}
  header.top h1{font-size:19px;}
  nav.tabs{padding:0 4px;overflow-x:auto;}
  nav.tabs a{padding:12px 11px;font-size:13px;white-space:nowrap;}
  .wrap{padding:0 14px 24px;}
  h2.section{font-size:17px;flex-wrap:wrap;margin-top:28px;}
  .grid{grid-template-columns:1fr;}
  .mix-ctl{margin-left:0;width:100%;}
  table.fx{font-size:12.5px;}
  .page-actions{flex-direction:column;}
}
.badge.trending{background:rgba(62,207,142,.15);color:var(--green);}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:12px;}
.card{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:14px 16px;
      position:relative;}
.card .row1{display:flex;justify-content:space-between;align-items:baseline;padding-right:22px;}
.card .sym{font-size:16px;font-weight:700;}
.card .name{color:var(--muted);font-size:11.5px;margin-top:1px;}
.card .price{font-size:15px;font-weight:600;}
.card .pct{font-size:12.5px;font-weight:600;}
.pct.pos{color:var(--green);} .pct.neg{color:var(--red);}
.card .stats{display:flex;gap:14px;margin-top:8px;font-size:11.5px;color:var(--muted);}
.card .spark{margin-top:8px;}
.card .badges{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap;}
.card .news{margin-top:10px;border-top:1px solid var(--border);padding-top:8px;}
.card .news a{color:var(--accent);text-decoration:none;font-size:11.5px;display:block;margin-bottom:4px;line-height:1.35;}
.card .news a:hover{text-decoration:underline;}
.card .news .src{color:var(--muted);}
table.fx{width:100%;border-collapse:collapse;font-size:13px;}
table.fx th{text-align:left;color:var(--muted);font-weight:600;font-size:11.5px;padding:8px 10px;border-bottom:1px solid var(--border);}
table.fx td{padding:8px 10px;border-bottom:1px solid var(--border);}
.news-list{display:flex;flex-direction:column;gap:10px;}
.news-item{background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:10px 14px;
           position:relative;padding-right:66px;}
.news-item .src{font-size:11px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.4px;}
.news-item a{color:var(--text);text-decoration:none;font-size:14px;display:block;margin-top:3px;}
.news-item a:hover{color:var(--accent);}
.news-item .summary{color:var(--muted);font-size:12.5px;margin-top:4px;line-height:1.4;}
.news-item .secondary-tag{display:inline-block;margin-top:6px;font-size:10.5px;background:rgba(124,156,255,.15);
    color:var(--accent);padding:2px 8px;border-radius:20px;}
footer.foot{color:var(--muted);font-size:11.5px;text-align:center;margin-top:40px;}
/* Watchlist checkbox: discreet, bottom-right */
.track{position:absolute;bottom:8px;right:10px;cursor:pointer;}
.track input{position:absolute;opacity:0;width:20px;height:20px;margin:0;cursor:pointer;}
.track .mark{display:block;width:16px;height:16px;border:1.5px solid var(--border);border-radius:4px;
             background:var(--panel-2);transition:all .15s;}
.track input:checked + .mark{background:var(--accent);border-color:var(--accent);}
.track input:checked + .mark::after{content:"✓";display:block;text-align:center;line-height:15px;
             font-size:11px;color:#0f1420;font-weight:700;}
.track:hover .mark{border-color:var(--accent);}
.empty-state{color:var(--muted);font-size:14px;padding:40px 20px;text-align:center;
             border:1px dashed var(--border);border-radius:10px;}
.wire-filters{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:16px;}
.wire-filters button{background:var(--panel);border:1px solid var(--border);color:var(--muted);
    font-size:11.5px;padding:5px 12px;border-radius:20px;cursor:pointer;}
.wire-filters button.active{background:var(--accent);color:#0f1420;border-color:var(--accent);font-weight:600;}
.remove-btn{background:none;border:1px solid var(--border);color:var(--muted);font-size:11px;
    padding:3px 10px;border-radius:14px;cursor:pointer;margin-top:8px;}
.remove-btn:hover{border-color:var(--red);color:var(--red);}
.watch-meta{color:var(--muted);font-size:10.5px;margin-top:6px;}
/* Share button: sits just left of the watchlist checkbox */
.share-btn{position:absolute;bottom:5px;right:34px;width:24px;height:24px;padding:0;border:none;
           background:none;color:var(--muted);cursor:pointer;border-radius:4px;
           display:flex;align-items:center;justify-content:center;}
.share-btn:hover{color:var(--accent);}
.share-btn svg{width:14px;height:14px;}
.share-btn.page{position:static;width:auto;height:auto;padding:7px 14px;border:1px solid var(--border);
           border-radius:18px;font-size:12.5px;gap:7px;color:var(--text);background:var(--panel);
           white-space:nowrap;flex-shrink:0;}
.share-btn.page:hover{border-color:var(--accent);}
.share-pop{position:absolute;z-index:50;background:var(--panel-2);border:1px solid var(--border);
           border-radius:8px;padding:4px;min-width:190px;box-shadow:0 6px 20px rgba(0,0,0,.45);}
.share-pop button{display:block;width:100%;text-align:left;background:none;border:none;color:var(--text);
           font-size:12.5px;padding:8px 10px;border-radius:5px;cursor:pointer;}
.share-pop button:hover{background:var(--panel);color:var(--accent);}
/* Tech / non-tech mix selector, on the Hot Stocks heading row */
.badge.even{background:rgba(139,149,173,.15);color:var(--muted);}
.mix-ctl{margin-left:auto;display:flex;align-items:center;gap:4px;flex-wrap:wrap;
         font-size:11px;font-weight:500;color:var(--muted);}
.mix-ctl span{margin-right:4px;}
.mix-ctl button{background:var(--panel);border:1px solid var(--border);color:var(--muted);font-size:11px;
         padding:3px 9px;border-radius:14px;cursor:pointer;}
.mix-ctl button:hover{border-color:var(--accent);color:var(--text);}
.mix-ctl button.active{background:var(--accent);color:#0f1420;border-color:var(--accent);font-weight:700;}
.mix-ctl.busy{opacity:.6;pointer-events:none;}
.page-actions{display:flex;justify-content:space-between;align-items:flex-start;gap:14px;margin:6px 0 4px;}
.page-actions p{margin:0;}
.export-meta{color:var(--muted);font-size:12.5px;margin-top:4px;}
"""

JS = """
function downloadReport(url) { window.location.href = url; }
function toggleWatch(el, removeOnUncheck) {
  const type = el.dataset.type, id = el.dataset.id, label = el.dataset.label;
  let snapshot = {};
  try { snapshot = JSON.parse(el.dataset.snapshot); } catch(e) {}
  const action = el.checked ? 'add' : 'remove';
  const prevChecked = el.checked;
  fetch('/api/watchlist/toggle', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({action, type, id, label, snapshot})
  }).then(r => {
    if (!r.ok) throw new Error('bad response');
    if (removeOnUncheck && !prevChecked) {
      const card = el.closest('.card, .news-item');
      if (card) { card.style.opacity = '0'; setTimeout(() => card.remove(), 200); }
    }
  }).catch(() => {
    el.checked = !prevChecked;
    alert('Could not update the watchlist. Is TrendScout still running?');
  });
}
let _sharePop = null;
function closeSharePop() { if (_sharePop) { _sharePop.remove(); _sharePop = null; } }
document.addEventListener('click', () => { closeSharePop(); closeFreePop(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') { closeSharePop(); closeFreePop(); } });
async function copyText(t) {
  try { await navigator.clipboard.writeText(t); return true; }
  catch (e) {
    const ta = document.createElement('textarea');
    ta.value = t; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    let ok = false; try { ok = document.execCommand('copy'); } catch (_) {}
    ta.remove(); return ok;
  }
}
function openShare(btn, ev) {
  ev.stopPropagation(); ev.preventDefault();
  closeFreePop();
  const reopen = !(_sharePop && _sharePop._for === btn);
  closeSharePop();
  if (!reopen) return;
  const title = btn.dataset.title || 'TrendScout', text = btn.dataset.text || '';
  const pop = document.createElement('div');
  pop.className = 'share-pop'; pop._for = btn;
  pop.addEventListener('click', e => e.stopPropagation());
  const add = (label, fn) => {
    const b = document.createElement('button');
    b.type = 'button'; b.textContent = label; b.onclick = () => fn(b); pop.appendChild(b);
  };
  add('\\u2709  Email', () => {
    let body = text;
    if (body.length > 1800) body = body.slice(0, 1800) + '\\n...(shortened - use Download report for the full version)';
    const a = document.createElement('a');
    a.href = 'mailto:?subject=' + encodeURIComponent(title) + '&body=' + encodeURIComponent(body);
    a.click(); closeSharePop();
  });
  add('\\u29C9  Copy text', async (b) => {
    const ok = await copyText(text);
    b.textContent = ok ? '\\u2713  Copied' : 'Copy failed';
    setTimeout(closeSharePop, 900);
  });
  if (btn.dataset.download) {
    add('\\u2B07  Download report (HTML)', () => { downloadReport(btn.dataset.download); closeSharePop(); });
  }
  if (navigator.share) {
    add('\\u2197  More apps...', () => { navigator.share({title, text}).catch(() => {}); closeSharePop(); });
  }
  document.body.appendChild(pop);
  const r = btn.getBoundingClientRect(), vw = document.documentElement.clientWidth;
  pop.style.top = (window.scrollY + r.bottom + 6) + 'px';
  pop.style.left = Math.max(8, Math.min(window.scrollX + r.right - 190, window.scrollX + vw - 200)) + 'px';
  _sharePop = pop;
}
function setMix(percent, btn) {
  const ctl = btn.closest('.mix-ctl');
  if (btn.classList.contains('active')) return;
  const label = ctl.querySelector('span');
  ctl.classList.add('busy'); label.textContent = 'Updating...';
  fetch('/api/settings/tech_split', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({percent})
  }).then(r => {
      if (!r.ok) throw new Error('bad response');
      try { sessionStorage.setItem('ts_scroll', String(window.scrollY)); } catch (e) {}
      location.reload();
    })
    .catch(() => {
      ctl.classList.remove('busy'); label.textContent = 'Tech / Non-tech';
      alert('Could not change the mix. Is TrendScout still running?');
    });
}
try {
  const y = sessionStorage.getItem('ts_scroll');
  if (y !== null) { sessionStorage.removeItem('ts_scroll'); window.scrollTo(0, parseInt(y, 10) || 0); }
} catch (e) {}
let _freePop = null;
function closeFreePop() { if (_freePop) { _freePop.remove(); _freePop = null; } }
function _place(pop, btn, width) {
  const r = btn.getBoundingClientRect(), vw = document.documentElement.clientWidth;
  pop.style.top = (window.scrollY + r.bottom + 6) + 'px';
  pop.style.left = Math.max(8, Math.min(window.scrollX + r.left, window.scrollX + vw - width - 8)) + 'px';
}
function _el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}
async function getFreeData(title) {
  const resp = await fetch('/api/free_versions?title=' + encodeURIComponent(title));
  if (!resp.ok) throw new Error('bad response');
  return await resp.json();
}
async function openFree(btn, ev) {
  ev.stopPropagation(); ev.preventDefault();
  closeSharePop();
  const same = _freePop && _freePop._for === btn;
  closeFreePop();
  if (same) return;
  const pop = _el('div', 'share-pop free-pop', 'Searching other outlets...');
  pop._for = btn;
  pop.addEventListener('click', e => e.stopPropagation());
  document.body.appendChild(pop);
  _place(pop, btn, 340);
  _freePop = pop;
  try {
    const d = await getFreeData(btn.dataset.title || '');
    if (_freePop !== pop) return;
    pop.textContent = '';
    pop.appendChild(_el('div', 'fp-head', 'Same story, other outlets'));
    if (d.matches && d.matches.length) {
      d.matches.forEach(m => {
        const a = _el('a', 'hit');
        a.href = m.link; a.target = '_blank'; a.rel = 'noopener';
        a.appendChild(_el('span', 'fs', m.source));
        a.appendChild(document.createTextNode(m.title));
        pop.appendChild(a);
      });
    } else if (d.notPrepared) {
      pop.appendChild(_el('div', '', 'This story was not searched in advance. The Google News link below searches other outlets for it.'));
    } else if (d.error) {
      pop.appendChild(_el('div', '', 'The search had trouble just now (' + d.error + '). The Google News link below still works.'));
    } else {
      pop.appendChild(_el('div', '', 'No close matches from other outlets in the last few days.'));
    }
    const foot = _el('div', 'fp-foot');
    const g = _el('a', '', 'Search Google News for \u201c' + (d.keywords || '').split(' ').slice(0, 3).join(' ') + '\u201d \u2197');
    g.href = d.search_url; g.target = '_blank'; g.rel = 'noopener';
    foot.appendChild(g);
    foot.appendChild(_el('div', 'fp-note', 'Matches are by keywords, so check the headline. Some outlets still limit free articles.'));
    pop.appendChild(foot);
    _place(pop, btn, 340);
  } catch (e) {
    if (_freePop === pop) pop.textContent = 'Could not search right now. Is TrendScout still running?';
  }
}
async function copyDiag(btn) {
  const ok = await copyText(document.getElementById('diag').textContent);
  btn.querySelector('span').textContent = ok ? 'Copied - paste it into your chat' : 'Copy failed - select the text manually';
}
function filterWire(source, btn) {
  document.querySelectorAll('.wire-filters button').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('.news-item[data-source]').forEach(item => {
    item.style.display = (source === 'all' || item.dataset.source === source) ? '' : 'none';
  });
}
"""


def _sparkline_b64(values: list, positive: bool) -> str:
    if not values or len(values) < 2:
        return ""
    color = "#3ecf8e" if positive else "#ff6b6b"
    fig, ax = plt.subplots(figsize=(2.4, 0.6), dpi=110)
    ax.plot(values, color=color, linewidth=1.8)
    ax.fill_between(range(len(values)), values, min(values), color=color, alpha=0.12)
    ax.axis("off")
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", transparent=True)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _spark_html(values: list, positive: bool) -> str:
    """The small trend line on a card: an inline SVG on the phone edition (crisp and
    tiny), the matplotlib PNG on the desktop."""
    if not STATIC["on"]:
        return f'<img src="data:image/png;base64,{_sparkline_b64(values, positive)}" width="220" height="55">'
    if not values or len(values) < 2:
        return ""
    color = "#3ecf8e" if positive else "#ff6b6b"
    w, h, pad = 220.0, 55.0, 3.0
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    pts = [(i * w / (len(values) - 1), h - pad - (v - lo) / span * (h - 2 * pad)) for i, v in enumerate(values)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"0,{h:.0f} {line} {w:.0f},{h:.0f}"
    return (f'<svg viewBox="0 0 {w:.0f} {h:.0f}" width="220" height="55" preserveAspectRatio="none" '
            f'style="max-width:100%"><polygon points="{area}" fill="{color}" fill-opacity="0.12"/>'
            f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="1.8" vector-effect="non-scaling-stroke" '
            f'stroke-linejoin="round" stroke-linecap="round"/></svg>')


def _pct_class(v: float) -> str:
    return "pos" if v >= 0 else "neg"


def _esc(s) -> str:
    return html_lib.escape(str(s)) if s is not None else ""


def news_id(link: str) -> str:
    return hashlib.md5((link or "").encode("utf-8")).hexdigest()[:16]


def _format_crypto_price(price: float) -> str:
    if price >= 1:
        return f"${price:,.2f}"
    if price >= 0.01:
        return f"${price:,.4f}"
    if price >= 0.0001:
        return f"${price:.6f}"
    return f"${price:.8f}"


_PAYWALL_SOURCE_RE = re.compile(
    "|".join(re.escape(m) for m in config.PAYWALLED_OUTLET_MARKERS + config.FREE_SEARCH_EXCLUDED_OUTLETS),
    re.IGNORECASE)


def _is_paywalled_source(source) -> bool:
    return bool(source) and bool(_PAYWALL_SOURCE_RE.search(str(source)))


def _free_button(title: str, mini: bool = False) -> str:
    label = "🔓" if mini else "🔓 Find free versions"
    tip = "Look for this story at outlets without a paywall"
    return (f'<button type="button" class="free-btn{" mini" if mini else ""}" title="{tip}" '
            f'data-title="{_attr(title)}" onclick="openFree(this, event)">{label}</button>')


def _card_news_html(news_items: list, interactive: bool = True) -> str:
    """The story links under a stock/crypto card; paywalled outlets get a small
    find-free-versions button beside the link."""
    if not news_items:
        return ""
    rows = []
    for n in news_items:
        btn = _free_button(n["title"], mini=True) if interactive and _is_paywalled_source(n.get("source")) else ""
        rows.append(
            f'<div class="news-row"><a href="{_esc(n["link"])}" target="_blank" rel="noopener">'
            f'{_esc(n["title"])} <span class="src">— {_esc(n["source"])}</span></a>{btn}</div>')
    return f'<div class="news">{"".join(rows)}</div>'


def _checkbox(item_type: str, item_id: str, label: str, snapshot: dict, checked: bool,
              remove_on_uncheck: bool = False) -> str:
    snap_json = html_lib.escape(json.dumps(snapshot), quote=True)
    checked_attr = "checked" if checked else ""
    remove_flag = "true" if remove_on_uncheck else "false"
    # The phone edition saves the card's own HTML instead of a data snapshot.
    snap_attr = "" if STATIC["on"] else f' data-snapshot="{snap_json}"'
    return f"""<label class="track" title="Track in Watchlist">
      <input type="checkbox" {checked_attr}
        data-type="{_esc(item_type)}" data-id="{_esc(item_id)}" data-label="{_esc(label)}"{snap_attr}
        onchange="toggleWatch(this, {remove_flag})">
      <span class="mark"></span>
    </label>"""


_SHARE_ICON = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
               'stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"/>'
               '<circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/>'
               '<line x1="8.6" y1="13.5" x2="15.4" y2="17.5"/><line x1="15.4" y1="6.5" x2="8.6" y2="10.5"/></svg>')

SHARE_FOOTER = "Shared from TrendScout - informational only, not investment advice."


def _attr(s: str) -> str:
    """Escape for an HTML attribute value, keeping line breaks intact."""
    return html_lib.escape(s or "", quote=True).replace("\n", "&#10;")


def _share_button(title: str, text: str, download: str = "", page_label: str = "") -> str:
    dl = f' data-download="{_attr(download)}"' if download else ""
    label = f"{_SHARE_ICON}<span>{_esc(page_label)}</span>" if page_label else _SHARE_ICON
    cls = "share-btn page" if page_label else "share-btn"
    return (f'<button type="button" class="{cls}" title="Share" data-title="{_attr(title)}" '
            f'data-text="{_attr(text)}"{dl} onclick="openShare(this, event)">{label}</button>')


def _as_of_line(snap: dict) -> str:
    return f"TrendScout snapshot: {snap['as_of']}" if snap.get("as_of") else ""


def _format_stock_price(price: float) -> str:
    # Penny stocks can sit well under a cent; don't round that away.
    return f"${price:,.2f}" if price >= 1 else _format_crypto_price(price)


def stock_share(snap: dict) -> tuple:
    lines = [f"{snap['symbol']} - {snap['Security']} ({snap['SectorBucket']})",
             f"{_format_stock_price(snap['last_close'])} ({snap['pct_1d']:+.2f}% 1d, {snap['pct_5d']:+.2f}% 5d), "
             f"volume {snap['vol_ratio']:.2f}x its 20-day average"]
    if _as_of_line(snap):
        lines.append(_as_of_line(snap))
    lines.append(f"https://finance.yahoo.com/quote/{quote(snap['symbol'])}")
    headlines = [f"  - {n['title']} ({n['source']})" for n in snap.get("news", [])[:2]]
    if headlines:
        lines += ["", "Recent headlines:"] + headlines
    lines += ["", SHARE_FOOTER]
    return f"{snap['symbol']} - {snap['Security']} (TrendScout)", "\n".join(lines)


def crypto_share(snap: dict) -> tuple:
    rank = snap.get("market_cap_rank")
    lines = [f"{snap['symbol_disp']} - {snap['name']}",
             f"{_format_crypto_price(snap['current_price'])} ({snap['pct_1d']:+.2f}% 24h, "
             f"{snap['pct_5d']:+.2f}% 7d)" + (f", market-cap rank #{int(rank)}" if rank else "")]
    if _as_of_line(snap):
        lines.append(_as_of_line(snap))
    lines.append(f"https://www.coingecko.com/en/coins/{quote(snap['id'])}")
    headlines = [f"  - {n['title']} ({n['source']})" for n in snap.get("news", [])[:2]]
    if headlines:
        lines += ["", "Recent headlines:"] + headlines
    lines += ["", SHARE_FOOTER]
    return f"{snap['symbol_disp']} - {snap['name']} (TrendScout)", "\n".join(lines)


def fx_share(snap: dict) -> tuple:
    lines = [f"{snap['pair']}: {snap['last']:.4f} ({snap['pct_1d']:+.2f}% 1d, {snap['pct_5d']:+.2f}% 5d)"]
    if _as_of_line(snap):
        lines.append(_as_of_line(snap))
    lines.append(f"https://finance.yahoo.com/quote/{quote(snap['ticker'], safe='=')}")
    lines += ["", SHARE_FOOTER]
    return f"{snap['pair']} (TrendScout)", "\n".join(lines)


def news_share(snap: dict) -> tuple:
    lines = [snap["title"], snap["source"], snap["link"], "", "Shared from TrendScout."]
    return snap["title"], "\n".join(lines)


def watchlist_share(items: list, stamp: str) -> tuple:
    """Plain-text version of the whole watchlist, for email/copy."""
    by_type = {"stock": [], "crypto": [], "fx": [], "news": []}
    for it in items:
        by_type.setdefault(it["type"], []).append(it["snapshot"])
    lines = [f"TrendScout Watchlist - {stamp}",
             "Prices are snapshots from the scan noted on each line.", ""]
    if by_type["stock"]:
        lines.append("STOCKS")
        for s in by_type["stock"]:
            lines.append(f"- {s['symbol']} ({s['Security']}): ${s['last_close']:.2f}, "
                         f"{s['pct_1d']:+.2f}% 1d, {s['pct_5d']:+.2f}% 5d [{s.get('as_of', '')}] "
                         f"https://finance.yahoo.com/quote/{quote(s['symbol'])}")
        lines.append("")
    if by_type["crypto"]:
        lines.append("CRYPTO")
        for s in by_type["crypto"]:
            lines.append(f"- {s['symbol_disp']} ({s['name']}): {_format_crypto_price(s['current_price'])}, "
                         f"{s['pct_1d']:+.2f}% 24h, {s['pct_5d']:+.2f}% 7d [{s.get('as_of', '')}] "
                         f"https://www.coingecko.com/en/coins/{quote(s['id'])}")
        lines.append("")
    if by_type["fx"]:
        lines.append("CURRENCIES")
        for s in by_type["fx"]:
            lines.append(f"- {s['pair']}: {s['last']:.4f}, {s['pct_1d']:+.2f}% 1d, "
                         f"{s['pct_5d']:+.2f}% 5d [{s.get('as_of', '')}]")
        lines.append("")
    if by_type["news"]:
        lines.append("STORIES")
        for s in by_type["news"]:
            lines += [f"- {s['title']} ({s['source']})", f"  {s['link']}"]
        lines.append("")
    lines.append(SHARE_FOOTER)
    return f"TrendScout Watchlist - {stamp}", "\n".join(lines)


def stock_snapshot(row) -> dict:
    return {
        "symbol": row["symbol"], "Security": row.get("Security", ""),
        "as_of": row.get("as_of", "") or "",
        "SectorBucket": row.get("SectorBucket", "Non-Tech"),
        "last_close": float(row["last_close"]), "pct_1d": float(row["pct_1d"]),
        "pct_5d": float(row["pct_5d"]), "vol_ratio": float(row["vol_ratio"]),
        "in_trending_feed": bool(row.get("in_trending_feed", False)),
        "spark": list(row.get("spark", [])),
        "news": row.get("news", []),
    }


def crypto_snapshot(row) -> dict:
    mcap_rank = row.get("market_cap_rank")
    # Handles both a pandas NaN (from a live scan row) and a plain None
    # (from a JSON round-trip through the watchlist store).
    mcap_rank_clean = float(mcap_rank) if (mcap_rank is not None and mcap_rank == mcap_rank) else None
    return {
        "id": row["id"], "symbol_disp": row["symbol_disp"], "name": row.get("name", ""),
        "as_of": row.get("as_of", "") or "",
        "current_price": float(row["current_price"]), "pct_1d": float(row["pct_1d"]),
        "pct_5d": float(row["pct_5d"]),
        "market_cap_rank": mcap_rank_clean,
        "in_trending_feed": bool(row.get("in_trending_feed", False)),
        "spark": list(row.get("spark", [])),
        "news": row.get("news", []),
    }


def fx_snapshot(row) -> dict:
    return {
        "pair": row["pair"], "ticker": row["ticker"], "last": float(row["last"]),
        "as_of": row.get("as_of", "") or "",
        "pct_1d": float(row["pct_1d"]), "pct_5d": float(row["pct_5d"]),
        "spark": list(row.get("spark", [])),
    }


def news_snapshot(row) -> dict:
    # A per-source batch with no secondary mentions can end up as an
    # all-None pandas column, which silently upcasts to NaN - and NaN is
    # truthy in Python, so it has to be normalized back to None here.
    secondary = row.get("secondary_mention")
    if secondary is not None and secondary != secondary:
        secondary = None
    return {
        "source": row["source"], "title": row["title"], "summary": row.get("summary", ""),
        "link": row.get("link", ""), "is_paywalled_source": bool(row.get("is_paywalled_source", False)),
        "secondary_mention": secondary,
    }


def stock_card(row, watchlisted: set, remove_on_uncheck: bool = False,
               interactive: bool = True, show_asof: bool = False) -> str:
    snapshot = stock_snapshot(row)
    checked = ("stock", row["symbol"]) in watchlisted
    spark_html = _spark_html(snapshot["spark"], snapshot["pct_5d"] >= 0)
    sector = snapshot["SectorBucket"]
    badge_cls = "tech" if sector == "Tech" else ("penny" if sector == "Penny" else "nontech")
    trending_badge = '<span class="badge trending">TRENDING</span>' if snapshot["in_trending_feed"] else ""
    news_items = snapshot.get("news", [])
    news_html = _card_news_html(news_items, interactive)
    controls = ""
    if interactive:
        share_title, share_text = stock_share(snapshot)
        controls = _share_button(share_title, share_text) + _checkbox(
            "stock", row["symbol"], f'{row["symbol"]} — {snapshot["Security"]}',
            snapshot, checked, remove_on_uncheck)
    asof_html = (f'<div class="watch-meta">Snapshot: {_esc(snapshot["as_of"])}</div>'
                 if show_asof and snapshot["as_of"] else "")
    price_fmt = _format_stock_price(snapshot["last_close"])
    return f"""
    <div class="card">
      {controls}
      <div class="row1">
        <div><div class="sym">{_esc(row['symbol'])}</div>
             <div class="name">{_esc(snapshot['Security'])}</div></div>
        <div style="text-align:right"><div class="price">{price_fmt}</div>
             <div class="pct {_pct_class(snapshot['pct_1d'])}">{snapshot['pct_1d']:+.2f}% 1d</div></div>
      </div>
      <div class="stats">
        <span>5d: <b class="{_pct_class(snapshot['pct_5d'])}">{snapshot['pct_5d']:+.2f}%</b></span>
        <span>Vol vs avg: <b>{snapshot['vol_ratio']:.2f}x</b></span>
      </div>
      <div class="spark">{spark_html}</div>
      <div class="badges"><span class="badge {badge_cls}">{sector}</span>{trending_badge}</div>
      {asof_html}
      {news_html}
    </div>"""


def crypto_card(row, watchlisted: set, remove_on_uncheck: bool = False,
                interactive: bool = True, show_asof: bool = False) -> str:
    snapshot = crypto_snapshot(row)
    checked = ("crypto", row["id"]) in watchlisted
    spark_html = _spark_html(snapshot["spark"], snapshot["pct_1d"] >= 0)
    trending_badge = '<span class="badge trending">TRENDING</span>' if snapshot["in_trending_feed"] else ""
    rank = snapshot.get("market_cap_rank")
    rank_txt = f"MCap rank #{int(rank)}" if rank else "Unranked"
    news_items = snapshot.get("news", [])
    news_html = _card_news_html(news_items, interactive)
    price_fmt = _format_crypto_price(snapshot["current_price"])
    controls = ""
    if interactive:
        share_title, share_text = crypto_share(snapshot)
        controls = _share_button(share_title, share_text) + _checkbox(
            "crypto", row["id"], f'{snapshot["symbol_disp"]} — {snapshot["name"]}',
            snapshot, checked, remove_on_uncheck)
    asof_html = (f'<div class="watch-meta">Snapshot: {_esc(snapshot["as_of"])}</div>'
                 if show_asof and snapshot["as_of"] else "")
    return f"""
    <div class="card">
      {controls}
      <div class="row1">
        <div><div class="sym">{_esc(snapshot['symbol_disp'])}</div>
             <div class="name">{_esc(snapshot['name'])}</div></div>
        <div style="text-align:right"><div class="price">{price_fmt}</div>
             <div class="pct {_pct_class(snapshot['pct_1d'])}">{snapshot['pct_1d']:+.2f}% 24h</div></div>
      </div>
      <div class="stats">
        <span>7d: <b class="{_pct_class(snapshot['pct_5d'])}">{snapshot['pct_5d']:+.2f}%</b></span>
        <span>{rank_txt}</span>
      </div>
      <div class="spark">{spark_html}</div>
      <div class="badges">{trending_badge}</div>
      {asof_html}
      {news_html}
    </div>"""


def fx_table_html(snaps: list, watchlisted: set, remove_on_uncheck: bool = False,
                  interactive: bool = True, show_asof: bool = False) -> str:
    rows = []
    for snap in snaps:
        controls_cell = ""
        if interactive:
            share_title, share_text = fx_share(snap)
            controls = _share_button(share_title, share_text) + _checkbox(
                "fx", snap["ticker"], snap["pair"], snap, ("fx", snap["ticker"]) in watchlisted,
                remove_on_uncheck)
            controls_cell = f'<td style="position:relative;width:70px">{controls}</td>'
        asof = (f'<div class="watch-meta">Snapshot: {_esc(snap["as_of"])}</div>'
                if show_asof and snap.get("as_of") else "")
        rows.append(f"""
        <tr>
          <td><b>{_esc(snap['pair'])}</b>{asof}</td>
          <td>{snap['last']:.4f}</td>
          <td class="{_pct_class(snap['pct_1d'])}">{snap['pct_1d']:+.2f}%</td>
          <td class="{_pct_class(snap['pct_5d'])}">{snap['pct_5d']:+.2f}%</td>
          {controls_cell}
        </tr>""")
    last_th = "<th></th>" if interactive else ""
    return f"""<table class="fx"><thead><tr><th>Pair</th><th>Last</th><th>1d</th><th>5d</th>{last_th}</tr></thead>
    <tbody>{''.join(rows)}</tbody></table>"""


def fx_table(df, watchlisted: set) -> str:
    if df is None or df.empty:
        return "<p class='section-sub'>Currency data unavailable this run.</p>"
    return fx_table_html([fx_snapshot(r) for _, r in df.iterrows()], watchlisted)


def news_item_html(row, watchlisted: set, remove_on_uncheck: bool = False, with_source_attr: bool = False,
                   interactive: bool = True) -> str:
    snapshot = news_snapshot(row)
    item_id = news_id(snapshot["link"])
    checked = ("news", item_id) in watchlisted
    tag = ""
    if snapshot["is_paywalled_source"]:
        label = ("Publisher-provided teaser (subscription site)" if snapshot["summary"]
                 else "Headline only (subscription site)")
        tag = f'<span class="secondary-tag">{label}</span>'
    elif snapshot.get("secondary_mention"):
        tag = f'<span class="secondary-tag">References {_esc(snapshot["secondary_mention"])} reporting</span>'
    if interactive and (snapshot["is_paywalled_source"] or _is_paywalled_source(snapshot["source"])):
        tag += _free_button(snapshot["title"])
    controls = ""
    if interactive:
        share_title, share_text = news_share(snapshot)
        controls = _share_button(share_title, share_text) + _checkbox(
            "news", item_id, snapshot["title"], snapshot, checked, remove_on_uncheck)
    source_attr = f' data-source="{_esc(snapshot["source"])}"' if with_source_attr else ""
    return f"""
    <div class="news-item"{source_attr}>
      {controls}
      <div class="src">{_esc(snapshot['source'])}</div>
      <a href="{_esc(snapshot['link'])}" target="_blank" rel="noopener">{_esc(snapshot['title'])}</a>
      <div class="summary">{_esc(snapshot['summary'])}</div>
      {tag}
    </div>"""


def _page_shell(active_tab: str, body_html: str, title_suffix: str = "") -> str:
    if STATIC["on"]:
        return _static_page_shell(active_tab, body_html, title_suffix)
    tabs = [("scan", "/", "📊 Scan Report"), ("watchlist", "/watchlist", "⭐ Watchlist"),
            ("wire", "/wire", "📰 Headline Wire")]
    nav = "".join(
        f'<a href="{path}" class="{"active" if key == active_tab else ""}">{label}</a>'
        for key, path, label in tabs
    )
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>TrendScout{title_suffix}</title>
<style>{CSS}</style></head><body>
<header class="top">
  <h1>📊 TrendScout — Personal Research Aggregator</h1>
  <div class="meta">Informational only — not investment advice. · Version {VERSION} · <a href="/diagnostics">Diagnostics</a></div>
</header>
<nav class="tabs">{nav}</nav>
<div class="wrap">{body_html}</div>
<script>{JS}</script>
</body></html>"""


def _static_page_shell(active_tab: str, body_html: str, title_suffix: str = "") -> str:
    """Phone-edition shell: relative links, PWA tags, refresh button and the banners
    the page script fills in (stale snapshot / newer snapshot available)."""
    import site_assets
    tabs = [("scan", "index.html", "📊 Scan"), ("watchlist", "watchlist.html", "⭐ Watchlist"),
            ("wire", "wire.html", "📰 Wire")]
    nav = "".join(
        f'<a href="{path}" class="{"active" if key == active_tab else ""}">{label}</a>'
        for key, path, label in tabs
    )
    st = STATIC
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>TrendScout{title_suffix}</title>
<meta name="theme-color" content="#0f1420">
<meta name="robots" content="noindex, nofollow">
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" type="image/png" sizes="32x32" href="icons/favicon-32.png">
<link rel="apple-touch-icon" href="icons/apple-touch-icon.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="TrendScout">
<style>{CSS}</style></head><body>
<header class="top">
  <div class="hdr-row">
    <div><h1>📊 TrendScout</h1>
    <div class="meta">Informational only — not investment advice. · {_esc(st["version_label"])} · <a href="diagnostics.html">Diagnostics</a></div></div>
    <button type="button" class="refresh-btn" onclick="refreshNow()" title="Reload the latest snapshot">⟳ Refresh</button>
  </div>
</header>
<nav class="tabs">{nav}</nav>
<div class="wrap">
<div id="stale-banner" class="banner warn"></div>
<div id="update-banner" class="banner info">A newer snapshot is available. <button type="button" onclick="location.reload()">Load it</button></div>
{body_html}
</div>
<script>const BUILD_ID={json.dumps(st["build_id"])}, SCAN_EPOCH={st["scan_epoch"]}, SCAN_LABEL={json.dumps(st["scan_label"])},
  SITE_VERSION={json.dumps(st["version_label"])}, REPO_URL={json.dumps(st["repo_url"])},
  FREE_EXCLUDE={json.dumps(" ".join("-site:" + d for d in config.FREE_SEARCH_EXCLUDED_DOMAINS))};</script>
<script>{JS}</script>
<script>{site_assets.STATIC_JS}</script>
</body></html>"""


def _mix_badge(pct: int) -> str:
    if pct > 50:
        return '<span class="badge tech">Tech-leaning</span>'
    if pct < 50:
        return '<span class="badge nontech">Non-tech-leaning</span>'
    return '<span class="badge even">Balanced</span>'


def _mix_control(pct: int) -> str:
    buttons = "".join(
        f'<button type="button" class="{"active" if opt == pct else ""}" '
        f'onclick="setMix({opt}, this)">{opt}/{100 - opt}</button>'
        for opt in config.TECH_SPLIT_OPTIONS
    )
    return (f'<div class="mix-ctl" title="Tech / non-tech balance of the Hot and Sleeper stock lists">'
            f'<span>Tech / Non-tech</span>{buttons}</div>')


def build_diagnostics_page(report: str) -> str:
    body = f"""
<h2 class="section">🩺 Diagnostics</h2>
<p class="section-sub">If something looks wrong, click Copy and paste the result into your chat with Claude. It lists
the app version, where your data is stored, item counts and the recent log (which notes tickers you added or removed).</p>
<div class="page-actions"><button type="button" class="share-btn page" onclick="copyDiag(this)">{_SHARE_ICON}<span>Copy diagnostics</span></button></div>
<pre class="diag" id="diag">{_esc(report)}</pre>
"""
    return _page_shell("diagnostics", body, title_suffix=" - Diagnostics")


def build_empty_scan_page() -> str:
    body = f"""
    <div class="disclaimer">{_esc(config.DISCLAIMER)}</div>
    <div class="empty-state">No scan yet. Go back to the TrendScout window and click
    "Scan Now" to generate a report.</div>
    """
    return _page_shell("scan", body)


def _mix_trio_html(stocks: dict, tech_pct: int, under50_note: str, watchlisted: set) -> str:
    """Hot Stocks (with the tech/non-tech buttons), Sleeper Stocks and Hot Stocks Under $50:
    the three sections that change with the mix setting."""
    def cards(df):
        if df is None or df.empty:
            return "<p class='section-sub'>No candidates found this run.</p>"
        return "".join(stock_card(r, watchlisted) for _, r in df.iterrows())

    return f"""
<h2 class="section">🔥 Hot Stocks {_mix_badge(tech_pct)}{_mix_control(tech_pct)}</h2>
<p class="section-sub">Ranked by price momentum, volume surge, and live trending-feed activity. Target mix ~{tech_pct}% tech / {100 - tech_pct}% non-tech, for both Hot and Sleeper stocks (change it with the buttons at right). <em>Volume during market hours is paced to a projected full day.</em></p>
<div class="grid">{cards(stocks.get("hot"))}</div>

<h2 class="section">🌱 Sleeper Stocks</h2>
<p class="section-sub">Rising volume and attention signals, before a big price move — mostly mid-cap names not yet in the mainstream spotlight.</p>
<div class="grid">{cards(stocks.get("sleeper"))}</div>

<h2 class="section">💵 Hot Stocks Under ${config.UNDER50_PRICE_MAX:.0f}</h2>
<p class="section-sub">The same momentum, volume and trending ranking as Hot Stocks, limited to S&amp;P 500 / 400 names priced ${config.PENNY_PRICE_MAX:.0f}–${config.UNDER50_PRICE_MAX:.0f} (under ${config.PENNY_PRICE_MAX:.0f} is the Penny section below). Names already shown under Hot or Sleeper above are skipped, so this adds new ones.</p>
<div class="note"><b>Why the Tech / Non-tech buttons don't apply here:</b> {under50_note} This list is ranked by score alone, so expect it to be mostly non-tech. Also, "hot" is relative to this price range — names here are often quieter than the Hot Stocks above.</div>
<div class="grid">{cards(stocks.get("under50"))}</div>
"""


def build_scan_page(data: dict, watchlisted: set, generated_at: dt.datetime = None, variants: dict = None) -> str:
    generated_at = generated_at or dt.datetime.now()
    now_str = generated_at.strftime("%A, %B %d %Y — %I:%M %p")
    tech_pct = data.get("tech_percent", int(round(config.TECH_SPLIT * 100)))

    stocks = data.get("stocks", {})
    crypto = data.get("crypto", {})
    hist = data.get("history_summary")
    history_html = ""
    if hist:
        def _day(ts):
            try:
                return dt.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").strftime("%b %d, %Y")
            except (TypeError, ValueError):
                return str(ts)
        plural = "scan" if hist["scans"] == 1 else "scans"
        history_html = (
            f'<div class="history-bar">Scan history: <b>{hist["scans"]} {plural}</b> saved on this PC, '
            f'{_day(hist["first"])} to {_day(hist["last"])}. '
            f'<a href="/history/export">Download picks (CSV)</a> · '
            f'<a href="/history/export?scope=all">Download with full scored stock list (CSV)</a></div>')
    history_html = data.get("footer_html") or history_html
    info = data.get("under50_info")
    if info and info["total"]:
        count = "None" if info["tech"] == 0 else f"Only {info['tech']}"
        under50_note = (f"{count} of the {info['total']} S&amp;P 500 / 400 stocks priced "
                        f"${config.PENNY_PRICE_MAX:.0f}–${config.UNDER50_PRICE_MAX:.0f} are tech companies, "
                        f"so a tech-heavy target would force weak names in ahead of hotter ones.")
    else:
        under50_note = ("Few stocks in this price range are tech companies, so a tech-heavy target "
                        "would force weak names in ahead of hotter ones.")
    if variants:
        # Phone edition: every mix is embedded; the page script shows the chosen one.
        mix_sections = "".join(
            f'<div class="mix-variant{" active" if pct == tech_pct else ""}" data-mix="{pct}">'
            f'{_mix_trio_html(v, pct, under50_note, watchlisted)}</div>'
            for pct, v in variants.items())
    else:
        mix_sections = _mix_trio_html(stocks, tech_pct, under50_note, watchlisted)
    hot_penny_stocks = stocks.get("penny")
    hot_crypto = crypto.get("hot")
    sleeper_crypto = crypto.get("sleeper")

    def cards(df, builder):
        if df is None or df.empty:
            return "<p class='section-sub'>No candidates found this run.</p>"
        return "".join(builder(r, watchlisted) for _, r in df.iterrows())

    digest_df = data.get("digest")
    if digest_df is not None and not digest_df.empty:
        digest_html = f'<div class="news-list">{"".join(news_item_html(r, watchlisted) for _, r in digest_df.iterrows())}</div>'
    else:
        digest_html = "<p class='section-sub'>No news items retrieved this run.</p>"

    body = f"""
<div class="meta" style="margin:18px 0 0;color:var(--muted);font-size:13px;">
  Generated {now_str} · Sources: Yahoo Finance, CoinGecko, StockTwits, and public headlines from WSJ, Reuters, Barron's, MarketWatch, CNBC, CoinDesk and others
</div>
<div class="disclaimer">{_esc(config.DISCLAIMER)}</div>

{mix_sections}

<h2 class="section">🪙 Hot Penny Stocks <span class="badge penny">High Risk</span></h2>
<p class="section-sub">Momentum and volume surge among stocks trading under ${config.PENNY_PRICE_MAX:.0f}, pulled from Yahoo's small-cap and most-active screeners rather than the full US-listed universe — so this is a sample of what's moving, not exhaustive.</p>
<div class="disclaimer">Penny stocks carry sharply higher risk than the names above: thin trading volume, wide bid-ask spreads, and a long history of pump-and-dump schemes. This list is not a recommendation to trade any of them — treat it strictly as a starting point for your own research.</div>
<div class="grid">{cards(hot_penny_stocks, stock_card)}</div>

<h2 class="section">🔥 Hot Crypto</h2>
<p class="section-sub">CoinGecko trending feed + volume/market-cap surge among widely tracked coins.</p>
<div class="grid">{cards(hot_crypto, crypto_card)}</div>

<h2 class="section">🌱 Sleeper Crypto</h2>
<p class="section-sub">Coins outside the top 100 by market cap showing unusual volume relative to their size.</p>
<div class="grid">{cards(sleeper_crypto, crypto_card)}</div>

<h2 class="section">💱 Currency Movers</h2>
<p class="section-sub">Major FX pairs ranked by 5-day move.</p>
{fx_table(data.get("forex"), watchlisted)}

<h2 class="section">📰 News Digest</h2>
<p class="section-sub">The lead headlines from each outlet, taking turns (max 3 per outlet), in each outlet's own front-page order — not ranked by web traffic or popularity. See the Headline Wire tab for the full pool.</p>
{digest_html}

{history_html}
<footer class="foot">{_esc(config.DISCLAIMER)}</footer>
"""
    return _page_shell("scan", body)


def _fmt_saved(added_iso: str) -> str:
    try:
        return dt.datetime.fromisoformat(added_iso).strftime("%b %d, %Y %I:%M %p")
    except Exception:
        return ""


def _normalize_watchlist_items(items: list) -> None:
    """Older saved items have no scan timestamp; fall back to when they were saved."""
    for it in items:
        snap = dict(it["snapshot"])
        if it["type"] != "news" and not snap.get("as_of"):
            saved = _fmt_saved(it["added_at"])
            snap["as_of"] = f"saved {saved}" if saved else ""
        it["snapshot"] = snap


def _watchlist_sections(items: list, interactive: bool) -> str:
    watchlisted = {(it["type"], it["id"]) for it in items}
    sections = {"stock": [], "crypto": [], "fx": [], "news": []}
    for it in items:
        sections.setdefault(it["type"], []).append(it)

    parts = []
    if sections["stock"]:
        parts.append('<h2 class="section">⭐ Stocks</h2><div class="grid">' + "".join(
            stock_card(it["snapshot"], watchlisted, remove_on_uncheck=True,
                       interactive=interactive, show_asof=True) for it in sections["stock"]) + '</div>')
    if sections["crypto"]:
        parts.append('<h2 class="section">⭐ Crypto</h2><div class="grid">' + "".join(
            crypto_card(it["snapshot"], watchlisted, remove_on_uncheck=True,
                        interactive=interactive, show_asof=True) for it in sections["crypto"]) + '</div>')
    if sections["fx"]:
        parts.append('<h2 class="section">⭐ Currencies</h2>' + fx_table_html(
            [it["snapshot"] for it in sections["fx"]], watchlisted, remove_on_uncheck=True,
            interactive=interactive, show_asof=True))
    if sections["news"]:
        parts.append('<h2 class="section">⭐ Stories</h2><div class="news-list">' + "".join(
            news_item_html(it["snapshot"], watchlisted, remove_on_uncheck=True, interactive=interactive)
            for it in sections["news"]) + '</div>')
    return "".join(parts)


def build_watchlist_page(items: list) -> str:
    if not items:
        body = """
        <div class="disclaimer">{}</div>
        <div class="empty-state">Nothing on your watchlist yet. Check the small box in the bottom-right
        corner of any stock, coin, currency, or headline on the Scan Report or Headline Wire tabs to save it here.</div>
        """.format(_esc(config.DISCLAIMER))
        return _page_shell("watchlist", body)

    _normalize_watchlist_items(items)
    stamp = dt.datetime.now().strftime("%b %d, %Y")
    share_title, share_text = watchlist_share(items, stamp)
    share_btn = _share_button(share_title, share_text, download="/watchlist/export",
                              page_label="Share watchlist")
    body = f"""
<div class="disclaimer">{_esc(config.DISCLAIMER)}</div>
<div class="page-actions">
  <p class="section-sub">Saved items stay here until you uncheck them — independent of what the next scan turns up.
  Uncheck the box to remove an item. Prices are snapshots from the scan noted on each item.</p>
  {share_btn}
</div>
{_watchlist_sections(items, interactive=True)}
"""
    return _page_shell("watchlist", body)


def build_watchlist_export(items: list) -> str:
    """Self-contained, non-interactive copy of the watchlist, meant to be
    emailed as a file, opened by a colleague, or printed to PDF."""
    _normalize_watchlist_items(items)
    now_str = dt.datetime.now().strftime("%A, %B %d %Y — %I:%M %p")
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>TrendScout Watchlist Report</title>
<style>{CSS}</style></head><body>
<header class="top">
  <h1>⭐ TrendScout — Watchlist Report</h1>
  <div class="export-meta">Generated {now_str} · TrendScout version {VERSION}</div>
</header>
<div class="wrap">
<div class="disclaimer">{_esc(config.DISCLAIMER)}</div>
<p class="section-sub">Prices are snapshots from the scan date noted on each item, not live quotes.</p>
{_watchlist_sections(items, interactive=False)}
<footer class="foot">{_esc(SHARE_FOOTER)}</footer>
</div></body></html>"""


def build_wire_page(wire_df, watchlisted: set) -> str:
    if wire_df is None or wire_df.empty:
        body = f"""<div class="disclaimer">{_esc(config.DISCLAIMER)}</div>
        <div class="empty-state">No headlines retrieved this run.</div>"""
        return _page_shell("wire", body)

    sources = sorted(wire_df["source"].unique().tolist())
    # Outlet names go in a data attribute, not a JS string: "Barron's" has an apostrophe.
    filter_btns = '<button class="active" data-source="all" onclick="filterWire(this.dataset.source, this)">All</button>' + "".join(
        f'<button data-source="{_esc(s)}" onclick="filterWire(this.dataset.source, this)">{_esc(s)}</button>'
        for s in sources
    )
    items_html = "".join(
        news_item_html(r, watchlisted, with_source_attr=True) for _, r in wire_df.iterrows()
    )
    body = f"""
<div class="disclaimer">{_esc(config.DISCLAIMER)}</div>
<h2 class="section">📰 Headline Wire</h2>
<p class="section-sub">The full pool of headlines from this scan across every source, in each outlet's own order — filter by outlet, check the box to save one to your Watchlist, or use the share icon to send it to a colleague.</p>
<div class="wire-filters">{filter_btns}</div>
<div class="news-list">{items_html}</div>
"""
    return _page_shell("wire", body)
