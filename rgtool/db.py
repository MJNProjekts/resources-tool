"""SQLite storage: schema, ingest of every API answer, small helpers."""

from __future__ import annotations

import json
import sqlite3
import time
import zlib
from pathlib import Path

SCHEMA = Path(__file__).with_name("schema.sql")


def f(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def i(v, default=0) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _rows(data):
    """API answers are lists of dicts; tolerate a single dict too."""
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        return [data]
    return []


class Database:
    def __init__(self, path: str = "resources.db"):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(path)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(SCHEMA.read_text(encoding="utf-8"))

    # ------------------------------------------------------------- basics
    def q(self, sql, args=()):
        return self.con.execute(sql, args).fetchall()

    def one(self, sql, args=()):
        return self.con.execute(sql, args).fetchone()

    def commit(self):
        self.con.commit()

    def get_meta(self, key, default=None):
        row = self.one("SELECT value FROM meta WHERE key=?", (key,))
        return row["value"] if row else default

    def set_meta(self, key, value):
        self.con.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, str(value)))

    def should_alert(self, key, cooldown_s, now=None):
        """True once per cooldown for the same key (de-duplicates alerts)."""
        now = now or int(time.time())
        row = self.one("SELECT ts FROM alerts WHERE key=?", (key,))
        if row and now - row["ts"] < cooldown_s:
            return False
        self.con.execute("INSERT OR REPLACE INTO alerts VALUES (?,?)", (key, now))
        return True

    # ------------------------------------------------------------- fetch log
    def log_fetch(self, ts, q, ok, rows=0, credits=1, note=""):
        self.con.execute("INSERT INTO fetch_log VALUES (?,?,?,?,?,?)",
                         (ts, q, int(ok), rows, credits, note))

    def last_fetch(self, q):
        row = self.one("SELECT MAX(ts) t FROM fetch_log WHERE q=? AND ok=1", (q,))
        return row["t"] if row and row["t"] else None

    def credits_used_since(self, ts):
        row = self.one("SELECT COALESCE(SUM(credits),0) c FROM fetch_log WHERE ts>=?", (ts,))
        return row["c"]

    # ------------------------------------------------------------- items
    def known_item_ids(self):
        return {r["item_id"] for r in self.q("SELECT item_id FROM items")}

    def item_name(self, item_id):
        row = self.one("SELECT name FROM items WHERE item_id=?", (item_id,))
        return row["name"] if row else f"#{item_id}"

    # ------------------------------------------------------------- ingest
    def ingest(self, q: int, data, ts: int | None = None) -> dict:
        """Store one API answer. Returns info: rows, unknown item IDs."""
        ts = ts or int(time.time())
        rows = _rows(data)
        self.con.execute("INSERT OR REPLACE INTO raw VALUES (?,?,?)",
                         (ts, q, zlib.compress(json.dumps(data).encode())))
        handler = getattr(self, f"_ingest_{q}", None)
        referenced = handler(rows, ts) if handler else set()
        known = self.known_item_ids()
        unknown = {x for x in (referenced or set()) if x and x not in known} if known else set()
        return {"rows": len(rows), "unknown_ids": unknown}

    # q=1 factories
    def _ingest_1(self, rows, ts):
        for r in rows:
            fid = i(r["factoryID"])
            self.con.execute("INSERT OR REPLACE INTO factories VALUES (?,?,?,?,?)",
                             (fid, r.get("name"), i(r.get("lvl")), r.get("strike"), ts))
            self.con.execute("INSERT OR REPLACE INTO factories_hist VALUES (?,?,?)",
                             (ts, fid, i(r.get("lvl"))))

    # q=2 warehouses
    def _ingest_2(self, rows, ts):
        ids = set()
        for r in rows:
            iid = i(r["itemID"])
            ids.add(iid)
            self.con.execute("INSERT OR REPLACE INTO warehouse_hist VALUES (?,?,?,?)",
                             (ts, iid, i(r.get("level")), f(r.get("amount"))))
        return ids

    # q=3 special buildings
    def _ingest_3(self, rows, ts):
        for r in rows:
            sid = i(r["specbID"])
            self.con.execute("INSERT OR REPLACE INTO specbuildings VALUES (?,?,?,?)",
                             (sid, r.get("name"), i(r.get("lvl")), ts))
            self.con.execute("INSERT OR REPLACE INTO specb_hist VALUES (?,?,?)",
                             (ts, sid, i(r.get("lvl"))))

    # q=4 HQ
    def _ingest_4(self, rows, ts):
        for r in rows[:1]:
            self.con.execute("INSERT OR REPLACE INTO hq VALUES (1,?,?,?,?,?,?)",
                             (i(r.get("lvl")), f(r.get("lat")), f(r.get("lon")),
                              f(r.get("target")), json.dumps(r), ts))

    # q=5 mines (full list -> mark missing as inactive)
    def _ingest_5(self, rows, ts):
        if not rows:
            return
        self.con.execute("UPDATE mines SET active=0")
        for r in rows:
            mid = f"{f(r.get('lat')):.6f},{f(r.get('lon')):.6f}"
            self.con.execute(
                "INSERT OR REPLACE INTO mines VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (mid, i(r.get("mineID")), r.get("name"), i(r.get("resourceID")), r.get("resourceName"),
                 f(r.get("lat")), f(r.get("lon")), i(r.get("builddate")), f(r.get("HQboost")),
                 f(r.get("fullrate")), f(r.get("rawrate")), f(r.get("techfactor")),
                 f(r.get("quality")), f(r.get("qualityInclTU")), f(r.get("condition")),
                 i(r.get("lastmaintenance")), i(r.get("lastenemyaction")),
                 i(r.get("def1")), i(r.get("def2")), i(r.get("def3")),
                 f(r.get("attackpenalty")), i(r.get("attackcount")), i(r.get("attacklost")),
                 1, ts))
            self.con.execute("INSERT OR REPLACE INTO mines_hist VALUES (?,?,?,?,?,?)",
                             (ts, mid, f(r.get("condition")), i(r.get("lastmaintenance")),
                              f(r.get("fullrate")), i(r.get("attackcount"))))
        return {i(r.get("resourceID")) for r in rows}

    # q=6 trade log
    def _ingest_6(self, rows, ts):
        for r in rows:
            self.con.execute("INSERT OR IGNORE INTO trades VALUES (?,?,?,?,?,?,?,?)",
                             (i(r.get("ts")), r.get("event"), r.get("username"), i(r.get("ulvl")),
                              i(r.get("itemID")), f(r.get("amount")), f(r.get("ppstk")),
                              f(r.get("transcost"))))
        return {i(r.get("itemID")) for r in rows}

    # q=7 player info
    def _ingest_7(self, rows, ts):
        for r in rows[:1]:
            self.con.execute("INSERT OR REPLACE INTO player_hist VALUES (?,?,?,?,?)",
                             (ts, r.get("username"), i(r.get("lvl")), i(r.get("points")),
                              i(r.get("worldrank"))))
            self.set_meta("username", r.get("username"))

    # q=8 money per category per day
    def _ingest_8(self, rows, ts):
        for r in rows:
            self.con.execute("INSERT OR REPLACE INTO money_daily VALUES (?,?,?,?,?)",
                             (i(r.get("date")), i(r.get("itemID")), r.get("itemName"),
                              f(r.get("revenues")), f(r.get("expenditures"))))

    # q=10 missions
    def _ingest_10(self, rows, ts):
        for r in rows:
            self.con.execute(
                "INSERT OR REPLACE INTO missions_hist VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (ts, i(r["questID"]), r.get("title"), r.get("descr"), str(r.get("status")),
                 f(r.get("progress")), f(r.get("missiongoal")), f(r.get("durHours")),
                 i(r.get("rewarditem")), f(r.get("rewardamount")), f(r.get("penalty")),
                 f(r.get("cooldown")), f(r.get("starttime")), f(r.get("endtime")),
                 f(r.get("intervalDays"))))
        return {i(r.get("rewarditem")) for r in rows}

    # q=12 achievements
    def _ingest_12(self, rows, ts):
        for r in rows:
            self.con.execute(
                "INSERT OR REPLACE INTO achievements VALUES (?,?,?,?,?,?,?,?,?,?)",
                (i(r["achievementID"]), r.get("title"), r.get("descr"), i(r.get("rewardItemID")),
                 f(r.get("rewardAmt")), f(r.get("reqAmt")), i(r.get("hasAchievCompleted")),
                 i(r.get("hasRewardEarned")), i(r.get("completedTS")), ts))

    # q=1001 ID list
    def _ingest_1001(self, rows, ts):
        for r in rows:
            self.con.execute("INSERT OR REPLACE INTO items VALUES (?,?,?)",
                             (i(r["itemID"]), r.get("itemname"), r.get("iconURL")))

    # q=1002 recipes
    def _ingest_1002(self, rows, ts):
        self.con.execute("DELETE FROM recipes")
        self.con.execute("DELETE FROM recipe_inputs")
        ids = set()
        for r in rows:
            pid = i(r["itemID"])
            ids.add(pid)
            self.con.execute("INSERT INTO recipes VALUES (?,?,?,?,?,?)",
                             (pid, i(r.get("factoryID")), r.get("factoryName"),
                              f(r.get("baseOutputPerHour")), f(r.get("outputPerCycle")),
                              f(r.get("creditsPerCycle"))))
            for n in (1, 2, 3):
                if r.get(f"itemID{n}"):
                    iid = i(r[f"itemID{n}"])
                    ids.add(iid)
                    self.con.execute("INSERT OR REPLACE INTO recipe_inputs VALUES (?,?,?)",
                                     (pid, iid, f(r.get(f"item{n}QtyPerCycle"))))
        return ids

    # q=1003 recycling
    def _ingest_1003(self, rows, ts):
        self.con.execute("DELETE FROM recycling")
        self.con.execute("DELETE FROM recycling_outputs")
        for r in rows:
            iid = i(r["itemID"])
            self.con.execute("INSERT INTO recycling VALUES (?,?,?)",
                             (iid, r.get("itemName"), f(r.get("inputQty"))))
            for n in (1, 2, 3, 4):
                if r.get(f"outputRes{n}"):
                    self.con.execute("INSERT OR REPLACE INTO recycling_outputs VALUES (?,?,?)",
                                     (iid, i(r[f"outputRes{n}"]), f(r.get(f"outputQty{n}"))))

    # q=1004 factory upgrade base data
    def _ingest_1004(self, rows, ts):
        self.con.execute("DELETE FROM factory_upgrades")
        self.con.execute("DELETE FROM factory_upgrade_items")
        for r in rows:
            fid = i(r["factoryID"])
            self.con.execute("INSERT INTO factory_upgrades VALUES (?,?,?,?,?)",
                             (fid, r.get("factoryName"), i(r.get("productID")),
                              f(r.get("baseUpgCost")), i(r.get("minUsrLvl"))))
            for n in (1, 2, 3):
                if r.get(f"baseUpgItemID{n}"):
                    self.con.execute("INSERT OR REPLACE INTO factory_upgrade_items VALUES (?,?,?)",
                                     (fid, i(r[f"baseUpgItemID{n}"]), f(r.get(f"baseUpgItemQty{n}"))))

    # q=1005 special building upgrade base data
    def _ingest_1005(self, rows, ts):
        self.con.execute("DELETE FROM specb_upgrades")
        self.con.execute("DELETE FROM specb_upgrade_items")
        for r in rows:
            sid = i(r["specBuildID"])
            self.con.execute("INSERT INTO specb_upgrades VALUES (?,?,?,?)",
                             (sid, r.get("specBuildName"), f(r.get("baseUpgCost")),
                              i(r.get("minUsrLvl"))))
            for n in (1, 2, 3):
                if r.get(f"baseUpgItemID{n}"):
                    self.con.execute("INSERT OR REPLACE INTO specb_upgrade_items VALUES (?,?,?)",
                                     (sid, i(r[f"baseUpgItemID{n}"]), f(r.get(f"baseUpgItemQty{n}"))))

    # q=1006 market rates
    def _ingest_1006(self, rows, ts):
        ids = set()
        for r in rows:
            iid = i(r["itemID"])
            ids.add(iid)
            self.con.execute("INSERT OR REPLACE INTO market_hist VALUES (?,?,?,?)",
                             (ts, iid, f(r.get("KIprice")), f(r.get("price"))))
        return ids

    # q=1007 troops
    def _ingest_1007(self, rows, ts):
        self.con.execute("DELETE FROM troops")
        self.con.execute("DELETE FROM troop_items")
        for r in rows:
            tid = i(r["itemID"])
            self.con.execute("INSERT INTO troops VALUES (?,?,?)",
                             (tid, r.get("itemName"), f(r.get("costPerUnit"))))
            for n in (1, 2, 3):
                if r.get(f"itemID{n}"):
                    self.con.execute("INSERT OR REPLACE INTO troop_items VALUES (?,?,?)",
                                     (tid, i(r[f"itemID{n}"]), f(r.get(f"itemQty{n}"))))

    # ------------------------------------------------------------- common reads
    def latest_ts(self, table):
        row = self.one(f"SELECT MAX(ts) t FROM {table}")
        return row["t"] if row else None

    def latest_prices(self):
        ts = self.latest_ts("market_hist")
        if not ts:
            return {}
        return {r["item_id"]: (r["ki_price"], r["price"])
                for r in self.q("SELECT * FROM market_hist WHERE ts=?", (ts,))}

    def latest_stock(self):
        ts = self.latest_ts("warehouse_hist")
        if not ts:
            return {}
        return {r["item_id"]: (r["amount"], r["level"])
                for r in self.q("SELECT * FROM warehouse_hist WHERE ts=? AND item_id<>1", (ts,))}
