"""Local dashboard for the RESOURCES tool. Reads the database only (0 credits).

    python -m web.app                 # http://127.0.0.1:8050
    python -m web.app --lan           # reachable from your phone on the same Wi-Fi
"""

from __future__ import annotations

import argparse
import ipaddress
import socket
import threading
import time
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory

import collector
from rgtool.api import APIError, ResourcesAPI
from rgtool.config import Config
from rgtool.db import Database

from . import data

STATIC = Path(__file__).with_name("static")
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def host_name(host: str) -> str:
    """'127.0.0.1:8050' -> '127.0.0.1', '[::1]:8050' -> '::1'."""
    host = (host or "").strip().lower()
    if host.startswith("["):
        return host[1:host.find("]")] if "]" in host else ""
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def host_allowed(host: str, allow_lan: bool) -> bool:
    """Blocks DNS rebinding: a foreign web page whose domain points to this
    computer still sends its own domain in the Host header, so it is refused.
    Locally only localhost names are accepted; with --lan also bare IP
    addresses and the Mac's own *.local name."""
    name = host_name(host)
    if name in LOCAL_HOSTS:
        return True
    if not allow_lan:
        return False
    if name.endswith(".local") and name.count(".") == 1:
        return True
    try:
        ipaddress.ip_address(name)
        return True
    except ValueError:
        return False


def create_app(cfg: Config, allow_lan_refresh: bool = False, allow_lan: bool = False) -> Flask:
    app = Flask(__name__, static_folder=None)
    allow_lan = allow_lan or allow_lan_refresh

    @app.before_request
    def check_host():
        if not host_allowed(request.host, allow_lan):
            return "Invalid host", 403

    @app.after_request
    def security_headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        return resp

    @app.get("/")
    def index():
        return send_from_directory(STATIC, "index.html")

    @app.get("/static/<path:name>")
    def static_files(name):
        return send_from_directory(STATIC, name)

    @app.get("/api/overview")
    def api_overview():
        db = Database(cfg.db_path)  # one connection per request: SQLite + threads
        try:
            return jsonify(data.overview(db, cfg))
        finally:
            db.con.close()

    lock = threading.Lock()
    credits_cache = {"ts": 0, "value": None}

    def credits_left():
        """Free API call, cached for 5 minutes."""
        if time.time() - credits_cache["ts"] > 300:
            try:
                credits_cache["value"] = ResourcesAPI(cfg.api_key, cfg.lang).credits()
            except APIError:
                credits_cache["value"] = None
            credits_cache["ts"] = time.time()
        return credits_cache["value"]

    @app.get("/api/status")
    def api_status():
        db = Database(cfg.db_path)
        try:
            return jsonify(data.status(db, cfg, credits_left()))
        finally:
            db.con.close()

    def err(code, status, **p):
        return jsonify(ok=False, code=code, p=p), status

    @app.post("/api/refresh/warehouse")
    def api_refresh_warehouse():
        """Fetch warehouses (q=2) now. Costs 1 credit, at most once per 5 minutes.

        Guards: the custom header blocks cross-site form posts (CSRF), and
        unless allowed, only this computer may spend credits (not the LAN).
        """
        if request.headers.get("X-Requested-With") != "rgtool":
            return err("forbidden", 403)
        if not allow_lan_refresh and request.remote_addr not in ("127.0.0.1", "::1"):
            return err("local_only", 403)
        if not lock.acquire(blocking=False):
            return err("busy", 409)
        db = Database(cfg.db_path)
        try:
            now = int(time.time())
            last = db.last_fetch(2)
            if last and now - last < 300:
                return err("too_soon", 429, m=(now - last) // 60)
            left = credits_left()
            if left is not None and left < cfg.min_credits:
                return err("low_credits", 402, n=left)
            try:
                api = ResourcesAPI(cfg.api_key, cfg.lang)
            except APIError:
                return err("no_key", 500)
            collector.fetch(api, db, cfg, 2, now)
            db.commit()
            credits_cache["ts"] = 0
            if db.last_fetch(2) != now:
                return err("api_failed", 502)
            return jsonify(ok=True, ts=now)
        finally:
            db.con.close()
            lock.release()

    return app


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8050)
    ap.add_argument("--lan", action="store_true", help="listen on the local network too (read-only)")
    ap.add_argument("--lan-refresh", action="store_true",
                    help="with --lan: also allow devices on the network to spend credits")
    args = ap.parse_args()
    load_dotenv()
    cfg = Config.from_env()
    host = "0.0.0.0" if args.lan else "127.0.0.1"
    if args.lan:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            print(f"On your phone open: http://{s.getsockname()[0]}:{args.port}")
            s.close()
        except OSError:
            pass
    if args.lan:
        print("Warning: anyone on this network can view the page. No login, use only on a trusted network.")
    create_app(cfg, allow_lan_refresh=args.lan and args.lan_refresh, allow_lan=args.lan).run(host=host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
