# Set up the Meta WhatsApp Cloud API

**Objective:** Get a Meta Developer app + WhatsApp Business number talking to
`app/`, so real customer messages reach the agent.

**When to run:** Once, before going live. The webhook-pointing step at the end
depends on `app/` already being deployed — see `deploy_agent_server.md` — so
this workflow is finished in two passes: credentials first, webhook after deploy.

## Inputs

| Input | Required | Notes |
|---|---|---|
| A Facebook account | yes | To create the Meta Developer app. |
| A phone number for testing | yes | Your own phone, to message the test number from. |

## Steps

### Pass 1 — credentials (do this before deploying)

1. **Create a Meta Developer account** — [developers.facebook.com](https://developers.facebook.com) → sign up / log in.

2. **Create an app** — "My Apps" → "Create App" → type **Business** → give it a name (e.g. "AT Exchange Agent").

3. **Add the WhatsApp product** — from the app dashboard, find "WhatsApp" under "Add products to your app" → Set up.

4. **Note the test number details** — the WhatsApp → API Setup page shows a
   free test phone number, its **Phone Number ID**, and your **WhatsApp
   Business Account ID**. Copy the Phone Number ID into
   `WHATSAPP_PHONE_NUMBER_ID` in `.env`.

5. **Get a temporary access token** — same API Setup page has a "Temporary
   access token" (valid 24h) — copy it into `WHATSAPP_ACCESS_TOKEN` for now,
   just to smoke-test sending. **Replace it before going live** (next step) —
   it expires and will silently break the agent.

6. **Create a permanent token** — Meta Business Suite → Business Settings →
   "Users" → "System Users" → create a system user → assign it to your app with
   `whatsapp_business_messaging` permission → "Generate New Token" → choose
   the app, select that permission, no expiration. Put this token in
   `WHATSAPP_ACCESS_TOKEN` instead of the temporary one.

7. **Find the App Secret** — App Dashboard → "App Settings" → "Basic" → "App
   Secret" (click "Show") → put it in `WHATSAPP_APP_SECRET`.

8. **Invent a verify token** — any random string you make up, e.g. a UUID —
   put it in `WHATSAPP_VERIFY_TOKEN`. You'll enter this same string into Meta's
   webhook config in Pass 2.

9. **Set OWNER_WHATSAPP_NUMBERS** — your own WhatsApp number(s), in the same
   digits-only format Meta uses (e.g. `2348012345678`), comma-separated if
   more than one. This is the number the agent pages for every transaction
   confirmation — get it right before testing.

10. **Smoke-test sending** — message the test number from your own phone
    first (free-form replies only work within 24h of the customer's last
    message).

### Pass 2 — point the webhook at the deployed app (after `deploy_agent_server.md`)

11. **Configure the webhook** — WhatsApp → Configuration → "Edit" on Webhook →
    Callback URL: `https://<your-render-app>.onrender.com/webhook`, Verify
    Token: the same `WHATSAPP_VERIFY_TOKEN` value → "Verify and Save".

12. **Subscribe to the `messages` field** — in the same Configuration page,
    under "Webhook fields", subscribe to `messages`.

13. **Test end-to-end** — message the test number from your phone and confirm
    a reply comes back from the deployed agent, then confirm a WhatsApp
    message arrives on `OWNER_WHATSAPP_NUMBERS` when you complete a test
    transaction request.

## Output

`.env` has working WhatsApp Cloud API credentials, and (after Pass 2) the
Meta App's webhook is verified and subscribed, pointing at the deployed `app/`.

## Edge cases

- **Free-form replies fail outside 24h:** Meta requires an approved message
  template to message a customer (or the owner) who hasn't messaged in the
  last 24 hours. Not handled in v1 — the agent only replies within an open
  conversation. This matters for the owner-notification flow too: if the
  owner hasn't messaged the agent's number in 24h, the "new lead" ping may fail
  to deliver as free-form text — have the owner send the agent any message
  (e.g. "hi") at least once a day, or set up an approved template later.
- **Temporary token expires:** if messages suddenly stop working after ~24h,
  this is almost always it — go create the permanent System User token (step 6).
- **Webhook verification fails (403):** the Verify Token in Meta's config
  doesn't match `WHATSAPP_VERIFY_TOKEN` in the deployed app's environment, or
  the app isn't actually reachable at that URL yet — check `/health` first.
- **Webhook verifies and subscribes to `messages`, but nothing ever reaches
  the app:** verifying the callback URL and subscribing to the `messages`
  field only configure the *app's* webhook. The WhatsApp Business Account
  (WABA) itself also has to be subscribed to that app, separately — check
  with `GET /{waba-id}/subscribed_apps` (needs a token with
  `whatsapp_business_management` scope, not just `whatsapp_business_messaging`).
  A freshly-created WABA can come back subscribed to Meta's own default
  receiver app instead of yours. Fix: `POST /{waba-id}/subscribed_apps` with
  that same token — this adds your app without removing the default one.
- **Business verification for a crypto/money-services business may take
  longer or be scrutinized more than a typical retail business** — Meta's
  Commerce/Business Policies have historically restricted cryptocurrency
  businesses. Start verification early and have a fallback communication
  channel in mind in case the account is delayed or flagged.

## Notes & learnings

- _(2026-09-08) Created — forked from the Tinsk Threads agent's setup workflow._
