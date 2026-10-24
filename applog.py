"""Rolling log file + a small record of runtime facts, so a problem on any
computer can be diagnosed by pasting one block of text.

The packaged app has no console window, so without a log file anything that
goes wrong would be invisible."""
import logging
import logging.handlers
import os
import sys
import threading

LOG_NAME = "trendscout.log"

# Facts the diagnostics report needs; filled in by main.py at startup / after scans.
runtime = {}


def setup(log_dir: str) -> logging.Logger:
    """Starts file logging (500 KB x 3 rotating files) and routes uncaught
    errors into it. Safe to call once at startup."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, LOG_NAME), maxBytes=500_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s [%(threadName)s] %(name)s: %(message)s"))
    root.addHandler(handler)
    for noisy in ("urllib3", "matplotlib", "PIL", "peewee", "charset_normalizer", "chardet", "werkzeug"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    log = logging.getLogger("trendscout")

    def _excepthook(exc_type, exc, tb):
        log.critical("Uncaught exception", exc_info=(exc_type, exc, tb))

    def _thread_excepthook(args):
        name = args.thread.name if args.thread else "?"
        log.critical("Uncaught exception in thread %s", name,
                     exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = _excepthook
    threading.excepthook = _thread_excepthook
    return log


def tail(log_dir: str, max_lines: int = 150) -> str:
    """The last `max_lines` log lines (reaching into the previous file if needed)."""
    lines = []
    for name in (LOG_NAME + ".1", LOG_NAME):
        path = os.path.join(log_dir, name)
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    lines += f.read().splitlines()
            except OSError:
                pass
    return "\n".join(lines[-max_lines:])
