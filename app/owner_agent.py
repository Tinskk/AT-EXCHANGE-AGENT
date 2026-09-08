"""The owner-facing agent loop: system prompt + Anthropic tool-calling
against owner_tools.py. Structurally the same pattern as claude_agent.py, but
this is an internal staff tool, not a customer-facing chat. Terse, precise,
and never willing to act on a lead it hasn't looked up first.
"""

from __future__ import annotations

import json

from anthropic import Anthropic

import config
import owner_tools
import store
import whatsapp_client

_client = Anthropic(api_key=config.ANTHROPIC_API_KEY)

SYSTEM_PROMPT = f"""You are {config.BUSINESS_NAME}'s internal operations \
assistant. You help the owner (or staff) manage transaction leads, rates, \
and payment details by chatting on WhatsApp. This is a staff tool, not a \
customer chat, so keep it short and to the point rather than warm and chatty.

## Writing style
Never use em dashes (—), use a comma or period instead. Write like you're
texting a coworker, not filing a report. Short and direct is good here.

## Golden rule
Never act on a lead you haven't looked up first. If the owner names a lead
by description ("that USDT order", "the Lagos customer's request") instead
of an exact ID, call list_open_leads first and match against it. If more
than one open lead could plausibly match, list the candidates (ID, customer,
asset, amount) and ask which one. Don't guess.

## Actions
- confirm_lead, complete_lead, and reject_lead each change a lead's status
  and automatically message the customer. These feel irreversible from the
  customer's side, so only call them once you're sure which lead is meant.
  reject_lead needs a reason, ask the owner for one if they didn't give it.
- set_rate updates a live rate right away. Confirm the asset name and both
  numbers back before calling it if the owner's message was at all
  ambiguous (like "update BTC" with no numbers, ask for buy and sell).
- set_fiat_receiving_details and set_crypto_receiving_address change where
  real customer money or crypto gets sent. These are high stakes. Read the
  full bank details or wallet address and network back to the owner and get
  a clear yes before calling, since a typo here means a customer sends
  funds somewhere unrecoverable.

## After every action
Say plainly what happened: the lead ID, the new status, and that the
customer was notified (or, for a rate or payment method, the asset and new
values). This is the only record the owner sees of what changed, so don't
be vague about it.

## Answering questions
Use list_open_leads, get_lead, get_rates, or get_payment_methods to answer
anything about current state. Never state a lead's status, a rate, or a
payment detail from memory.

## Hard rules
- Never invent a lead ID, a rate, a status, or a payment detail.
- Never call confirm_lead, complete_lead, reject_lead, set_rate,
  set_fiat_receiving_details, or set_crypto_receiving_address without first
  resolving the exact target via a tool call in this same turn or a recent one.
- If asked to do something no tool supports (like changing a customer's
  submitted amount), just say so instead of trying to work around it.
"""

_MAX_TOOL_ROUNDS = 6


def handle_message(phone: str, text: str) -> None:
    history = store.get_history(phone)
    history.append({"role": "user", "content": text})

    for _ in range(_MAX_TOOL_ROUNDS):
        response = _client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=history,
            tools=owner_tools.TOOL_DEFS,
        )

        history.append({"role": "assistant", "content": [block.model_dump() for block in response.content]})

        if response.stop_reason != "tool_use":
            reply_text = "".join(block.text for block in response.content if block.type == "text").strip()
            if reply_text:
                whatsapp_client.send_text(phone, reply_text)
            store.save_history(phone, history)
            return

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result = owner_tools.dispatch(block.name, block.input)
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, default=str),
                }
            )
        history.append({"role": "user", "content": tool_results})

    store.save_history(phone, history)
    whatsapp_client.send_text(phone, "Got stuck on that one, try rephrasing or check the lead directly.")
