# Manage rates, payment methods, and the knowledge base

**Objective:** Keep the agent's rates, payment/receiving details, and
FAQ/policy content current — all three are read live, with no redeploy needed.

**When to run:** Whenever a rate or payment detail changes, or you learn
something the agent should know (a new accepted gift card brand, a policy
clarification, a support answer you had to give manually).

## Rates (`data/rates.json`)

Fastest path: talk to the owner agent naturally from an owner WhatsApp number
(see `workflows/owner_commands.md`) — e.g. *"set BTC buy 1.5m sell 1.55m"*.
Takes effect on the very next customer message; no restart needed.

For a multi-word asset (e.g. "Amazon Gift Card") or bulk edits, edit
`data/rates.json` directly — it's plain JSON, one entry per asset:

```json
"Amazon Gift Card": { "buy": "80%", "sell": "85%" }
```

`"buy"`/`"sell"` are free-text strings on purpose — crypto rates are usually
a fiat price per unit, gift card rates are usually a percentage of face
value. Use whatever a human would read as unambiguous. Leave `"TBD"` for
anything not yet decided — the agent is instructed to tell the customer it'll
confirm rather than guess when it sees that.

## Payment methods (`data/payment_methods.json`)

This is where AT Exchange itself receives money/assets — the bank account
customers pay into when buying, and the wallet address(es) customers send
crypto to when selling. The customer-facing agent looks this up fresh for
every transaction request (via `get_payment_instructions`) rather than ever
memorizing it, so an update here takes effect immediately.

Fastest path: tell the owner agent naturally — e.g. *"set our bank account to
Access Bank, 0123456789, AT Exchange Ltd"* or *"set our USDT wallet to
TXyz... on TRC20"*. Since a typo here means a customer could send funds
somewhere unrecoverable, the owner agent is instructed to read the full
details back to you and get an explicit yes before saving — don't skip past
that confirmation.

For bulk edits, `data/payment_methods.json` is plain JSON:
- `receive_fiat_for_buys` — one bank account, used for every "buy" regardless of asset.
- `receive_crypto_for_sells` — one wallet + network per crypto asset.
- `receive_gift_cards_for_sells` — just instructions text (customers send the code/photo in chat, no address needed).

Leave `"TBD"` for anything not yet decided — same convention as rates.

## Knowledge base (`knowledge_base/*.md`)

Add or edit any `.md` file in `knowledge_base/` — the agent re-scans the
folder automatically whenever a file's contents change (checked by
modification time), so no restart is needed here either.

Write it the way you'd answer a customer directly: short, one topic per `##`
heading (the search splits on headings, so keep each one focused). The
existing files (`faq.md`, `assets_and_rates.md`, `policies.md`) each have a
"Not yet finalized" section at the bottom flagging what's still a placeholder
— move an item out of that section into the real content once you've decided
the answer, so the agent stops saying "I'll confirm and get back to you" for
it.

## Verification

After any change, message the agent yourself as a test customer and ask the
relevant question / request the relevant asset, and confirm the answer
reflects your edit.

## Notes & learnings

- _(2026-09-08) Created._
- _(2026-09-08) Added payment methods section; rate/payment-method updates
  moved from a fixed WhatsApp command syntax to the conversational owner
  agent (`owner_agent.py`/`owner_tools.py`)._
- _(2026-09-08) Seeded `data/rates.json` with real starting numbers (BTC,
  USDT, ETH, SOL, and the three gift card brands) pulled from public market
  data (Binance P2P USDT/NGN, spot crypto prices, typical Nigerian gift card
  resale rates) with a standard buy/sell spread applied. These are a
  starting point the owner should check against the live market and adjust
  via the owner agent, not a permanent number, crypto and gift card rates
  move daily. Wallet addresses in `data/payment_methods.json` are still TBD
  since those can only come from the owner, never invent one, a wrong
  address means unrecoverable funds._
