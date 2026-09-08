"""Reads/writes data/payment_methods.json — where AT Exchange itself receives
money or assets from a customer. Kept separate from rates.py: rates answer
"what's the price", this answers "where does it physically go" — a customer
buying pays fiat to receive_fiat_for_buys; a customer selling crypto sends it
to the matching entry in receive_crypto_for_sells; a customer selling a gift
card is told to send the code/photo in-chat rather than to any address.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import config

_PLACEHOLDER = "TBD"


def _load() -> dict:
    if not config.PAYMENT_METHODS_PATH.exists():
        return {}
    return json.loads(config.PAYMENT_METHODS_PATH.read_text(encoding="utf-8"))


def _save(data: dict) -> None:
    config.PAYMENT_METHODS_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.PAYMENT_METHODS_PATH.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def get_payment_instructions(direction: str, asset: str) -> dict:
    """Where the customer should pay/send to for this side of the trade.

    direction='buy' -> our fiat-receiving details (they're paying us).
    direction='sell' -> our crypto wallet for that asset if it's a known
    crypto symbol, otherwise the generic gift-card submission instructions.
    """
    data = _load()
    if direction == "buy":
        info = data.get("receive_fiat_for_buys", {})
        return {"pay_to": info, "is_placeholder": _has_placeholder(info)}

    crypto_entries = data.get("receive_crypto_for_sells", {})
    match = next((v for k, v in crypto_entries.items() if k.lower() == asset.strip().lower()), None)
    if match:
        return {"send_to": match, "is_placeholder": _has_placeholder(match)}

    gift_card_info = data.get("receive_gift_cards_for_sells", {})
    return {"send_to": gift_card_info, "is_placeholder": _has_placeholder(gift_card_info)}


def list_payment_methods() -> dict:
    return _load()


def set_fiat_receiving_details(bank_name: str, account_name: str, account_number: str) -> dict:
    data = _load()
    data["receive_fiat_for_buys"] = {
        "method": "bank transfer",
        "bank_name": bank_name,
        "account_name": account_name,
        "account_number": account_number,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _save(data)
    return data["receive_fiat_for_buys"]


def set_crypto_receiving_address(asset: str, network: str, address: str) -> dict:
    data = _load()
    crypto_entries = data.setdefault("receive_crypto_for_sells", {})
    existing_key = next((k for k in crypto_entries if k.lower() == asset.strip().lower()), None)
    key = existing_key or asset.strip()
    crypto_entries[key] = {
        "network": network,
        "address": address,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _save(data)
    return {"asset": key, **crypto_entries[key]}


def _has_placeholder(info: dict) -> bool:
    if not info:
        return True
    return any(str(v).strip().upper() == _PLACEHOLDER for v in info.values() if isinstance(v, str))
