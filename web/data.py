"""Builds the dashboard payload from the database. No API calls."""

from __future__ import annotations

import math
import time

from rgtool import maintenance
from rgtool.config import Config
from rgtool.db import Database

H = 3600
D = 24 * H
CREDITS_ID = 1
SPECB_MAX_LVL = 10


def _dist_m(lat1, lon1, lat2, lon2):
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def player(db: Database, now: int) -> dict:
    p = db.one("SELECT * FROM player_hist ORDER BY ts DESC LIMIT 1")
    if not p:
        return {}
    out = dict(p)
    for label, ago in (("d24", D), ("d7", 7 * D)):
        o = db.one("SELECT * FROM player_hist WHERE ts<=? ORDER BY ts DESC LIMIT 1", (p["ts"] - ago + H,))
        out[label] = ({"points": p["points"] - o["points"], "rank": o["rank"] - p["rank"]}
                      if o and o["ts"] < p["ts"] else None)
    out["history"] = [dict(r) for r in db.q("SELECT ts, points, rank FROM player_hist ORDER BY ts")]
    ts = db.latest_ts("warehouse_hist")
    cash = db.one("SELECT amount FROM warehouse_hist WHERE ts=? AND item_id=?", (ts, CREDITS_ID)) if ts else None
    out["cash"] = cash["amount"] if cash else None
    return out


def warehouse(db: Database, cfg: Config, now: int) -> list[dict]:
    ts = db.latest_ts("warehouse_hist")
    if not ts:
        return []
    prev = db.one("SELECT MAX(ts) t FROM warehouse_hist WHERE ts<=?", (ts - H,))
    old = {}
    if prev and prev["t"]:
        old = {r["item_id"]: (r["amount"], prev["t"]) for r in
               db.q("SELECT * FROM warehouse_hist WHERE ts=?", (prev["t"],))}
    prices = db.latest_prices()
    rows = []
    for r in db.q("SELECT w.*, i.name, i.icon_url FROM warehouse_hist w "
                  "LEFT JOIN items i ON i.item_id=w.item_id WHERE w.ts=? AND w.item_id<>?",
                  (ts, CREDITS_ID)):
        cap = cfg.capacity(r["level"]) if r["level"] else 0
        ki, bid = prices.get(r["item_id"], (0, 0))
        rate = left_h = None
        if r["item_id"] in old:
            a0, t0 = old[r["item_id"]]
            rate = (r["amount"] - a0) / ((ts - t0) / H)
            if rate > 0 and cap:
                left_h = max((cap - r["amount"]) / rate - (now - ts) / H, 0)
        rows.append({
            "id": r["item_id"], "name": r["name"] or f"#{r['item_id']}", "icon": r["icon_url"],
            "amount": r["amount"], "level": r["level"], "capacity": cap,
            "fill": r["amount"] / cap if cap else None, "rate": rate, "left_h": left_h,
            "ki": ki, "bid": bid, "premium": (bid / ki - 1) if bid and ki else None,
            "value": r["amount"] * ki,
        })
    rows.sort(key=lambda x: -x["value"])
    return rows


