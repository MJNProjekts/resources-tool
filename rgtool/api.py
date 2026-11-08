"""Client for the RESOURCES data API (api.resources-game.ch).

Every query except q=0 costs one credit, so the client never retries.
The scheduler in collector.py decides what to fetch and when.
"""

from __future__ import annotations

import json
import re

import requests

BASE_URL = "https://api.resources-game.ch/"

QUERIES = {
    0: "credits", 1: "factories", 2: "warehouses", 3: "specialbuildings", 4: "hq_progress",
    5: "mines", 51: "mines_summary", 6: "trade_log", 7: "player_info", 8: "monetary_items",
    9: "attack_log", 10: "missions", 11: "maintenance_log", 12: "achievements",
    1001: "id_list", 1002: "item_production_base", 1003: "recycling_base",
    1004: "factory_upgrades", 1005: "specialbuilding_upgrades", 1006: "market_rates",
    1007: "troops", 2001: "luxury_auctions", 2002: "loan_statistics",
}


class APIError(Exception):
    """API problem. The message never contains the API key."""


class ResourcesAPI:
    def __init__(self, key: str, lang: str = "en", timeout: int = 30):
        if not key:
            raise APIError("API key missing - set RG_API_KEY in .env")
        self._key = key
        self.lang = lang
        self.timeout = timeout

    def query(self, q: int, days: int | None = None):
        params = {"q": q, "f": 1, "k": self._key, "l": self.lang}
        if days:
            params["d"] = max(1, min(int(days), 30))
        try:
            r = requests.get(BASE_URL, params=params, timeout=self.timeout)
        except requests.RequestException as e:
            raise APIError(f"network error on q={q}: {type(e).__name__}") from None
        if r.status_code != 200:
            raise APIError(f"HTTP {r.status_code} on q={q}")
        try:
            return r.json()
        except ValueError:
            snippet = r.text[:200].replace(self._key, "***")
            raise APIError(f"non-JSON answer on q={q}: {snippet!r}") from None

    def credits(self) -> int | None:
        """Credits left (free query)."""
        try:
            nums = re.findall(r"\d+", json.dumps(self.query(0)))
            return int(nums[-1]) if nums else None
        except APIError:
            return None
