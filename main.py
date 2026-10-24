"""TrendScout desktop launcher: starts the local-only web server, then a
button in this window triggers a scan and opens the live report in your
browser. The server binds to 127.0.0.1 only - nothing outside this PC can
reach it."""
import logging
import os
import threading
import time
import traceback
import webbrowser
import datetime as dt
import tkinter as tk
from tkinter import scrolledtext, messagebox

import applog
import paths

LOG_DIR = paths.log_dir()
applog.setup(LOG_DIR)          # start the log file before anything else runs

import app_server              # noqa: E402  (imported after logging is configured)
import diagnostics             # noqa: E402
import history                 # noqa: E402
import scan_runner             # noqa: E402
import store                   # noqa: E402
from version import VERSION    # noqa: E402

logger = logging.getLogger("trendscout")


class App:
    def __init__(self, root):
        self.root = root
        root.title(f"TrendScout v{VERSION} — Market & Crypto Trend Scanner")
        root.geometry("780x560")
        root.configure(bg="#0f1420")
        root.report_callback_exception = self._tk_error
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        header = tk.Label(
            root, text="TrendScout", font=("Segoe UI", 20, "bold"),
            fg="#e8ecf6", bg="#0f1420",
        )
        header.pack(pady=(18, 0))
        sub = tk.Label(
            root, text="Scans free/public sources for hot & sleeper stocks, crypto, and currencies.\n"
                        "Informational only — not investment advice.",
            font=("Segoe UI", 10), fg="#8b95ad", bg="#0f1420", justify="center",
        )
        sub.pack(pady=(2, 14))
        tk.Label(root, text=f"Version {VERSION}", font=("Segoe UI", 8),
                 fg="#8b95ad", bg="#0f1420").pack(side="bottom", pady=(0, 6))

        self.scan_btn = tk.Button(
            root, text="Scan Now", font=("Segoe UI", 13, "bold"),
            bg="#3ecf8e", fg="#0f1420", activebackground="#33b87c",
            relief="flat", padx=22, pady=10, command=self.start_scan,
        )
        self.scan_btn.pack(pady=(0, 12))

        self.log_box = scrolledtext.ScrolledText(
            root, height=18, bg="#161d2e", fg="#c8d0e0", insertbackground="#c8d0e0",
            font=("Consolas", 9), relief="flat",
        )
        self.log_box.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        self.log_box.configure(state="disabled")

        btn_row = tk.Frame(root, bg="#0f1420")
        btn_row.pack(pady=(0, 16))
        for text, command in (
            ("Open Report", lambda: self.open_url("/")),
            ("Watchlist", lambda: self.open_url("/watchlist")),
            ("Headline Wire", lambda: self.open_url("/wire")),
            ("Copy Diagnostics", self.copy_diagnostics),
            ("Open Data Folder", self.open_data_folder),
        ):
            tk.Button(
                btn_row, text=text, font=("Segoe UI", 10),
                bg="#1c2438", fg="#e8ecf6", relief="flat", padx=11, pady=6, command=command,
            ).pack(side="left", padx=3)

        self.port = None
        self.server_thread = None
        self._start_server()

    # -- startup ---------------------------------------------------------
    def _open_database(self) -> str:
        try:
            db_path, how = paths.resolve_db()
        except Exception as e:
            # Never block startup over this: fall back to the old next-to-the-exe location.
            logger.exception("Could not prepare the data folder")
            db_path, how = paths.legacy_db_path(), f"fallback to old location ({type(e).__name__}: {e})"
        applog.runtime.update(db_path=db_path, db_how=how)
        return db_path

    def _start_server(self):
        logger.info("=== TrendScout %s starting ===", VERSION)
        self.log("Starting local server (127.0.0.1 only - not reachable from your network)...")
        db_path = self._open_database()
        how = applog.runtime["db_how"]
        app = app_server.create_app(db_path)
        items = store.watchlist_count(app_server.state.conn)
        scans = (store.history_summary(app_server.state.conn) or {}).get("scans", 0)

        self.log(f"Data folder: {paths.data_dir()}")
        self.log(f"Watchlist database: {db_path}")
        if how == "existing":
            self.log(f"  found your saved data: {items} watchlist items, {scans} saved scans.")
        elif how.startswith("copied"):
            self.log(f"  imported your earlier database ({how}): {items} watchlist items.")
            self.log("  From now on the app keeps it in the data folder above, so moving or")
            self.log("  re-extracting the program folder can no longer lose it.")
        else:
            self.log("  NOTE: no earlier watchlist database was found, so a NEW, EMPTY one was created.")
            self.log("  If you expected saved items, click 'Copy Diagnostics' and paste the result to Claude.")
        logger.info("database %s (%s): %d watchlist items, %d saved scans", db_path, how, items, scans)

        self.port = app_server.find_free_port()
        applog.runtime["port"] = self.port

        def run():
            app_server.run_server(app, self.port)

        self.server_thread = threading.Thread(target=run, daemon=True, name="web-server")
        self.server_thread.start()
        self.log(f"Server ready at http://127.0.0.1:{self.port}/")

    # -- helpers ---------------------------------------------------------
    def open_url(self, path):
        if self.port is None:
            return
        webbrowser.open(f"http://127.0.0.1:{self.port}{path}")

    def log(self, msg: str):
        logger.info(msg)

        def append():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", msg + "\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.root.after(0, append)

    def copy_diagnostics(self):
        try:
            report = diagnostics.build_report(app_server.state.conn)
            self.root.clipboard_clear()
            self.root.clipboard_append(report)
            self.root.update()
            logger.info("diagnostics copied to clipboard (%d characters)", len(report))
            messagebox.showinfo("Diagnostics copied",
                                "The diagnostics are on your clipboard.\n\n"
                                "Paste them into your chat with Claude (Ctrl+V). They list versions, "
                                "where your data is stored, item counts and the recent log "
                                "(which notes tickers you added or removed).")
        except Exception as e:
            logger.exception("Could not build diagnostics")
            messagebox.showerror("Diagnostics", f"Could not build the diagnostics:\n{e}")

    def open_data_folder(self):
        try:
            os.startfile(paths.data_dir())
        except Exception as e:
            logger.exception("Could not open the data folder")
            messagebox.showerror("Data folder", f"Could not open the folder:\n{e}\n\n{paths.data_dir()}")

    def _tk_error(self, exc_type, exc, tb):
        logger.error("Error in the app window", exc_info=(exc_type, exc, tb))

    def _on_close(self):
        logger.info("=== TrendScout closed ===")
        self.root.destroy()

    # -- scanning --------------------------------------------------------
    def start_scan(self):
        self.scan_btn.configure(state="disabled", text="Scanning...")
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        thread = threading.Thread(target=self._run_scan, daemon=True, name="scan")
        thread.start()

    @staticmethod
    def _summary(result) -> str:
        stocks, crypto = result["data"]["stocks"], result["data"]["crypto"]
        n = lambda df: 0 if df is None else len(df)
        wire = result.get("wire_df")
        return (f"hot={n(stocks.get('hot'))} sleeper={n(stocks.get('sleeper'))} "
                f"under50={n(stocks.get('under50'))} penny={n(stocks.get('penny'))} "
                f"crypto_hot={n(crypto.get('hot'))} crypto_sleeper={n(crypto.get('sleeper'))} "
                f"fx={n(result['data'].get('forex'))} headlines={n(wire)}")

    def _run_scan(self):
        started = time.time()
        try:
            result = scan_runner.run_full_scan(
                progress_cb=self.log, tech_split=app_server.get_tech_percent() / 100)
            app_server.state.set_scan(
                result["data"], result["digest_df"], result["wire_df"], result["generated_at"],
                stock_metrics=result["stock_metrics"], stock_news_cache=result["stock_news_cache"],
            )
            seconds = round(time.time() - started)
            summary = self._summary(result)
            applog.runtime["last_scan"] = {"finished": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                           "ok": True, "seconds": seconds, "summary": summary}
            self.log(f"Scan finished in {seconds}s: {summary}")
            # Saving history is a bonus; if it ever fails the scan itself still succeeds.
            try:
                scan_id, saved = history.record(
                    app_server.state.conn, result, VERSION, app_server.get_tech_percent())
                self.log(f"Saved scan #{scan_id} to history ({saved} rows).")
            except Exception as e:
                logger.exception("Scan history not saved")
                self.log(f"(Scan history not saved: {e})")
            self.root.after(0, self._on_scan_done)
        except Exception as e:
            logger.exception("Scan failed")
            applog.runtime["last_scan"] = {"finished": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                           "ok": False, "seconds": round(time.time() - started),
                                           "summary": f"{type(e).__name__}: {e}"}
            self.log(f"ERROR: {e}")
            self.log(traceback.format_exc())
            self.root.after(0, self._on_scan_error, str(e))

    def _on_scan_done(self):
        self.scan_btn.configure(state="normal", text="Scan Now")
        self.open_url("/")

    def _on_scan_error(self, msg):
        self.scan_btn.configure(state="normal", text="Scan Now")
        messagebox.showerror("Scan failed",
                             f"Something went wrong:\n{msg}\n\nClick 'Copy Diagnostics' and paste the "
                             "result to Claude so it can be fixed.")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