def mines(db: Database, cfg: Config, now: int) -> dict:
    prices = db.latest_prices()
    hq = db.one("SELECT * FROM hq WHERE id=1")
    items = [dict(r) for r in db.q("SELECT * FROM mines WHERE active=1")]
    for m in items:
        m["value_h"] = m["fullrate"] * prices.get(m["resource_id"], (0, 0))[0]
        if hq:
            m["dist_hq"] = _dist_m(hq["lat"], hq["lon"], m["lat"], m["lon"])
    by_res = {}
    for m in items:
        g = by_res.setdefault(m["resource_name"], {
            "resource": m["resource_name"], "resource_id": m["resource_id"], "count": 0, "in_hq": 0,
            "rate": 0.0, "value_h": 0.0, "q_sum": 0.0, "c_sum": 0.0})
        g["count"] += 1
        g["in_hq"] += m["hq_boost"] >= 10
        g["rate"] += m["fullrate"]
        g["value_h"] += m["value_h"]
        g["q_sum"] += m["quality"]
        g["c_sum"] += m["condition"]
    summary = []
    for g in by_res.values():
        g["quality"] = g.pop("q_sum") / g["count"]
        g["condition"] = g.pop("c_sum") / g["count"]
        g["value_per_mine"] = g["value_h"] / g["count"]
        summary.append(g)
    # factory demand per raw resource at full load, and who needs it
    need = {}
    for f in db.q("SELECT f.name, f.lvl, r.item_id, r.base_out_h, r.out_per_cycle FROM factories f "
                  "JOIN recipes r ON r.factory_id=f.factory_id"):
        cyc = f["lvl"] * f["base_out_h"] / f["out_per_cycle"]
        for i in db.q("SELECT * FROM recipe_inputs WHERE item_id=?", (f["item_id"],)):
            n = need.setdefault(i["input_id"], {"need_h": 0.0, "users": []})
            n["need_h"] += i["qty_per_cycle"] * cyc
            n["users"].append({"name": f["name"], "need_h": i["qty_per_cycle"] * cyc})
    ts = db.latest_ts("missions_hist")
    mission_h = {}
    if ts:
        for m in db.q("SELECT * FROM missions_hist WHERE ts=? AND interval_days>0 AND reward_item>0", (ts,)):
            if m["quest_id"] not in cfg.mission_ignore:
                mission_h[m["reward_item"]] = mission_h.get(m["reward_item"], 0) + m["reward_amt"] / (m["interval_days"] * 24)
    # raw resources = anything a mine type produces (known from mines) or ends in "Ore"
    raw_ids = {g["resource_id"] for g in summary}
    for iid in need:
        name = db.item_name(iid)
        if iid not in raw_ids and (name.endswith(" Ore") or name in ("Rough Diamonds", "Crude Oil", "Coal", "Clay",
                "Gravel", "Limestone", "Bauxite", "Quartz Sand", "Chalcopyrite", "Wolframite", "Ilmenite")):
            summary.append({"resource": name, "resource_id": iid, "count": 0, "in_hq": 0, "rate": 0.0,
                            "value_h": 0.0, "quality": None, "condition": None, "value_per_mine": None})
    for g in summary:
        n = need.get(g["resource_id"])
        g["need_h"] = n["need_h"] if n else 0.0
        g["users"] = sorted(n["users"], key=lambda u: -u["need_h"]) if n else []
        g["missions_h"] = mission_h.get(g["resource_id"], 0.0)
        g["coverage"] = (g["rate"] + g["missions_h"]) / g["need_h"] if g["need_h"] else None
        per_mine = g["rate"] / g["count"] if g["count"] else None
        missing = g["need_h"] - g["rate"] - g["missions_h"]
        g["mines_missing"] = (missing / per_mine) if (per_mine and missing > 0) else None
    summary.sort(key=lambda g: -g["value_h"])
    hq_radius = max((m["dist_hq"] for m in items if m["hq_boost"] >= 10 and "dist_hq" in m), default=None)
    state = maintenance.state_at(db)
    return {
        "items": items, "summary": summary,
        "hq": {"lat": hq["lat"], "lon": hq["lon"], "lvl": hq["lvl"], "radius_est": hq_radius} if hq else None,
        "total_value_h": sum(m["value_h"] for m in items),
        "count": len(items), "in_hq": sum(1 for m in items if m["hq_boost"] >= 10),
        "condition_pred": maintenance.predicted(db, cfg, now),
        "condition_measured": state.avg_condition if state else None,
        "condition_ts": state.ts if state else None,
        "decay_per_day": maintenance.decay_per_day(db, cfg),
    }


