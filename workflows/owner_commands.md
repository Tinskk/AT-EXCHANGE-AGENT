# Managing leads, rates, and payment methods as the owner

**Objective:** Reference for how you (or any staff number listed in
`OWNER_WHATSAPP_NUMBERS`) manage transaction leads, rates, and AT Exchange's
own payment/receiving details — entirely by chatting naturally on WhatsApp,
no dashboard and no fixed command syntax needed.

**When to run:** Any time a new lead comes in, a rate changes, or a bank
account/wallet address needs updating.

## How it works

Messages from a number listed in `OWNER_WHATSAPP_NUMBERS` are routed to a
second Claude agent (`app/owner_agent.py`), separate from the customer-facing
one — it has its own system prompt and its own tool set (`app/owner_tools.py`:
`list_open_leads`, `get_lead`, `confirm_lead`, `complete_lead`, `reject_lead`,
`get_rates`, `set_rate`, `get_payment_methods`, `set_fiat_receiving_details`,
`set_crypto_receiving_address`). You talk to it the same way you'd talk to a
staff member over chat; it looks up the real lead before acting, and always
tells you exactly what it did.

You don't need to memorize any syntax — just describe what you want:

- "confirm LD7"
- "go ahead and confirm the USDT order for that Lagos number"
- "what's still pending?"
- "reject LD9, the screenshot doesn't match the amount"
- "mark LD7 as done"
- "what's the current BTC rate?"
- "set BTC buy 1.5m sell 1.55m"
- "what's our current payment info?"
- "set our bank account to Access Bank, 0123456789, AT Exchange Ltd"
- "set our USDT wallet to TXyz... on TRC20"

Because a wrong bank account or wallet address means a customer's money/crypto
goes somewhere unrecoverable, the agent will read the full details back to
you and wait for an explicit yes before saving a payment method change —
don't be surprised if it double-checks before something else would've just
acted.

If your description could match more than one open lead, the agent will list
the candidates and ask you to pick rather than guessing — respond with the
lead ID it should act on.

## Example

You send: `confirm the USDT one, 500 units`
Agent (after calling `list_open_leads` and finding one match) replies:
`Confirmed LD7 (sell 500 USDT, customer 2348012345678) — customer notified.`
Customer receives: `✅ Your transaction (LD7) has been confirmed and is being processed.`

Later, once you've actually sent the payout: `mark LD7 done`
Customer receives: `🎉 Your transaction (LD7) has been completed. Thank you for using AT Exchange!`

If your description is ambiguous, e.g. two open USDT leads:
Agent replies: `Two open USDT leads match — which one? LD7: 500 USDT, customer
2348012345678, pending. LD9: 200 USDT, customer 2347099998888, pending.`
You reply: `LD7`

## Edge cases

- **A customer's payment-proof photo isn't tagged with the right lead:** the
  agent attaches an image to whichever lead is most recently `pending` or
  `confirmed` for that customer's number (this part is still deterministic,
  in `app/main.py`). If a customer has more than one open lead at once,
  double-check with `get_lead`/"show me LD_" before assuming which one a
  forwarded photo belongs to.
- **`set_rate` with a multi-word asset name (e.g. "Amazon Gift Card"):** the
  tool takes a single asset name string — ask the agent to set it (it'll pass
  the name through as given), or edit `data/rates.json` directly for
  precision on multi-word keys.
- **A number not in `OWNER_WHATSAPP_NUMBERS` tries this:** it's treated as an
  ordinary customer and goes to the customer-facing agent instead — nothing
  happens to any lead. Double-check the number list in `.env` if a request
  from a staff member "does nothing."
- **The agent hesitates or asks a clarifying question when you expected it to
  just act:** that's intentional — it's instructed to never guess a lead ID
  or act on an ambiguous match. Answer the clarifying question rather than
  rephrasing to try to force a direct action.

## Notes & learnings

- _(2026-09-08) Created as a fixed-command reference._
- _(2026-09-08) Rewritten — the owner side moved from a deterministic string
  parser to a conversational Claude agent (`owner_agent.py`/`owner_tools.py`),
  same pattern as the customer-facing agent, so the owner never has to
  memorize exact syntax._
