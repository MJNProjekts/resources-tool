"""All settings come from .env (see .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _ids(s: str) -> set[int]:
    return {int(x) for x in s.replace(" ", "").split(",") if x}


@dataclass
class Config:
    api_key: str = ""
    lang: str = "en"          # language of item names from the API
    ui_lang: str = "en"       # language of Telegram messages: en | lv
    db_path: str = "resources.db"
    tg_token: str = ""
    tg_chat: str = ""

    # credits
    min_credits: int = 20
    daily_budget: int = 40
    tick_minutes: int = 10

    # alerts
    warehouse_alert_h: float = 6
    price_alert_pct: float = 15
    market_premium_pct: float = 8
    price_min_stock_value: float = 10e9
    mission_deadline_h: float = 6
    mission_ignore: set = field(default_factory=lambda: {41, 42, 56})
    # items you use yourself, never suggested for selling:
    # maintenance kit, TU1-4, giant diamond, troops, HR items, drones, detectors, archaeologists
    market_ignore: set = field(default_factory=lambda: {
        42, 43, 44, 45, 46, 48, 96, 98, 99, 103, 104, 117, 120, 159, 160, 161, 166, 167})
    market_top_n: int = 5
    daily_report_hour: int = 20

    # mines maintenance prediction
    maint_check_level: float = 0.93      # fetch mines when predicted condition hits this
    maint_decay_per_day: float = 0.04    # starting guess, refined from real data
    maint_mission_id: int = 38

    # warehouse capacity = cap_a * level ^ cap_b (measured in the app)
    cap_a: float = 5000
    cap_b: float = 2

    def capacity(self, level: int) -> float:
        return self.cap_a * level ** self.cap_b

    @classmethod
    def from_env(cls) -> "Config":
        e = os.environ.get
        c = cls()
        c.api_key = e("RG_API_KEY", "")
        c.lang = e("RG_LANG") or c.lang
        c.ui_lang = (e("UI_LANG") or c.ui_lang).lower()
        c.db_path = e("DB_PATH") or c.db_path
        c.tg_token = e("TELEGRAM_BOT_TOKEN", "")
        c.tg_chat = e("TELEGRAM_CHAT_ID", "")
        for name, attr, conv in [
            ("MIN_CREDITS", "min_credits", int), ("DAILY_CREDIT_BUDGET", "daily_budget", int),
            ("TICK_MINUTES", "tick_minutes", int),
            ("WAREHOUSE_ALERT_HOURS", "warehouse_alert_h", float),
            ("PRICE_ALERT_PCT", "price_alert_pct", float),
            ("MARKET_PREMIUM_PCT", "market_premium_pct", float),
            ("PRICE_MIN_STOCK_VALUE", "price_min_stock_value", float),
            ("MISSION_DEADLINE_HOURS", "mission_deadline_h", float),
            ("DAILY_REPORT_HOUR", "daily_report_hour", int),
            ("MAINT_CHECK_LEVEL", "maint_check_level", float),
            ("MAINT_DECAY_PER_DAY", "maint_decay_per_day", float),
            ("WAREHOUSE_CAP_A", "cap_a", float), ("WAREHOUSE_CAP_B", "cap_b", float),
        ]:
            if e(name):
                setattr(c, attr, conv(e(name)))
        if e("MARKET_IGNORE") is not None:
            c.market_ignore = _ids(e("MARKET_IGNORE"))
        if e("MISSION_IGNORE") is not None:
            c.mission_ignore = _ids(e("MISSION_IGNORE"))
        return c
