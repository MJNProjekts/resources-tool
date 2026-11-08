"""Alerts built from the database. Each function returns a list of messages (HTML)."""

from __future__ import annotations

from datetime import datetime

from . import maintenance
from .db import Database
from .fmt import clock, esc, hours, num
from .i18n import t

HOUR = 3600
DAY = 24 * HOUR


# ---------------------------------------------------------------- warehouse
def warehouse(db: Database, cfg, now: int) -> list[str]:
    """Warn when a warehouse will be full in < warehouse_alert_h hours.

    Rate = net change between the two latest snapshots that are >= 1 h apart,
    so factory consumption is already included."""
    ts = db.latest_ts("warehouse_hist")
    prev = db.one("SELECT MAX(ts) t FROM warehouse_hist WHERE ts<=?", (ts - HOUR,)) if ts else None
    if not ts or not prev or not prev["t"]:
        return []
    prev_ts = prev["t"]
    old = {r["item_id"]: r["amount"] for r in db.q("SELECT * FROM warehouse_hist WHERE ts=?", (prev_ts,))}
    prices = db.latest_prices()
    out = []
    for r in db.q("SELECT * FROM warehouse_hist WHERE ts=? AND item_id<>1", (ts,)):
        iid, amount, level = r["item_id"], r["amount"], r["level"]
        if iid not in old or level <= 0:
            continue
        rate = (amount - old[iid]) / ((ts - prev_ts) / HOUR)
        if rate <= 0:
            continue
        cap = cfg.capacity(level)
        left_h = (cap - amount) / rate - (now - ts) / HOUR
        if left_h >= cfg.warehouse_alert_h or not db.should_alert(f"wh:{iid}", 6 * HOUR, now):
            continue
        ki, bid = prices.get(iid, (0, 0))
        hint = (t("wh_buyer", bid=num(bid), ki=num(ki)) if bid > ki > 0 else t("wh_no_buyer", ki=num(ki)))
        when = t("wh_full_now") if left_h <= 0 else t("wh_full_in", t=hours(left_h))
        out.append(f"📦 <b>{esc(db.item_name(iid))}</b> {min(100 * amount / cap, 100):.0f}%, "
                   f"{when} (+{num(rate)}/h)\n{hint}")
    return out


# ---------------------------------------------------------------- market
def market(db: Database, cfg, now: int) -> list[str]:
    """One grouped message: buyers paying clearly more than the KI-market for things
    you hold a lot of, ranked by extra profit vs selling to the KI-market.
    The same offer (item + price) is announced only once."""
    prices = db.latest_prices()
    stock = db.latest_stock()
    offers, trends = [], []
    for iid, (ki, bid) in prices.items():
        if iid in cfg.market_ignore:
            continue
        held = stock.get(iid, (0, 0))[0]
        if ki <= 0 or held * ki < cfg.price_min_stock_value:
            continue
        if bid > 0 and 100 * (bid / ki - 1) >= cfg.market_premium_pct:
            offers.append((held * (bid - ki), iid, ki, bid, held))
        r = db.one("SELECT AVG(ki_price) a, COUNT(*) n FROM market_hist WHERE item_id=? AND ts>=?",
                   (iid, now - 7 * DAY))
        if r["a"] and r["n"] >= 8:
            diff = 100 * (ki / r["a"] - 1)
            if diff >= cfg.price_alert_pct and db.should_alert(f"px:{iid}", DAY, now):
                trends.append(t("tr_line", name=esc(db.item_name(iid)), ki=num(ki), pct=f"{diff:.0f}",
                                value=num(held * ki)))
    out = []
    lines = []
    for gain, iid, ki, bid, held in sorted(offers, reverse=True)[:cfg.market_top_n]:
        if db.should_alert(f"mp:{iid}:{int(bid)}", 7 * DAY, now):
            lines.append(t("mk_line", name=esc(db.item_name(iid)), bid=num(bid),
                           pct=f"{100 * (bid / ki - 1):.0f}", held=num(held), gain=num(gain)))
    if lines:
        out.append(t("mk_head") + "\n" + "\n".join(lines))
    if trends:
        out.append(t("tr_head") + "\n" + "\n".join(trends))
    return out


def new_items(rows: list, unknown: set) -> list[str]:
    """Called by the collector when market/warehouse contain an unknown item ID."""
    out = []
    for r in rows:
        iid = int(float(r.get("itemID", 0)))
        if iid in unknown:
            name = r.get("itemName") or r.get("itemname") or f"#{iid}"
            out.append(t("new_item", name=esc(name), id=iid, ki=num(r.get("KIprice", 0))))
    return out


# ---------------------------------------------------------------- missions
def _mission_text(db, r) -> str:
    descr = str(r["descr"] or "").replace("{}", num(r["goal"]))
    reward = f"{num(r['reward_amt'])} × {db.item_name(r['reward_item'])}" if r["reward_item"] else ""
    return f"<b>{esc(r['title'])}</b>: {esc(descr)}" + (f" ({esc(reward)})" if reward else "")


