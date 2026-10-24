"""SQLite-backed watchlist persistence. Lives next to the app so it survives
between scans and between app restarts."""
import sqlite3
import json
import datetime
import threading

_lock = threading.Lock()


def get_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            item_type TEXT NOT NULL,
            item_id TEXT NOT NULL,
            label TEXT,
            snapshot TEXT,
            added_at TEXT,
            PRIMARY KEY (item_type, item_id)
        )
    """)
    conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    # Scan history: one row per scan, plus one row per item in each section
    # (and the full scored stock universe, as a baseline for later analysis).
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scan_runs (
            scan_id INTEGER PRIMARY KEY AUTOINCREMENT,
            scanned_at TEXT NOT NULL,
            app_version TEXT,
            tech_percent INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scan_items (
            scan_id INTEGER NOT NULL,
            section TEXT NOT NULL,
            rank INTEGER,
            item_id TEXT NOT NULL,
            symbol TEXT, name TEXT, price REAL,
            pct_1d REAL, pct_5d REAL, pct_7d REAL, vol_ratio REAL,
            hot_score REAL, sleeper_score REAL,
            sector TEXT, cap_tier TEXT, mcap_rank REAL, trending INTEGER,
            PRIMARY KEY (scan_id, section, item_id)
        )
    """)
    conn.commit()
    return conn


HISTORY_COLUMNS = ["scan_id", "scanned_at", "app_version", "tech_percent", "section", "rank", "item_id",
                   "symbol", "name", "price", "pct_1d", "pct_5d", "pct_7d", "vol_ratio", "hot_score",
                   "sleeper_score", "sector", "cap_tier", "mcap_rank", "trending"]
_ITEM_COLUMNS = HISTORY_COLUMNS[4:]


def save_scan(conn: sqlite3.Connection, scanned_at: str, app_version: str, tech_percent: int, items: list) -> tuple:
    """Saves one scan and all its items in a single transaction.
    Returns (scan_id, number_of_items)."""
    with _lock:
        try:
            cur = conn.execute(
                "INSERT INTO scan_runs (scanned_at, app_version, tech_percent) VALUES (?, ?, ?)",
                (scanned_at, app_version, tech_percent))
            scan_id = cur.lastrowid
            placeholders = ",".join("?" * (len(_ITEM_COLUMNS) + 1))
            conn.executemany(
                f"INSERT OR REPLACE INTO scan_items (scan_id, {','.join(_ITEM_COLUMNS)}) VALUES ({placeholders})",
                [(scan_id, *[item.get(c) for c in _ITEM_COLUMNS]) for item in items])
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return scan_id, len(items)


def history_summary(conn: sqlite3.Connection):
    """None if nothing has been saved yet, else {'scans', 'first', 'last'}."""
    with _lock:
        n, first, last = conn.execute(
            "SELECT COUNT(*), MIN(scanned_at), MAX(scanned_at) FROM scan_runs").fetchone()
    return {"scans": n, "first": first, "last": last} if n else None


def history_rows(conn: sqlite3.Connection, include_universe: bool = False) -> list:
    """Every saved item joined to its scan, oldest first. The full scored
    universe is left out unless include_universe is set (it's ~900 rows/scan)."""
    where = "" if include_universe else "WHERE i.section != 'universe'"
    cols = ", ".join(["r.scan_id", "r.scanned_at", "r.app_version", "r.tech_percent"] +
                     [f"i.{c}" for c in _ITEM_COLUMNS])
    with _lock:
        return conn.execute(
            f"SELECT {cols} FROM scan_items i JOIN scan_runs r USING (scan_id) {where} "
            "ORDER BY r.scan_id, i.section, i.rank, i.item_id").fetchall()


def get_setting(conn: sqlite3.Connection, key: str, default: str = None):
    with _lock:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str):
    with _lock:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        conn.commit()


def add_item(conn: sqlite3.Connection, item_type: str, item_id: str, label: str, snapshot: dict):
    with _lock:
        conn.execute(
            "INSERT OR REPLACE INTO watchlist (item_type, item_id, label, snapshot, added_at) "
            "VALUES (?, ?, ?, ?, COALESCE((SELECT added_at FROM watchlist WHERE item_type=? AND item_id=?), ?))",
            (item_type, item_id, label, json.dumps(snapshot), item_type, item_id,
             datetime.datetime.now().isoformat()),
        )
        conn.commit()


def remove_item(conn: sqlite3.Connection, item_type: str, item_id: str):
    with _lock:
        conn.execute("DELETE FROM watchlist WHERE item_type=? AND item_id=?", (item_type, item_id))
        conn.commit()


def list_items(conn: sqlite3.Connection) -> list:
    with _lock:
        rows = conn.execute(
            "SELECT item_type, item_id, label, snapshot, added_at FROM watchlist ORDER BY added_at DESC"
        ).fetchall()
    return [
        {"type": r[0], "id": r[1], "label": r[2], "snapshot": json.loads(r[3]), "added_at": r[4]}
        for r in rows
    ]


def watchlist_count(conn: sqlite3.Connection) -> int:
    with _lock:
        return conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0]


def watchlisted_keys(conn: sqlite3.Connection) -> set:
    with _lock:
        rows = conn.execute("SELECT item_type, item_id FROM watchlist").fetchall()
    return {(r[0], r[1]) for r in rows}