def buy_transport(db: Database) -> float:
    """Share of the purchase value paid as transport. Measured from your own
    buy trades (the buyer pays transport), fallback 9 %."""
    r = db.one("SELECT AVG(transcost / (amount * ppstk)) t, COUNT(*) n FROM trades "
               "WHERE event='buy' AND amount>0 AND ppstk>0")
    return r["t"] if r and r["n"] >= 3 else 0.09


HORIZON_DAYS = 30


def production_model(db: Database, cfg: Config, horizon_days: float = HORIZON_DAYS,
                     levels: dict | None = None) -> dict:
    """Average load of every factory over the next `horizon_days`.

    Inflow per item = mines + mission rewards (if done every time) + output of
    the factories that make it (at their own load) + current stock spread over
    the horizon. When several factories need the same item and there is not
    enough, it is shared in proportion to what each one uses.
    Solved by damped fixed-point iteration.
    """
    facs = {}
    for f in db.q("SELECT f.factory_id, f.lvl, r.item_id, r.base_out_h, r.out_per_cycle FROM factories f "
                  "JOIN recipes r ON r.factory_id=f.factory_id"):
        lvl = (levels or {}).get(f["factory_id"], f["lvl"])
        out_h = lvl * f["base_out_h"]
        cyc = out_h / f["out_per_cycle"]
        facs[f["factory_id"]] = {
            "product": f["item_id"], "out_h": out_h,
            "need": {i["input_id"]: i["qty_per_cycle"] * cyc
                     for i in db.q("SELECT * FROM recipe_inputs WHERE item_id=?", (f["item_id"],))}}
    base = {}
    def add(iid, src, v):
        base.setdefault(iid, {"mines": 0.0, "missions": 0.0, "stock": 0.0})[src] += v
    for r in db.q("SELECT resource_id, SUM(fullrate) r FROM mines WHERE active=1 GROUP BY resource_id"):
        add(r["resource_id"], "mines", r["r"])
    ts = db.latest_ts("missions_hist")
    if ts:
        for m in db.q("SELECT * FROM missions_hist WHERE ts=? AND interval_days>0 AND reward_item>0", (ts,)):
            if m["quest_id"] not in cfg.mission_ignore:
                add(m["reward_item"], "missions", m["reward_amt"] / (m["interval_days"] * 24))

    for iid, (amount, _) in db.latest_stock().items():
        add(iid, "stock", amount / (horizon_days * 24))

    loads = {fid: 1.0 for fid in facs}
    ratio = {}
    # Proportional sharing: each consumer of item X asks for what it could use
    # given its OTHER inputs; X is split in proportion to those requests.
    # Producers' output depends on their own load, so iterate to a fixed point.
    ratio = {}
    for _ in range(300):
        made = {}
        for fid, f in facs.items():
            made[f["product"]] = made.get(f["product"], 0) + f["out_h"] * loads[fid]
        demand = {}
        for fid, f in facs.items():
            for iid, n in f["need"].items():
                others = [ratio.get(j, 1) for j in f["need"] if j != iid]
                demand[iid] = demand.get(iid, 0) + n * min([1.0] + others)
        supply = {iid: sum(base.get(iid, {}).values()) + made.get(iid, 0) for iid in demand}
        ratio = {iid: (min(supply[iid] / demand[iid], 1) if demand[iid] > 1e-9 else 1) for iid in demand}
        new = {fid: min([1.0] + [ratio[i] for i in f["need"]]) for fid, f in facs.items()}
        delta = max(abs(new[k] - loads[k]) for k in facs) if facs else 0
        loads = {fid: 0.5 * loads[fid] + 0.5 * new[fid] for fid in facs}
        if delta < 1e-7:
            break
    made = {}
    for fid, f in facs.items():
        made[f["product"]] = made.get(f["product"], 0) + f["out_h"] * loads[fid]
    items = {}
    for iid in set(base) | set(made) | {i for f in facs.values() for i in f["need"]}:
        items[iid] = {"mines": base.get(iid, {}).get("mines", 0.0),
                      "missions": base.get(iid, {}).get("missions", 0.0),
                      "stock": base.get(iid, {}).get("stock", 0.0),
                      "factories": made.get(iid, 0.0),
                      "demand": sum(f["need"].get(iid, 0) for fid, f in facs.items()),
                      "ratio": ratio.get(iid, 1)}
    return {"loads": loads, "items": items}


