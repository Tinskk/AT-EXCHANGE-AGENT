"""Reads/writes data/rates.json — the single source of truth for current
buy/sell rates. Kept as a plain JSON file (not a DB table) so the owner's
`setrate` command is a trivial read-modify-write, and so the file can also be
hand-edited directly if ever needed.

Rates are stored as free-form strings (not floats) deliberately: crypto rates
are a number in a fiat currency, but gift card rates are usually a percentage
of face value, and both need a human-readable "not set yet" placeholder —
forcing a single numeric type would fight all three.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import config

_PLACEHOLDER = "TBD"


def _load() -> dict:
    if not config.RATES_PATH.exists():
        return {}
    return json.loads(config.RATES_PATH.read_text(encoding="utf-8"))


def _save(data: dict) -> None:
    config.RATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.RATES_PATH.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def get_rate(asset: str) -> dict | None:
    data = _load()
    for key, value in data.items():
        if key.lower() == asset.strip().lower():
            return {"asset": key, **value}
    return None


def list_rates() -> dict:
    return _load()


def set_rate(asset: str, buy: str, sell: str) -> dict:
    data = _load()
    # Match an existing key case-insensitively so `setrate usdt ...` updates
    # the "USDT" entry instead of creating a duplicate "usdt" one.
    existing_key = next((k for k in data if k.lower() == asset.strip().lower()), None)
    key = existing_key or asset.strip()
    data[key] = {
        "buy": buy,
        "sell": sell,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _save(data)
    return {"asset": key, **data[key]}


def is_placeholder(value: str | None) -> bool:
    return not value or value.strip().upper() == _PLACEHOLDER
