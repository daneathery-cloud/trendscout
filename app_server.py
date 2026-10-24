"""Local-only Flask server. Binds to 127.0.0.1 so it's reachable only from
this machine - never the network or internet."""
import csv
import datetime as dt
import io
import logging
import socket
import logging
import threading

from flask import Flask, request, jsonify, Response

import config
import scan_runner
import diagnostics
import store
import render
from scanners import news

logging.getLogger("werkzeug").setLevel(logging.WARNING)  # keep the request-access-log noise down
log = logging.getLogger("trendscout.web")


class AppState:
    def __init__(self):
        self.lock = threading.Lock()
        self.data = None          # latest scan_runner output dict
        self.digest_df = None     # short diverse digest for the Scan Report tab
        self.wire_df = None       # full headline pool for the Headline Wire tab
        self.generated_at = None
        self.stock_metrics = None    # every scanned stock, scored - lets the mix change without a rescan
        self.stock_news_cache = {}   # headlines already fetched per symbol
        self.conn = None          # sqlite connection, set in create_app

    def set_scan(self, data, digest_df, wire_df, generated_at, stock_metrics=None, stock_news_cache=None):
        with self.lock:
            self.data = data
            self.digest_df = digest_df
            self.wire_df = wire_df
            self.generated_at = generated_at
            self.stock_metrics = stock_metrics
            self.stock_news_cache = stock_news_cache if stock_news_cache is not None else {}


state = AppState()


def get_tech_percent() -> int:
    """The user's saved tech share for the stock lists (falls back to the default)."""
    default = int(round(config.TECH_SPLIT * 100))
    try:
        value = int(store.get_setting(state.conn, "tech_split_percent", default))
    except (TypeError, ValueError):
        return default
    return value if value in config.TECH_SPLIT_OPTIONS else default


def find_free_port(preferred: int = 5187) -> int:
    for port in [preferred, *range(5188, 5220)]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def create_app(db_path: str) -> Flask:
    app = Flask(__name__)
    state.conn = store.get_conn(db_path)

    @app.get("/")
    def scan_report():
        watchlisted = store.watchlisted_keys(state.conn)
        with state.lock:
            if state.data is None:
                return render.build_empty_scan_page()
            data = dict(state.data)
            data["digest"] = state.digest_df
            gen_at = state.generated_at
        data["tech_percent"] = get_tech_percent()
        data["history_summary"] = store.history_summary(state.conn)
        return render.build_scan_page(data, watchlisted, generated_at=gen_at)

    @app.get("/watchlist")
    def watchlist():
        items = store.list_items(state.conn)
        return render.build_watchlist_page(items)

    @app.get("/watchlist/export")
    def watchlist_export():
        items = store.list_items(state.conn)
        filename = f"TrendScout_Watchlist_{dt.date.today().isoformat()}.html"
        return Response(
            render.build_watchlist_export(items), mimetype="text/html",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/history/export")
    def history_export():
        include_universe = request.args.get("scope") == "all"
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(store.HISTORY_COLUMNS)
        writer.writerows(store.history_rows(state.conn, include_universe=include_universe))
        label = "with_universe" if include_universe else "picks"
        filename = f"TrendScout_History_{label}_{dt.date.today().isoformat()}.csv"
        # utf-8-sig adds the byte-order mark Excel needs to read company names correctly.
        return Response(
            buf.getvalue().encode("utf-8-sig"), mimetype="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/api/free_versions")
    def free_versions():
        title = (request.args.get("title") or "").strip()
        if not title:
            return jsonify({"ok": False, "error": "missing title"}), 400
        result = news.find_free_versions(title)
        if result.get("error"):
            log.warning("free-version search failed for %r: %s", title[:80], result["error"])
        else:
            log.info("free-version search %r -> %d matches", title[:80], len(result["matches"]))
        return jsonify({"ok": True, **result})

    @app.get("/diagnostics")
    def diagnostics_page():
        return render.build_diagnostics_page(diagnostics.build_report(state.conn))

    @app.get("/wire")
    def wire():
        watchlisted = store.watchlisted_keys(state.conn)
        with state.lock:
            wire_df = state.wire_df
        return render.build_wire_page(wire_df, watchlisted)

    @app.post("/api/watchlist/toggle")
    def toggle_watchlist():
        payload = request.get_json(force=True, silent=True) or {}
        action = payload.get("action")
        item_type = payload.get("type")
        item_id = payload.get("id")
        label = payload.get("label", "")
        snapshot = payload.get("snapshot", {})
        if not item_type or not item_id or action not in ("add", "remove"):
            return jsonify({"ok": False, "error": "bad request"}), 400
        if action == "add":
            store.add_item(state.conn, item_type, item_id, label, snapshot)
        else:
            store.remove_item(state.conn, item_type, item_id)
        log.info("watchlist %s %s/%s (now %d items)", action, item_type, item_id, store.watchlist_count(state.conn))
        return jsonify({"ok": True})

    @app.post("/api/settings/tech_split")
    def set_tech_split():
        payload = request.get_json(force=True, silent=True) or {}
        percent = payload.get("percent")
        if percent not in config.TECH_SPLIT_OPTIONS:
            return jsonify({"ok": False, "error": "unsupported mix"}), 400
        store.set_setting(state.conn, "tech_split_percent", int(percent))
        log.info("tech/non-tech mix set to %s/%s", percent, 100 - percent)
        with state.lock:
            metrics, cache, data = state.stock_metrics, state.stock_news_cache, state.data
        if data is not None and metrics is not None and not metrics.empty:
            # Headline lookups for newly surfaced names happen here, outside the lock.
            picks = scan_runner.repick_stocks(metrics, percent / 100, cache)
            with state.lock:
                # Merge, don't replace - repick_stocks only returns hot/sleeper,
                # and "penny" (unaffected by the tech/non-tech mix) must survive.
                state.data = {**state.data, "stocks": {**state.data["stocks"], **picks}}
        return jsonify({"ok": True})

    return app


def run_server(app: Flask, port: int):
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True)