def factories(db: Database, cfg: Config, now: int) -> list[dict]:
    """Per factory, all per hour:
    gain_full  processing gain at full load vs selling the inputs to the KI-market
    load       share of time the inputs last, from steady inflow (mines, other
               factories, mission rewards) minus what other factories use
    gain_real  gain_full * load
    buy_full   profit at full load if every input is bought (market price + transport)
    """
    prices = db.latest_prices()
    stock = db.latest_stock()
    model = production_model(db, cfg)
    t = buy_transport(db)
    out = []
    for f in db.q("SELECT f.*, r.item_id product_id, r.base_out_h, r.out_per_cycle, r.credits_per_cycle "
                  "FROM factories f LEFT JOIN recipes r ON r.factory_id=f.factory_id"):
        row = {"id": f["factory_id"], "name": f["name"], "lvl": f["lvl"], "strike": f["strike"],
               "product": db.item_name(f["product_id"]) if f["product_id"] else None}
        if not (f["product_id"] and f["out_per_cycle"]):
            out.append(row)
            continue
        out_h = f["lvl"] * f["base_out_h"]
        cycles_h = out_h / f["out_per_cycle"]
        revenue = f["out_per_cycle"] * prices.get(f["product_id"], (0, 0))[0]
        cost_ai = cost_buy = f["credits_per_cycle"]
        inputs = []
        for i in db.q("SELECT * FROM recipe_inputs WHERE item_id=?", (f["product_id"],)):
            iid, qty = i["input_id"], i["qty_per_cycle"]
            ki, rate = prices.get(iid, (0, 0))
            buy_price = (rate or ki) * (1 + t)
            cost_ai += qty * ki
            cost_buy += qty * buy_price
            need_h = qty * cycles_h
            s = model["items"].get(iid, {"mines": 0, "factories": 0, "missions": 0, "stock": 0,
                                         "demand": 0, "ratio": 1})
            have = stock.get(iid, (0, 0))[0]
            inputs.append({
                "id": iid, "name": db.item_name(iid), "qty": qty, "need_h": need_h, "have": have,
                "hours_of_stock": have / need_h if need_h else None,
                "from_mines": s["mines"], "from_factories": s["factories"],
                "from_missions": s["missions"], "from_stock": s.get("stock", 0),
                "demand_total": s["demand"], "ratio": s["ratio"],
                "ki": ki, "buy_price": buy_price, "cycle_cost": qty * buy_price,
            })
        gain_full = (revenue - cost_ai) * cycles_h
        buy_all = (revenue - cost_buy) * cycles_h
        load = model["loads"].get(f["factory_id"], 1.0)
        limiting = min(inputs, key=lambda x: x["ratio"]) if inputs and load < 0.999 else None
        # the input you would actually buy: the limiting one, else the most expensive one
        buy = limiting or (max(inputs, key=lambda x: x["qty"] * x["ki"]) if inputs else None)
        buy_one = None
        if buy:
            market = buy["buy_price"] / (1 + t)          # price before transport
            own_rest = cost_ai - buy["qty"] * buy["ki"]   # other inputs valued at KI-market price
            buy_one = (revenue - own_rest - buy["qty"] * buy["buy_price"]) * cycles_h
            buy.update({
                "market_price": market,
                # highest price (before transport) at which buying this input still pays off
                "break_even": max((revenue - own_rest) / buy["qty"] / (1 + t), 0),
                "profit_buy_full": buy_one,
                "extra_if_topped_up": max(buy_one, 0) * (1 - load) if limiting else 0,
            })
        row.update({
            "out_h": out_h, "load": load, "gain_full": gain_full, "gain_real": gain_full * load,
            "margin_pct": (revenue / cost_ai - 1) if cost_ai else None,
            "buy_all": buy_all, "buy_all_pct": (revenue / cost_buy - 1) if cost_buy else None,
            "buy": buy, "limiting": limiting, "inputs": inputs,
            "bottleneck": min(inputs, key=lambda x: x["hours_of_stock"] or 1e18) if inputs else None,
        })
        out.append(row)
    out.sort(key=lambda r: -(r.get("gain_real") or -1e18))
    return out


