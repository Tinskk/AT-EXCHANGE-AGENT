# Deploy the agent server

**Objective:** Get `app/` running continuously on Render so it can receive
WhatsApp webhooks 24/7.

**When to run:** Once for the first deploy, then any time `app/` changes and
needs to go live (Render auto-redeploys on push once connected, so this is
mostly a first-time setup).

## Inputs

| Input | Required | Notes |
|---|---|---|
| GitHub repo with this project pushed | yes | Render deploys from a connected repo. |
| A Render account | yes | Free to create; the service itself needs the Starter plan (~$7/mo). |
| All `.env` values filled in | yes | You'll re-enter them as Render env vars — see `.env.example`. |

## Steps

1. **Push to GitHub** — commit `app/`, `knowledge_base/`, `data/`,
   `workflows/`, and the rest of the project (everything except what's
   gitignored — `.env` and `app/data/*.db` never get committed) to the repo.

2. **Create a Render Web Service from the blueprint** — in the Render
   dashboard, "New" → "Blueprint" → connect the repo → set **Blueprint Path**
   to `app/render.yaml` explicitly (it defaults to looking at the repo root)
   → confirm.

   (If you'd rather configure manually instead of via blueprint: "New" → "Web
   Service" → connect repo → Root Directory: `app` → Build Command:
   `pip install -r requirements.txt` → Start Command:
   `uvicorn main:app --host 0.0.0.0 --port $PORT` → Plan: **Starter**, not
   Free — the free tier spins down after 15 min idle, which is too slow for a
   webhook Meta expects a fast ack from.)

3. **Set the environment variables** — in the service's "Environment" tab, add
   every value from `.env.example`: `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`,
   `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_APP_SECRET`,
   `WHATSAPP_VERIFY_TOKEN`, `GRAPH_API_VERSION`, `OWNER_WHATSAPP_NUMBERS`,
   `BUSINESS_NAME`. Never commit these — they only live in `.env` locally and
   in Render's dashboard.

4. **Confirm the persistent disk actually attached.** `app/render.yaml`
   declares a 1GB disk mounted at `/var/data`, with `AGENT_DB_PATH` pointing
   at `/var/data/agent.db`, so `app/store.py`'s SQLite file (conversation
   memory, dedupe, and the leads table, the actual transaction record here)
   survives redeploys instead of living on Render's default ephemeral disk.
   If the service was created *before* this was added to `render.yaml`,
   Render's Blueprint sync doesn't always retrofit a disk onto an existing
   service automatically — check the service's **Disks** tab in the Render
   dashboard. If nothing's listed there, add one manually: **Disks** → **Add
   Disk** → name it, mount path `/var/data`, size 1GB, then confirm
   `AGENT_DB_PATH` is set to `/var/data/agent.db` in the Environment tab.

5. **Deploy and confirm health** — once the build finishes,
   `curl https://<your-app>.onrender.com/health` should return
   `{"status":"ok"}`.

6. **Point Meta's webhook at this URL** — see Pass 2 of
   `setup_meta_whatsapp_cloud_api.md`.

7. **Send a real test message**, place a test transaction request, confirm
   the owner number receives the lead notification, then tell the owner
   agent to confirm it and confirm the customer receives the confirmation.

## Output

A live URL (`https://<your-app>.onrender.com`) running `app/`, wired up to
Meta's webhook, responding to real WhatsApp messages and owner commands.

## Edge cases

- **Build fails on missing env var:** `config.py` fails fast at boot with the
  exact variable name that's missing — check the Render logs, add it, redeploy.
- **`/health` times out or 502s right after deploy:** cold start on the first
  request after a build — wait ~30s and retry before assuming something's wrong.
- **Webhook verification fails after deploy:** confirm `/health` works first
  (proves the service is up), then re-check `WHATSAPP_VERIFY_TOKEN` matches
  exactly between Render's env vars and Meta's webhook config.
- **Redeploy resets conversation memory AND leads:** this was a real issue
  hit during initial setup, caused by the service running on Render's
  default ephemeral disk before the persistent disk in step 4 existed. If
  leads still disappear after a redeploy with the disk attached, check that
  `AGENT_DB_PATH` is actually set to a path under `/var/data` (the mount
  path), not the local default.
- **Blueprint deploy fails immediately, "render.yaml not found":** set
  **Blueprint Path** to `app/render.yaml` explicitly when creating the Blueprint.
- **First deploy after Blueprint creation fails:** expected if you haven't
  filled in the `sync: false` env vars yet — Render creates the service from
  the blueprint before you've had a chance to add secrets. Go to the
  service's Environment tab, add the missing values, save, and it auto-redeploys.
- **Agent replies to the first message but goes silent (or errors) on the
  second:** two known bug classes to check for if this happens — (1)
  `response.content` from the Anthropic SDK holds Pydantic objects, and
  `json.dumps(..., default=str)` must NOT be used when persisting the
  assistant's turn to history (use `block.model_dump()` per block, as
  `claude_agent.py` already does) — stringifying it instead corrupts every
  conversation after the first message; (2) trimming history by raw message
  count can cut in the middle of a tool-calling round trip, leaving an
  orphaned `tool_result` with no matching `tool_use` before it, which the
  Anthropic API rejects outright (`store.save_history` already guards against
  this by only resuming from a plain-string user message — don't remove that
  guard).

## Notes & learnings

- _(2026-09-08) Created, forked from the Tinsk Threads agent's deploy
  workflow; added the persistent-disk warning since leads (not a Sheet) are
  the system of record in this build._
- _(2026-09-08) Hit the predicted issue for real: a lead created during
  testing vanished after the next push auto-redeployed the service, because
  the disk hadn't been added yet. Fixed by adding the `disk` block to
  `app/render.yaml` and pointing `AGENT_DB_PATH` at it. Confirm the disk
  actually attached to the existing service (see step 4) rather than
  assuming the render.yaml change alone was enough._
