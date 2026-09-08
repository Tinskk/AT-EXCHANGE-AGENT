# Manage rates and the knowledge base

**Objective:** Keep the agent's rates and FAQ/policy content current — both
are read live, with no redeploy needed.

**When to run:** Whenever a rate changes, or you learn something the agent
should know (a new accepted gift card brand, a policy clarification, a
support answer you had to give manually).

## Rates (`data/rates.json`)

Fastest path: send `setrate <asset> <buy> <sell>` from an owner WhatsApp
number (see `workflows/owner_commands.md`) — e.g. `setrate BTC 1500000
1550000`. Takes effect on the very next customer message; no restart needed.

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