def missions_opened(db: Database, cfg, now: int) -> list[str]:
    """Mission cooldown is seconds until it opens, so we know the exact opening
    time without extra queries. Runs every tick."""
    rows = db.q("""
        SELECT m.* FROM missions_hist m
        JOIN (SELECT quest_id, MAX(ts) t FROM missions_hist WHERE cooldown>0 GROUP BY quest_id) x
          ON m.quest_id=x.quest_id AND m.ts=x.t""")
    opened = []
    for r in rows:
        if r["quest_id"] in cfg.mission_ignore:
            continue
        opens_at = r["ts"] + r["cooldown"]
        if now - DAY < opens_at <= now and db.should_alert(
                f"mo:{r['quest_id']}:{int(opens_at // HOUR)}", 2 * DAY, now):
            line = "• " + _mission_text(db, r)
            if r["quest_id"] == cfg.maint_mission_id:
                p = maintenance.predicted(db, cfg, now)
                if p is not None:
                    line += "\n   " + t("mines_now", pct=f"{100 * p:.1f}")
            opened.append(line)
    return [t("ms_opened") + "\n" + "\n".join(opened)] if opened else []


def missions_deadline(db: Database, cfg, now: int) -> list[str]:
    ts = db.latest_ts("missions_hist")
    if not ts:
        return []
    out = []
    for r in db.q("SELECT * FROM missions_hist WHERE ts=? AND endtime>? AND progress<goal",
                  (ts, now)):
        left = (r["endtime"] - now) / HOUR
        if left < cfg.mission_deadline_h and db.should_alert(
                f"mdl:{r['quest_id']}:{int(r['endtime'])}", DAY, now):
            out.append(t("ms_deadline", title=esc(r["title"]), t=hours(left), progress=num(r["progress"]),
                         goal=num(r["goal"]), penalty=num(r["penalty"])))
    return out


def maintenance_due(db: Database, cfg, now: int) -> list[str]:
    """Called after a mines fetch that found no maintenance."""
    s = maintenance.state_at(db)
    m = db.one("SELECT * FROM missions_hist WHERE quest_id=? ORDER BY ts DESC LIMIT 1",
               (cfg.maint_mission_id,))
    msg = t("maint", avg=f"{100 * s.avg_condition:.1f}", min=f"{100 * s.min_condition:.1f}")
    if m:
        opens_at = m["ts"] + m["cooldown"]
        if opens_at > now:
            msg += "\n" + t("maint_wait", when=clock(opens_at), t=hours((opens_at - now) / HOUR))
        else:
            msg += "\n" + t("maint_open")
    return [msg]


# ---------------------------------------------------------------- daily report
def daily_report(db: Database, cfg, now: int, credits_left=None, force=False) -> list[str]:
    today = datetime.fromtimestamp(now).strftime("%Y-%m-%d")
    if not force and (datetime.fromtimestamp(now).hour < cfg.daily_report_hour
                      or db.get_meta("last_report") == today):
        return []
    p = db.one("SELECT * FROM player_hist ORDER BY ts DESC LIMIT 1")
    if not p:
        return []
    db.set_meta("last_report", today)
    lines = [t("rep_head", user=esc(p["username"])),
             t("rep_line", lvl=p["lvl"], rank=f"{p['rank']:,}", points=num(p["points"]))]
    for label, ago in (("24h", DAY), ("7d", 7 * DAY)):
        o = db.one("SELECT * FROM player_hist WHERE ts<=? ORDER BY ts DESC LIMIT 1", (now - ago + HOUR,))
        if o and o["ts"] < p["ts"]:
            lines.append(t("rep_delta", label=label, points=num(p["points"] - o["points"]),
                           rank=f"{o['rank'] - p['rank']:+,}"))

    money = db.one("SELECT date, SUM(revenues) r, SUM(expenditures) e FROM money_daily "
                   "GROUP BY date ORDER BY date DESC LIMIT 1")
    if money:
        lines.append(t("rep_money", date=f"{datetime.fromtimestamp(money['date']):%d.%m}",
                       rev=num(money["r"]), exp=num(money["e"]), net=num(money["r"] - money["e"])))

    prices, stock = db.latest_prices(), db.latest_stock()
    value = sum(a * prices.get(iid, (0, 0))[0] for iid, (a, _) in stock.items())
    lines.append(t("rep_stock", v=num(value)))

    pred = maintenance.predicted(db, cfg, now)
    if pred is not None:
        lines.append(t("rep_cond", pct=f"{100 * pred:.1f}"))

    ts = db.latest_ts("missions_hist")
    if ts:
        soon = db.q("SELECT * FROM missions_hist WHERE ts=? AND cooldown>0 ORDER BY cooldown", (ts,))
        soon = [r for r in soon if r["quest_id"] not in cfg.mission_ignore
                and ts + r["cooldown"] < now + DAY]
        if soon:
            lines.append("\n" + t("rep_soon"))
            lines += [f"• {clock(r['ts'] + r['cooldown'])} {esc(r['title'])}" for r in soon]

    used = db.credits_used_since(now - DAY)
    lines.append("\n" + t("rep_credits", used=used) +
                 (t("rep_left", n=credits_left) if credits_left is not None else ""))
    return ["\n".join(lines)]
