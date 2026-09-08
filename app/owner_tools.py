"""Tool definitions exposed to the owner agent, and the dispatcher that
executes them.

Structurally the same idea as agent_tools.py: the LLM only ever decides
*what* to do — it never touches store.py/rates.py/whatsapp_client.py
directly, and every state change (a lead's status, a rate, a message to the
customer) happens in plain, deterministic Python here. That's what keeps a
conversational owner interface safe for a money-handling flow: the model can
misread which lead "that USDT order" refers to, but it can't invent a lead ID
or change a record without going through these functions and getting a real
result back to report.
"""

from __future__ import annotations

import payment_methods
import rates
import store
import whatsapp_client
from config import BUSINESS_NAME

TOOL_DEFS = [
    {
        "name": "list_open_leads",
        "description": (
            "List every lead that's still pending or confirmed (not yet completed/rejected). "
            "Call this first whenever the owner refers to a transaction by description rather "
            "than by exact lead ID (e.g. 'that USDT order', 'the Lagos customer's request') so "
            "you can find the real lead ID before acting on it."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_lead",
        "description": "Get full details for one lead by its ID (e.g. 'LD7' or '7').",
        "input_schema": {
            "type": "object",
            "properties": {"lead_id": {"type": "string"}},
            "required": ["lead_id"],
        },
    },
    {
        "name": "confirm_lead",
        "description": (
            "Mark a lead confirmed, meaning it's been reviewed and is being processed. "
            "Notifies the customer it's confirmed, nothing more. Only call this on a lead ID "
            "you've verified via list_open_leads or get_lead, never guess an ID from the "
            "owner's description alone."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"lead_id": {"type": "string"}},
            "required": ["lead_id"],
        },
    },
    {
        "name": "complete_lead",
        "description": (
            "Mark a lead completed. Use this once the owner has actually sent the money or "
            "the asset, not just approved the request. Notifies the customer they've been "
            "paid (if they were selling to us) or that their asset is on its way (if they "
            "were buying from us), based on the lead's direction."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"lead_id": {"type": "string"}},
            "required": ["lead_id"],
        },
    },
    {
        "name": "reject_lead",
        "description": "Mark a lead rejected and relay the reason to the customer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "lead_id": {"type": "string"},
                "reason": {"type": "string", "description": "Why it's being rejected. This gets sent to the customer as-is."},
            },
            "required": ["lead_id", "reason"],
        },
    },
    {
        "name": "get_rates",
        "description": "List every asset's current buy/sell rate.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "set_rate",
        "description": "Set the buy/sell rate for one asset (single-word asset names, e.g. 'BTC', 'USDT').",
        "input_schema": {
            "type": "object",
            "properties": {
                "asset": {"type": "string"},
                "buy": {"type": "string"},
                "sell": {"type": "string"},
            },
            "required": ["asset", "buy", "sell"],
        },
    },
    {
        "name": "get_payment_methods",
        "description": "List AT Exchange's current payment/receiving details — the bank account customers pay into for buys, and the crypto wallet addresses customers send to for sells.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "set_fiat_receiving_details",
        "description": "Set the bank account customers pay into when buying crypto/gift cards from us.",
        "input_schema": {
            "type": "object",
            "properties": {
                "bank_name": {"type": "string"},
                "account_name": {"type": "string"},
                "account_number": {"type": "string"},
            },
            "required": ["bank_name", "account_name", "account_number"],
        },
    },
    {
        "name": "set_crypto_receiving_address",
        "description": "Set our wallet address for receiving a crypto asset when a customer sells it to us (single-word asset name, e.g. 'BTC', 'USDT').",
        "input_schema": {
            "type": "object",
            "properties": {
                "asset": {"type": "string"},
                "network": {"type": "string", "description": "e.g. 'TRC20', 'ERC20', 'Bitcoin mainnet'"},
                "address": {"type": "string"},
            },
            "required": ["asset", "network", "address"],
        },
    },
]

_CUSTOMER_MESSAGES = {
    "confirmed": "✅ Your transaction ({lead_id}) has been confirmed and is being processed.",
    "rejected": "❌ Your transaction ({lead_id}) couldn't be processed. Reason: {reason}",
}

# "completed" is direction-aware: a sell means we paid the customer, a buy
# means we sent them their asset. Two different things to actually say.
_COMPLETED_MESSAGES = {
    "sell": "💸 You've been paid! Your {asset} transaction ({lead_id}) is complete. Thanks for using {business}.",
    "buy": "✅ Your {asset} is on its way! Transaction ({lead_id}) is complete. Thanks for using {business}.",
}


def _notify_customer(lead: dict, status: str, reason: str | None = None) -> None:
    if status == "completed":
        template = _COMPLETED_MESSAGES.get(lead["direction"], _COMPLETED_MESSAGES["sell"])
        text = template.format(lead_id=lead["lead_id"], business=BUSINESS_NAME, asset=lead["asset"])
    else:
        text = _CUSTOMER_MESSAGES[status].format(lead_id=lead["lead_id"], business=BUSINESS_NAME, reason=reason)
    whatsapp_client.send_text(lead["customer_phone"], text)


def _set_status(lead_id: str, status: str, notes: str | None = None) -> dict:
    lead = store.update_lead_status(lead_id, status, notes=notes)
    if not lead:
        return {"ok": False, "error": f"No lead found for '{lead_id}'."}
    _notify_customer(lead, status, reason=notes)
    return {"ok": True, "lead": lead, "customer_notified": True}


def dispatch(name: str, tool_input: dict) -> dict:
    if name == "list_open_leads":
        return {"leads": store.list_open_leads()}

    if name == "get_lead":
        lead = store.get_lead(tool_input["lead_id"])
        return {"lead": lead} if lead else {"ok": False, "error": f"No lead found for '{tool_input['lead_id']}'."}

    if name == "confirm_lead":
        return _set_status(tool_input["lead_id"], "confirmed")

    if name == "complete_lead":
        return _set_status(tool_input["lead_id"], "completed")

    if name == "reject_lead":
        return _set_status(tool_input["lead_id"], "rejected", notes=tool_input["reason"])

    if name == "get_rates":
        return {"rates": rates.list_rates()}

    if name == "set_rate":
        result = rates.set_rate(tool_input["asset"], tool_input["buy"], tool_input["sell"])
        return {"ok": True, "rate": result}

    if name == "get_payment_methods":
        return {"payment_methods": payment_methods.list_payment_methods()}

    if name == "set_fiat_receiving_details":
        result = payment_methods.set_fiat_receiving_details(
            tool_input["bank_name"], tool_input["account_name"], tool_input["account_number"]
        )
        return {"ok": True, "receive_fiat_for_buys": result}

    if name == "set_crypto_receiving_address":
        result = payment_methods.set_crypto_receiving_address(
            tool_input["asset"], tool_input["network"], tool_input["address"]
        )
        return {"ok": True, "receiving_address": result}

    return {"error": f"unknown tool: {name}"}