def specbuildings(db: Database) -> list[dict]:
    stock = db.latest_stock()
    cash_ts = db.latest_ts("warehouse_hist")
    cash = db.one("SELECT amount FROM warehouse_hist WHERE ts=? AND item_id=?", (cash_ts, CREDITS_ID))
    cash = cash["amount"] if cash else 0
    out = []
    for s in db.q("SELECT s.*, u.base_cost FROM specbuildings s "
                  "LEFT JOIN specb_upgrades u ON u.specb_id=s.specb_id ORDER BY s.lvl, s.name"):
        row = {"id": s["specb_id"], "name": s["name"], "lvl": s["lvl"], "max": s["lvl"] >= SPECB_MAX_LVL}
        if not row["max"] and s["base_cost"]:
            t = s["lvl"] + 1
            needs = [{"name": "__cash__", "need": s["base_cost"] * t * t, "have": cash}]
            for it in db.q("SELECT * FROM specb_upgrade_items WHERE specb_id=?", (s["specb_id"],)):
                needs.append({"name": db.item_name(it["item_id"]), "need": it["qty"] * t * t,
                              "have": stock.get(it["item_id"], (0, 0))[0]})
            prices = db.latest_prices()
            missing_value = 0.0
            for n, it in zip(needs[1:], db.q("SELECT * FROM specb_upgrade_items WHERE specb_id=?",
                                             (s["specb_id"],))):
                missing_value += max(n["need"] - n["have"], 0) * prices.get(it["item_id"], (0, 0))[0]
            row.update({"target": t, "needs": needs, "missing_value": missing_value,
                        "ready": all(n["have"] >= n["need"] for n in needs)})
        out.append(row)
    return out


def missions(db: Database, cfg: Config, now: int) -> list[dict]:
    ts = db.latest_ts("missions_hist")
    if not ts:
        return []
    out = []
    for r in db.q("SELECT * FROM missions_hist WHERE ts=?", (ts,)):
        if r["quest_id"] in cfg.mission_ignore:
            continue
        opens_at = ts + r["cooldown"] if r["cooldown"] > 0 else None
        state = "open" if not opens_at or opens_at <= now else "waiting"
        if r["endtime"] and r["endtime"] > now:
            state = "active"
        out.append({
            "id": r["quest_id"], "title": r["title"],
            "descr": str(r["descr"] or "").replace("{}", f"{r['goal']:,.0f}"),
            "state": state, "opens_at": opens_at, "ends_at": r["endtime"] if r["endtime"] > now else None,
            "progress": r["progress"], "goal": r["goal"], "penalty": r["penalty"],
            "reward": f"{r['reward_amt']:,.0f} × {db.item_name(r['reward_item'])}" if r["reward_item"] else "",
        })
    order = {"active": 0, "open": 1, "waiting": 2}
    out.sort(key=lambda m: (order[m["state"]], m["opens_at"] or 0))
    return out


def money(db: Database) -> dict:
    days = [dict(r) for r in db.q(
        "SELECT date, SUM(revenues) rev, SUM(expenditures) exp FROM money_daily "
        "GROUP BY date ORDER BY date")]
    cats = [dict(r) for r in db.q(
        "SELECT name, SUM(revenues) rev, SUM(expenditures) exp FROM money_daily "
        "GROUP BY name ORDER BY SUM(revenues)+SUM(expenditures) DESC")]
    items = [dict(r) for r in db.q(
        "SELECT date, name, SUM(revenues) rev, SUM(expenditures) exp FROM money_daily "
        "GROUP BY date, name ORDER BY date")]
    return {"days": days, "categories": cats, "items": items}


