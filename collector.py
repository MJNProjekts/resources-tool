"""RESOURCES collector: fetches API data on a schedule, stores it, sends alerts.

    python collector.py                  # run forever (checks every TICK_MINUTES)
    python collector.py --once           # one tick: fetch what is due, then exit
    python collector.py --status         # what is due, credits used (free)
    python collector.py --report         # send the daily report now (no fetch)
    python collector.py --fetch 2 1006   # fetch these queries right now (1 credit each)
    python collector.py --import samples # load probe.py samples (0 credits)

Schedule (about 19 credits/day):
    every 6 h   warehouses (2), market (1006), missions (10)
    daily       player (7), factories (1), special buildings (3), money (8), trades (6)
    weekly      recipes & upgrade data (1002-1005, 1007), HQ (4), achievements (12)
    on demand   mines (5): when predicted condition reaches MAINT_CHECK_LEVEL, plus weekly
                id list (1001): when an unknown item ID shows up, plus monthly
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from rgtool import alerts, i18n, maintenance
from rgtool.api import QUERIES, APIError, ResourcesAPI
from rgtool.config import Config
from rgtool.db import Database
from rgtool.telegram import Telegram

H = 3600
D = 24 * H

# q: (interval seconds, days parameter, priority: lower = more important)
SCHEDULE = {
    1001: (30 * D, None, 0),
    2: (6 * H, None, 1),
    1006: (6 * H, None, 1),
    10: (6 * H, None, 1),
    7: (D, None, 2),
    1: (D, None, 2),
    3: (D, None, 2),
    8: (D, None, 2),
    6: (D, 2, 2),
    5: (7 * D, None, 3),
    1002: (7 * D, None, 3),
    1003: (7 * D, None, 4),
    1004: (7 * D, None, 4),
    1005: (7 * D, None, 3),
    1007: (7 * D, None, 4),
    4: (7 * D, None, 4),
    12: (7 * D, None, 4),
}
# Small slack so a 6 h task fetched at 12:02 is due again at 18:00, not 18:02
SLACK = 15 * 60


def due_queries(db: Database, cfg: Config, now: int) -> list[int]:
    due = []
    for q, (interval, _, _) in SCHEDULE.items():
        last = db.last_fetch(q)
        if last is None or now - last >= interval - SLACK:
            due.append(q)
    if 5 not in due and maintenance.needs_fetch(db, cfg, now):
        due.append(5)
    last_ids = db.last_fetch(1001)
    if 1001 not in due and db.get_meta("need_1001") == "1" and (not last_ids or now - last_ids > D):
        due.append(1001)
    return sorted(due, key=lambda q: SCHEDULE.get(q, (0, None, 9))[2])


def fetch(api, db: Database, cfg: Config, q: int, now: int) -> list[str]:
    """Fetch and store one query. Returns alerts produced by this fetch."""
    msgs = []
    days = SCHEDULE.get(q, (0, None, 0))[1]
    prev_mines = maintenance.state_at(db) if q == 5 else None
    try:
        data = api.query(q, days)
    except APIError as e:
        db.log_fetch(now, q, False, note=str(e))
        print(f"  q={q} {QUERIES.get(q)}: {e}")
        return msgs
    info = db.ingest(q, data, now)
    db.log_fetch(now, q, True, info["rows"])
    print(f"  q={q} {QUERIES.get(q)}: {info['rows']} rows")

    if q == 1001:
        db.set_meta("need_1001", "0")
    if info["unknown_ids"]:
        db.set_meta("need_1001", "1")
        if q in (2, 1006):
            msgs += alerts.new_items(data if isinstance(data, list) else [], info["unknown_ids"])
    if q == 5:
        new = maintenance.state_at(db, now)
        result = maintenance.after_fetch(db, cfg, prev_mines, new)
        if result["warn"]:
            msgs += alerts.maintenance_due(db, cfg, now)
    return msgs


def tick(api, db: Database, cfg: Config, tg: Telegram, now: int | None = None) -> None:
    now = now or int(time.time())
    db.set_meta("heartbeat", now)          # the web page shows "monitor active" from this
    db.set_meta("tick_minutes", cfg.tick_minutes)
    db.commit()
    due = due_queries(db, cfg, now)
    msgs: list[str] = []
    credits_left = None
    if due:
        credits_left = api.credits()
        if credits_left is not None and credits_left < cfg.min_credits:
            if db.should_alert("low_credits", D, now):
                tg.send(i18n.t("low_credits", n=credits_left))
            due = []
        budget = cfg.daily_budget - db.credits_used_since(now - D)
        if len(due) > budget:
            print(f"  daily budget: running {max(budget, 0)} of {len(due)} due queries")
            due = due[:max(budget, 0)]
    fetched = set()
    for q in due:
        msgs += fetch(api, db, cfg, q, now)
        fetched.add(q)
    db.commit()

    if 2 in fetched:
        msgs += alerts.warehouse(db, cfg, now)
    if 1006 in fetched:
        msgs += alerts.market(db, cfg, now)
    if 10 in fetched:
        msgs += alerts.missions_deadline(db, cfg, now)
    msgs += alerts.missions_opened(db, cfg, now)
    msgs += alerts.daily_report(db, cfg, now, credits_left)
    db.commit()
    if msgs:
        tg.send("\n\n".join(msgs))
    if fetched:
        print(f"{time.strftime('%H:%M')} fetched {sorted(fetched)}, {len(msgs)} messages")


def import_samples(db: Database, folder: str) -> None:
    """Load JSON files saved by probe.py (named <q>_<name>.json). Costs nothing."""
    files = sorted(Path(folder).glob("*_*.json"), key=lambda p: int(p.name.split("_")[0]))
    # id list first, so other imports can resolve names
    files.sort(key=lambda p: p.name.split("_")[0] != "1001")
    for p in files:
        q = int(p.name.split("_")[0])
        if q not in SCHEDULE:
            print(f"  skipped  q={q:<5} {QUERIES.get(q, '?')} (not used)")
            continue
        ts = int(p.stat().st_mtime)
        info = db.ingest(q, json.loads(p.read_text(encoding="utf-8")), ts)
        db.log_fetch(ts, q, True, info["rows"], credits=0, note="import")
        print(f"  imported q={q:<5} {QUERIES.get(q, '?'):<26} {info['rows']} rows")
    db.commit()


def status(db: Database, cfg: Config, now: int) -> None:
    print(f"Credits used last 24h: {db.credits_used_since(now - D)} (budget {cfg.daily_budget})")
    p = maintenance.predicted(db, cfg, now)
    if p is not None:
        print(f"Mines condition (predicted): {100 * p:.1f}%  "
              f"decay {100 * maintenance.decay_per_day(db, cfg):.2f}%/day")
    print("Due now:", due_queries(db, cfg, now) or "nothing")
    for q in sorted(SCHEDULE):
        last = db.last_fetch(q)
        age = f"{(now - last) / H:6.1f} h ago" if last else "never"
        print(f"  q={q:<5} {QUERIES[q]:<26} {age}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--import", dest="import_dir")
    ap.add_argument("--fetch", type=int, nargs="+", metavar="Q", help="fetch these query IDs now")
    args = ap.parse_args()

    load_dotenv()
    cfg = Config.from_env()
    i18n.set_lang(cfg.ui_lang)
    db = Database(cfg.db_path)
    tg = Telegram(cfg.tg_token, cfg.tg_chat)
    now = int(time.time())

    if args.import_dir:
        import_samples(db, args.import_dir)
        return
    if args.status:
        status(db, cfg, now)
        return
    if args.report:
        tg.send("\n".join(alerts.daily_report(db, cfg, now, force=True)) or i18n.t("no_report"))
        db.commit()
        return

    try:
        api = ResourcesAPI(cfg.api_key, cfg.lang)
    except APIError as e:
        sys.exit(f"Error: {e}")

    if args.fetch:
        now = int(time.time())
        for q in args.fetch:
            if q not in QUERIES or q == 0:
                print(f"  unknown query {q}")
                continue
            for m in fetch(api, db, cfg, q, now):
                tg.send(m)
        db.commit()
        return

    while True:
        try:
            tick(api, db, cfg, tg)
        except Exception as e:  # keep running; never spam retries
            print(f"tick error: {type(e).__name__}: {e}")
        if args.once:
            break
        time.sleep(cfg.tick_minutes * 60)


if __name__ == "__main__":
    main()
