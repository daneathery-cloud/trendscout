"""Builds the copy-and-paste diagnostics report. It lists versions, where the
data lives, item counts and the recent log (which notes tickers added to or
removed from the watchlist)."""
import datetime as dt
import os
import platform
import sqlite3
import sys

import applog
import paths
import store
from version import VERSION


def _db_counts(path: str) -> str:
    """Read-only look at a database file: size, watchlist items, saved scans."""
    if not os.path.exists(path):
        return "not present"
    try:
        size = os.path.getsize(path)
        modified = dt.datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")
        conn = sqlite3.connect("file:" + path.replace("\\", "/") + "?mode=ro", uri=True)
        try:
            items = conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0]
            try:
                scans = conn.execute("SELECT COUNT(*) FROM scan_runs").fetchone()[0]
            except sqlite3.Error:
                scans = "n/a (older format)"
        finally:
            conn.close()
        return f"{size:,} bytes, modified {modified}, watchlist items: {items}, saved scans: {scans}"
    except Exception as e:
        return f"exists but could not be read ({type(e).__name__}: {e})"


def build_report(conn=None, max_log_lines: int = 150) -> str:
    rt = applog.runtime
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db_path = rt.get("db_path") or os.path.join(paths.data_dir(), paths.DB_NAME)
    last_scan = rt.get("last_scan")
    if last_scan:
        scan_txt = (f"{last_scan.get('finished')} - "
                    f"{'OK' if last_scan.get('ok') else 'FAILED'} in {last_scan.get('seconds', '?')}s. "
                    f"{last_scan.get('summary', '')}")
    else:
        scan_txt = "none since this window was opened"
    live = ""
    if conn is not None:
        try:
            live = (f"watchlist items now: {store.watchlist_count(conn)}, "
                    f"saved scans: {(store.history_summary(conn) or {}).get('scans', 0)}")
        except Exception as e:
            live = f"(could not query: {e})"
    lines = [
        "=== TrendScout diagnostics ===",
        f"Generated:       {now}",
        f"App version:     {VERSION}",
        f"Windows:         {platform.platform()}",
        f"Python:          {platform.python_version()}  (packaged exe: {bool(getattr(sys, 'frozen', False))})",
        f"Program file:    {sys.executable}",
        f"Data folder:     {paths.data_dir()}",
        f"Database:        {db_path}",
        f"  opened how:    {rt.get('db_how', 'unknown')}",
        f"  contents:      {_db_counts(db_path)}",
        f"  right now:     {live}",
        f"Old-style db next to the program (pre-2026-10-21 location): {paths.legacy_db_path()}",
        f"  contents:      {_db_counts(paths.legacy_db_path())}",
        f"Local server:    http://127.0.0.1:{rt.get('port', '?')}/",
        f"Last scan:       {scan_txt}",
        "",
        f"--- Last {max_log_lines} log lines ---",
        applog.tail(paths.log_dir(), max_log_lines) or "(log is empty)",
        "=== end of diagnostics ===",
    ]
    return "\n".join(lines)