def recycling(db: Database) -> dict:
    """What each recyclable gives (API base x Recycling Plant level) and whether
    recycling beats selling, at KI-market prices."""
    r = db.one("SELECT lvl FROM specbuildings WHERE name LIKE 'Recycling%'")
    mult = r["lvl"] if r and r["lvl"] else 1
    prices = db.latest_prices()
    stock = db.latest_stock()
    used_by = {}
    for x in db.q("SELECT ri.input_id, f.name FROM recipe_inputs ri JOIN recipes r ON r.item_id=ri.item_id "
                  "JOIN factories f ON f.factory_id=r.factory_id"):
        used_by.setdefault(x["input_id"], []).append(x["name"])
    rows = []
    for rc in db.q("SELECT * FROM recycling"):
        iid, qty = rc["item_id"], rc["input_qty"]
        ki, bid = prices.get(iid, (0, 0))
        sell = qty * ki
        outs, value_out = [], 0.0
        for o in db.q("SELECT * FROM recycling_outputs WHERE item_id=?", (iid,)):
            q = o["qty"] * mult
            p = prices.get(o["out_id"], (0, 0))[0]
            value_out += q * p
            outs.append({"id": o["out_id"], "name": db.item_name(o["out_id"]), "qty": q, "value": q * p,
                         "used_by": used_by.get(o["out_id"], [])})
        have = stock.get(iid, (0, 0))[0]
        batches = int(have // qty) if qty else 0
        rows.append({
            "id": iid, "name": rc["name"] or db.item_name(iid), "qty": qty, "outputs": outs,
            "sell_value": sell, "recycle_value": value_out, "bid": bid, "ki": ki,
            "ratio": value_out / sell if sell else None,
            "stock": have, "batches": batches,
            "gain_all": (value_out - sell) * batches,
            "out_all": [{"name": o["name"], "qty": o["qty"] * batches} for o in outs],
        })
        if len(outs) == 1 and outs[0]["name"].startswith("Tech Upgrade"):
            o = outs[0]
            rows[-1]["per_unit"] = {"name": o["name"], "via": sell / o["qty"],
                                    "market": prices.get(o["id"], (0, 0))[0]}
    rows.sort(key=lambda x: -(x["ratio"] or 0))
    return {"multiplier": mult, "items": rows}


STEADY = 1e6  # horizon (days) that makes current stock irrelevant: long-run payback


def _factory_gains(db: Database, cfg: Config, levels: dict | None = None) -> dict:
    """Long-run processing gain per hour of every factory (KI-market prices, real load)."""
    prices = db.latest_prices()
    model = production_model(db, cfg, STEADY, levels)
    out = {}
    for f in db.q("SELECT f.factory_id, f.lvl, r.item_id, r.base_out_h, r.out_per_cycle, r.credits_per_cycle "
                  "FROM factories f JOIN recipes r ON r.factory_id=f.factory_id"):
        lvl = (levels or {}).get(f["factory_id"], f["lvl"])
        cyc = lvl * f["base_out_h"] / f["out_per_cycle"]
        cost = f["credits_per_cycle"] + sum(i["qty_per_cycle"] * prices.get(i["input_id"], (0, 0))[0]
                                            for i in db.q("SELECT * FROM recipe_inputs WHERE item_id=?", (f["item_id"],)))
        rev = f["out_per_cycle"] * prices.get(f["item_id"], (0, 0))[0]
        out[f["factory_id"]] = (rev - cost) * cyc * model["loads"][f["factory_id"]]
    return out


def investments(db: Database, cfg: Config) -> dict:
    """Payback of the typical investments, at KI-market prices.

    Factory +1 level: cost = base * target^2 (+ items * target^2), checked against
    real upgrade expenses. Gain = change in total factory profit, so if the
    upgraded factory takes inputs from another one, that loss is included.
    Long run: current stock is ignored, mission rewards count as if done every time.
    """
    prices = db.latest_prices()
    ki = lambda iid: prices.get(iid, (0, 0))[0]
    base_gain = _factory_gains(db, cfg)
    total0 = sum(base_gain.values())
    fac = []
    for f in db.q("SELECT f.factory_id, f.name, f.lvl, u.base_cost FROM factories f "
                  "JOIN factory_upgrades u ON u.factory_id=f.factory_id"):
        t = f["lvl"] + 1
        items = [{"name": db.item_name(x["item_id"]), "qty": x["qty"] * t * t, "value": x["qty"] * t * t * ki(x["item_id"])}
                 for x in db.q("SELECT * FROM factory_upgrade_items WHERE factory_id=?", (f["factory_id"],))]
        cost = f["base_cost"] * t * t + sum(i["value"] for i in items)
        gains = _factory_gains(db, cfg, {f["factory_id"]: t})
        gain = sum(gains.values()) - total0
        own = gains[f["factory_id"]] - base_gain[f["factory_id"]] if f["factory_id"] in gains else 0
        fac.append({"name": f["name"], "lvl": f["lvl"], "target": t, "cash": f["base_cost"] * t * t,
                    "items": items, "cost": cost, "gain_h": gain, "own_gain_h": own,
                    "payback_days": cost / gain / 24 if gain > 0 else None})
    fac.sort(key=lambda x: x["payback_days"] if x["payback_days"] else 1e12)

    # TU set on one mine (your combination), cheapest source per TU level
    tu_set = {44: 135, 45: 2, 46: 8, 47: 0}
    tu_factor = 5.05
    via_coins = {44: 55, 45: 40}  # TU1 <- copper coins, TU2 <- roman coins
    rec = recycling(db)
    coin_cost = {}
    for r in rec["items"]:
        if r["id"] in via_coins.values() and r["outputs"]:
            o = r["outputs"][0]
            coin_cost[o["id"]] = r["sell_value"] / o["qty"]
    tu_price = {t: min(x for x in (ki(t), coin_cost.get(t)) if x) if (ki(t) or coin_cost.get(t)) else 0
                for t in tu_set}
    set_cost = sum(n * tu_price[t] for t, n in tu_set.items())
    tu = []
    for r in db.q("SELECT resource_id, resource_name, AVG(rawrate) raw, COUNT(*) n FROM mines WHERE active=1 "
                  "GROUP BY resource_id ORDER BY resource_name"):
        g1 = r["raw"] * (tu_factor - 1) * ki(r["resource_id"])
        tu.append({"resource": r["resource_name"], "mines": r["n"], "raw_h": r["raw"], "gain_1x": g1,
                   "gain_hq": g1 * 10, "payback_1x": set_cost / g1 / 24 if g1 else None,
                   "payback_hq": set_cost / g1 / 240 if g1 else None})
    tu.sort(key=lambda x: x["payback_1x"] or 1e12)
    return {
        "factories": fac, "tu": tu, "tu_set": {"TU1": 135, "TU2": 2, "TU3": 8}, "tu_set_cost": set_cost,
        "tu_prices": {f"TU{t - 43}": {"ki": ki(t), "coins": coin_cost.get(t)} for t in (44, 45, 46)},
    }


def achievements(db: Database) -> list[dict]:
    rows = db.q("SELECT * FROM achievements WHERE completed=0 ORDER BY reward_amt DESC")
    return [{"title": r["title"], "descr": r["descr"], "reward": r["reward_amt"],
             "reward_item": db.item_name(r["reward_item_id"]), "req": r["req_amt"]} for r in rows]


def actions(wh, mn, fac, sb, ms, now) -> list[dict]:
    """'What to do now' list, most urgent first. Texts are built in the page
    from `key` + params `p`, so they can be shown in any language."""
    out = []
    add = lambda level, key, **p: out.append({"level": level, "key": key, "p": p})
    for w in wh:
        if w["left_h"] is not None and w["left_h"] < 24:
            add("critical" if w["left_h"] < 6 else "warning", "wh_full", name=w["name"], h=w["left_h"])
        elif w["fill"] is not None and w["fill"] >= 0.95 and w["amount"] > 0:
            add("warning", "wh_pct", name=w["name"], pct=100 * w["fill"])
    for m in ms:
        if m["state"] == "active" and m["ends_at"] and m["progress"] < m["goal"]:
            add("critical" if m["ends_at"] - now < 6 * H else "warning", "mis_ends", title=m["title"],
                h=(m["ends_at"] - now) / H, progress=m["progress"], goal=m["goal"])
        elif m["opens_at"] and now < m["opens_at"] < now + 6 * H:
            add("info", "mis_opens", title=m["title"], h=(m["opens_at"] - now) / H)
    p = mn.get("condition_pred")
    if p is not None and p < 0.93:
        add("warning", "maint", pct=100 * p)
    for f in fac:
        if f.get("strike") not in (None, "no"):
            add("critical", "strike", name=f["name"])
        b = f.get("bottleneck")
        if b and b["hours_of_stock"] is not None and b["hours_of_stock"] < 1:
            add("info", "idle", name=f["name"], item=b["name"], full_b=f["gain_full"])
    tops = [f for f in fac if f.get("buy") and f["buy"].get("extra_if_topped_up", 0) > 50e6
            and f["buy"]["market_price"] <= f["buy"]["break_even"]]
    for f in sorted(tops, key=lambda f: -f["buy"]["extra_if_topped_up"])[:3]:
        b = f["buy"]
        add("info", "topup", name=f["name"], item=b["name"], price=b["market_price"],
            break_even=b["break_even"], gain_m=b["extra_if_topped_up"])
    for x in sb:
        if x.get("ready"):
            add("good", "upgrade", name=x["name"], lvl=x["target"])
    rank = {"critical": 0, "warning": 1, "good": 2, "info": 3}
    return sorted(out, key=lambda a: rank[a["level"]])


def status(db: Database, cfg: Config, credits_left=None, now: int | None = None) -> dict:
    """Is the collector running, and when was each kind of data last fetched."""
    now = now or int(time.time())
    hb = db.get_meta("heartbeat")
    hb = int(hb) if hb else None
    tick = int(db.get_meta("tick_minutes", cfg.tick_minutes))
    last = {str(q): {"ts": db.last_fetch(q)} for q in (2, 1006, 10, 7, 5, 1)}
    row = db.one("SELECT ts, q FROM fetch_log WHERE ok=1 AND credits>0 ORDER BY ts DESC LIMIT 1")
    return {
        "now": now, "heartbeat": hb, "tick_minutes": tick,
        "active": bool(hb and now - hb < 2 * tick * 60 + 120),
        "last_request": row["ts"] if row else None,
        "last": last, "credits_24h": db.credits_used_since(now - D), "credits_left": credits_left,
    }


def overview(db: Database, cfg: Config, now: int | None = None) -> dict:
    now = now or int(time.time())
    wh = warehouse(db, cfg, now)
    mn = mines(db, cfg, now)
    fac = factories(db, cfg, now)
    sb = specbuildings(db)
    ms = missions(db, cfg, now)
    pl = player(db, now)
    last = db.one("SELECT MAX(ts) t FROM fetch_log WHERE ok=1")
    return {
        "now": now, "last_fetch": last["t"] if last else None,
        "credits_24h": db.credits_used_since(now - D),
        "player": pl, "warehouse": wh, "mines": mn, "factories": fac, "specbuildings": sb,
        "missions": ms, "money": money(db), "achievements": achievements(db), "recycling": recycling(db),
        "investments": investments(db, cfg),
        "actions": actions(wh, mn, fac, sb, ms, now),
        "stock_value": sum(w["value"] for w in wh),
        "buy_transport": buy_transport(db), "horizon_days": HORIZON_DAYS,
    }
