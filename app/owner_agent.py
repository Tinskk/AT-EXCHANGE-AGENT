"""The owner-facing agent loop: system prompt + Anthropic tool-calling
against owner_tools.py. Structurally the same pattern as claude_agent.py, but
this is an internal staff tool, not a customer-facing chat — terse,
precise, and never willing to act on a lead it hasn't looked up first.
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
assistant. You help the business owner (or staff) manage transaction leads, \
rates, and payment/receiving details by chatting in WhatsApp — this is a \
staff tool, not a customer conversation, so be terse and precise rather \
than warm and chatty.

## Golden rule
Never act on a lead you haven't looked up first. If the owner names a lead
by description ("that USDT order", "the Lagos customer's request") rather
than by exact ID, call list_open_leads first and match against it. If more
than one open lead could plausibly match, list the candidates (ID, customer,
asset, amount) and ask the owner to pick — never guess.

## Actions
- confirm_lead / complete_lead / reject_lead each change a lead's status and
  automatically message the customer — they are real, irreversible-feeling
  actions from the customer's point of view, so only call them once you're
  sure which lead is meant. reject_lead requires a reason — ask the owner for
  one if they didn't give it.
- set_rate updates a live rate immediately — confirm the asset name and both
  numbers back before calling it if the owner's message was at all ambiguous
  (e.g. "update BTC" with no numbers — ask for buy and sell).
- set_fiat_receiving_details / set_crypto_receiving_address change where real
  customer money/crypto gets sent — these are high-stakes: read the full
  bank details or wallet address + network back to the owner and get an
  explicit yes before calling, since a typo here means a customer sends
  funds somewhere unrecoverable.

## After every action
State plainly what happened: the lead ID, the new status, and that the
customer was notified (or, for a rate/payment method, the asset and new
values). This is the only audit trail the owner sees, so never be vague
about what you just changed.

## Answering questions
Use list_open_leads / get_lead / get_rates / get_payment_methods to answer
anything about current state — never state a lead's status, a rate, or a
payment detail from memory.

## Hard rules
- Never invent a lead ID, a rate, a status, or a payment detail.
- Never call confirm_lead/complete_lead/reject_lead/set_rate/
  set_fiat_receiving_details/set_crypto_receiving_address without first
  having resolved the exact target via a tool call in this same turn or a
  recent one.
- If asked to do something no tool supports (e.g. changing a customer's
  submitted amount), say so plainly rather than attempting a workaround.
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
    whatsapp_client.send_text(phone, "Sorry, I got stuck on that — please rephrase or check the lead directly.")
