"""Mine condition model.

Condition drops at a steady rate (about 4 %/day, refined from real data), so
instead of fetching all mines every day we predict the condition and fetch
only when the prediction reaches the check level.
"""

from __future__ import annotations

from dataclasses import dataclass

from .db import Database

DAY = 86400


@dataclass
class MineState:
    ts: int                 # when q=5 was fetched
    avg_condition: float
    min_condition: float
    last_maint: int         # newest lastmaintenance across mines
    count: int


def state_at(db: Database, ts: int | None = None) -> MineState | None:
    if ts is None:
        ts = db.latest_ts("mines_hist")
    if not ts:
        return None
    r = db.one("SELECT AVG(condition) a, MIN(condition) m, MAX(lastmaintenance) lm, COUNT(*) n "
               "FROM mines_hist WHERE ts=?", (ts,))
    return MineState(ts, r["a"], r["m"], r["lm"], r["n"])


def decay_per_day(db: Database, cfg) -> float:
    return float(db.get_meta("maint_decay_per_day", cfg.maint_decay_per_day))


def predicted(db: Database, cfg, now: int) -> float | None:
    s = state_at(db)
    if not s:
        return None
    return s.avg_condition - decay_per_day(db, cfg) * (now - s.ts) / DAY


def needs_fetch(db: Database, cfg, now: int) -> bool:
    """Fetch mines when the predicted condition reaches the check level,
    but not more often than every 12 h."""
    s = state_at(db)
    if not s:
        return True
    if now - s.ts < 12 * 3600:
        return False
    p = predicted(db, cfg, now)
    return p is not None and p <= cfg.maint_check_level


def after_fetch(db: Database, cfg, prev: MineState | None, new: MineState) -> dict:
    """Calibrate the decay rate and decide whether to warn.

    Returns {'maintained': bool, 'warn': bool}.
    """
    if not prev:
        return {"maintained": False, "warn": False}
    maintained = new.last_maint > prev.last_maint
    hrs = (new.ts - prev.ts) / 3600
    if not maintained and hrs >= 6:
        observed = (prev.avg_condition - new.avg_condition) / (hrs / 24)
        if 0 < observed < 0.5:
            old = decay_per_day(db, cfg)
            db.set_meta("maint_decay_per_day", round(0.5 * old + 0.5 * observed, 5))
    warn = (not maintained) and new.avg_condition <= cfg.maint_check_level + 0.005
    return {"maintained": maintained, "warn": warn}
