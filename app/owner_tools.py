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
            "Mark a lead confirmed and notify the customer it's being processed. "
            "Only call this on a lead ID you've verified via list_open_leads or get_lead — "
            "never guess an ID from the owner's description alone."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"lead_id": {"type": "string"}},
            "required": ["lead_id"],
        },
    },
    {
        "name": "complete_lead",
        "description": "Mark a lead completed and notify the customer the transaction is done.",
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
                "reason": {"type": "string", "description": "Why it's being rejected — this is sent to the customer verbatim."},
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
        "description": "Set the buy/sell rate for one asset (single-word asset names, e.g. 'BTC', 'USDT', 'Zelle').",
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
]

_CUSTOMER_MESSAGES = {
    "confirmed": "✅ Your transaction ({lead_id}) has been confirmed and is being processed.",
    "completed": "🎉 Your transaction ({lead_id}) has been completed. Thank you for using {business}!",
    "rejected": "❌ Your transaction ({lead_id}) could not be processed. Reason: {reason}",
}


def _notify_customer(lead: dict, status: str, reason: str | None = None) -> None:
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

    return {"error": f"unknown tool: {name}"}
