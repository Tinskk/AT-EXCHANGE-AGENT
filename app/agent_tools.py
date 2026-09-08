"""Tool definitions exposed to Claude, and the dispatcher that executes them.

Kept deliberately minimal: four tools, each backed by real data (rates.json,
the leads table, or the knowledge base) so the model never has to invent a
rate, a policy, or a transaction status. The agent never moves money or
confirms a transaction itself — create_transaction_lead only ever creates a
pending record and pages the owner; a human always makes the actual call.
"""

from __future__ import annotations

import config
import knowledge_base
import rates
import store
import whatsapp_client

TOOL_DEFS = [
    {
        "name": "get_rate",
        "description": (
            "Look up the current buy/sell rate for an asset (a crypto symbol like "
            "BTC/USDT/ETH, a gift card brand like 'Amazon Gift Card', or 'Zelle'/"
            "'PayPal'). Always call this before quoting any rate — never state one "
            "from memory. If it returns a TBD/placeholder rate, tell the customer "
            "the team will confirm the exact rate for their request."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"asset": {"type": "string", "description": "e.g. 'BTC', 'USDT', 'Amazon Gift Card', 'Zelle'"}},
            "required": ["asset"],
        },
    },
    {
        "name": "create_transaction_lead",
        "description": (
            "Log a customer's transaction request as a pending lead and notify the "
            "owner for manual confirmation. Only call this after you've gathered "
            "the asset, direction (buy or sell), amount, payment method, and "
            "destination details, and the customer has confirmed they want to "
            "proceed. This never completes a transaction — it only creates a "
            "lead for the owner to review."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["sell", "buy"],
                    "description": (
                        "'sell' = the customer is selling/sending the asset to AT Exchange "
                        "in return for cash/payout. 'buy' = the customer is paying AT Exchange "
                        "to receive the asset."
                    ),
                },
                "asset": {"type": "string", "description": "e.g. 'BTC', 'USDT', 'Amazon Gift Card ($100)', 'Zelle', 'PayPal'"},
                "amount": {"type": "string", "description": "e.g. '500 USDT', '$200 Amazon gift card', '$150 via Zelle'"},
                "payment_method": {
                    "type": "string",
                    "description": "How the customer will pay or be paid, e.g. 'bank transfer', 'Zelle', 'PayPal', 'crypto wallet'",
                },
                "destination_details": {
                    "type": "string",
                    "description": "Where funds/asset should be sent — wallet address, bank account, PayPal/Zelle email or phone, etc.",
                },
                "notes": {"type": "string", "description": "Anything else relevant, e.g. gift card region, urgency."},
            },
            "required": ["direction", "asset", "amount", "payment_method", "destination_details"],
        },
    },
    {
        "name": "search_knowledge_base",
        "description": (
            "Search business FAQs/policies (supported assets, limits, processing "
            "time, verification requirements, etc.) for an answer. Call this "
            "before answering any question that isn't a rate lookup or an "
            "existing transaction status."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "get_transaction_status",
        "description": "Look up a customer's transaction lead(s) by their phone number, optionally filtered to one lead ID (e.g. 'LD12').",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_phone": {"type": "string"},
                "lead_id": {"type": "string"},
            },
            "required": ["customer_phone"],
        },
    },
]

_STATUS_LABELS = {
    "pending": "Pending — awaiting confirmation from our team.",
    "confirmed": "Confirmed — being processed.",
    "completed": "Completed.",
    "rejected": "Rejected.",
}


def _notify_owner_new_lead(lead: dict) -> None:
    direction_label = "SELLING to us" if lead["direction"] == "sell" else "BUYING from us"
    text = (
        f"🆕 New lead {lead['lead_id']}\n"
        f"Customer: {lead['customer_phone']}\n"
        f"{direction_label}: {lead['amount']} ({lead['asset']})\n"
        f"Payment method: {lead['payment_method']}\n"
        f"Destination/details: {lead['destination_details']}\n"
        + (f"Notes: {lead['notes']}\n" if lead.get("notes") else "")
        + f"\nReply: confirm {lead['lead_id']} | reject {lead['lead_id']} <reason>"
    )
    for owner_number in config.OWNER_WHATSAPP_NUMBERS:
        whatsapp_client.send_text(owner_number, text)


def dispatch(name: str, tool_input: dict, phone: str) -> dict:
    if name == "get_rate":
        rate = rates.get_rate(tool_input["asset"])
        if not rate:
            return {"found": False, "note": "No rate on file for that asset — tell the customer you'll confirm and get back to them."}
        return {"found": True, "rate": rate, "is_placeholder": rates.is_placeholder(rate.get("buy")) or rates.is_placeholder(rate.get("sell"))}

    if name == "create_transaction_lead":
        lead = store.create_lead(
            customer_phone=phone,
            direction=tool_input["direction"],
            asset=tool_input["asset"],
            amount=tool_input.get("amount"),
            payment_method=tool_input.get("payment_method"),
            destination_details=tool_input.get("destination_details"),
            notes=tool_input.get("notes"),
        )
        _notify_owner_new_lead(lead)
        return {"lead_id": lead["lead_id"], "status": lead["status"]}

    if name == "search_knowledge_base":
        results = knowledge_base.search(tool_input["query"])
        if not results:
            return {
                "results": [],
                "note": "No knowledge base content yet — tell the customer you'll confirm and follow up.",
            }
        return {"results": results}

    if name == "get_transaction_status":
        if tool_input.get("lead_id"):
            lead = store.get_lead(tool_input["lead_id"])
            leads = [lead] if lead and lead["customer_phone"] == phone else []
        else:
            leads = store.get_leads_for_phone(phone)
        for lead in leads:
            lead["status_label"] = _STATUS_LABELS.get(lead["status"], lead["status"])
        return {"leads": leads}

    return {"error": f"unknown tool: {name}"}
