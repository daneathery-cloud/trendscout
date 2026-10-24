"""Where TrendScout keeps its data.

The watchlist database and the log used to sit next to the exe, so zipping,
moving or re-extracting the app folder could leave the app looking at a
different (empty) database. They now live in a fixed per-user folder
(%LOCALAPPDATA%\\TrendScout) that no exe swap or folder move can touch.
"""
import os
import shutil
import sys

DB_NAME = "trendscout_watchlist.db"


def exe_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def data_dir() -> str:
    """The per-user data folder. TRENDSCOUT_DATA_DIR overrides it (for testing).
    Falls back to the exe's folder if the per-user folder can't be written."""
    base = os.environ.get("TRENDSCOUT_DATA_DIR")
    if not base:
        local = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
        base = os.path.join(local, "TrendScout")
    try:
        os.makedirs(base, exist_ok=True)
        probe = os.path.join(base, ".write_test")
        with open(probe, "w"):
            pass
        os.remove(probe)
        return base
    except OSError:
        return exe_dir()


def log_dir() -> str:
    path = os.path.join(data_dir(), "logs")
    os.makedirs(path, exist_ok=True)
    return path


def legacy_db_path() -> str:
    """Where earlier versions kept the database: next to the exe."""
    return os.path.join(exe_dir(), DB_NAME)


def resolve_db() -> tuple:
    """Returns (db_path, how) where how is 'existing', 'copied from <old path>'
    or 'created new (empty)'. An old database next to the exe is COPIED into the
    data folder the first time (the original is left where it is)."""
    db = os.path.join(data_dir(), DB_NAME)
    if os.path.exists(db):
        return db, "existing"
    legacy = legacy_db_path()
    if os.path.abspath(legacy) != os.path.abspath(db) and os.path.exists(legacy):
        shutil.copy2(legacy, db)
        return db, f"copied from {legacy}"
    return db, "created new (empty)"
