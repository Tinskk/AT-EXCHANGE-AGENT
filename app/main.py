"""FastAPI webhook receiver for the WhatsApp Cloud API.

Local dev:
    uvicorn main:app --reload --app-dir app       # from the project root
    # or: cd app && uvicorn main:app --reload

Production: deployed to Render — see workflows/deploy_agent_server.md.
"""

from __future__ import annotations

import logging

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

import claude_agent
import config
import owner_agent
import store
import whatsapp_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("whatsapp_agent")

app = FastAPI(title=f"{config.BUSINESS_NAME} WhatsApp Agent")

_UNSUPPORTED_MESSAGE_REPLY = (
    "Thanks for that! For now I can only read text messages and photos — "
    "could you describe what you need in a text?"
)
_IMAGE_RECEIVED_REPLY = "Got it, thanks — we've forwarded that to our team."
_IMAGE_NO_LEAD_NOTE = "(no open lead found for this number — matching it manually)"


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/debug/selftest")
def selftest(token: str | None = None) -> dict:
    """TEMPORARY diagnostic route — gated by WHATSAPP_VERIFY_TOKEN so it's not
    publicly callable. Runs each step of the message pipeline synchronously
    (unlike the real webhook flow, which fires it via BackgroundTasks and
    swallows exceptions into the server log we can't see from here) and
    reports exactly which step fails. Remove once the live-message issue is
    diagnosed — this is not meant to stay in the deployed app.
    """
    if token != config.WHATSAPP_VERIFY_TOKEN:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    result: dict = {}

    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=16,
            messages=[{"role": "user", "content": "Reply with exactly: OK"}],
        )
        result["anthropic"] = {"ok": True, "reply": "".join(b.text for b in resp.content if b.type == "text")}
    except Exception as e:  # noqa: BLE001 — diagnostic route, want the raw error
        result["anthropic"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}

    try:
        owner = config.OWNER_WHATSAPP_NUMBERS[0]
        send_result = whatsapp_client.send_text(owner, "DEBUG SELFTEST: direct WhatsApp send check.")
        result["whatsapp_send"] = {"ok": True, "response": send_result}
    except Exception as e:  # noqa: BLE001
        body = getattr(getattr(e, "response", None), "text", None)
        result["whatsapp_send"] = {"ok": False, "error": f"{type(e).__name__}: {e}", "response_body": body}

    try:
        store.get_history("debug-selftest-phone")
        result["store"] = {"ok": True}
    except Exception as e:  # noqa: BLE001
        result["store"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}

    return result


@app.get("/webhook")
def verify(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    result = whatsapp_client.verify_webhook(mode, token, challenge)
    if result is not None:
        return PlainTextResponse(result)
    return PlainTextResponse("forbidden", status_code=403)


def _handle_customer_image(from_number: str, media_id: str) -> None:
    lead = store.get_most_recent_open_lead(from_number)
    caption = f"📎 Photo from {from_number}"
    caption += f" — {lead['lead_id']}" if lead else f" {_IMAGE_NO_LEAD_NOTE}"
    for owner_number in config.OWNER_WHATSAPP_NUMBERS:
        whatsapp_client.forward_image(owner_number, media_id, caption=caption)
    whatsapp_client.send_text(from_number, _IMAGE_RECEIVED_REPLY)


@app.post("/webhook")
async def receive(request: Request, background_tasks: BackgroundTasks):
    raw_body = await request.body()
    signature = request.headers.get("x-hub-signature-256")

    if not whatsapp_client.verify_signature(raw_body, signature):
        logger.warning("rejected webhook: bad signature")
        return JSONResponse({"status": "invalid signature"}, status_code=401)

    payload = await request.json()

    for message in whatsapp_client.parse_incoming(payload):
        if store.is_duplicate(message.wamid):
            logger.info("skipping duplicate message %s", message.wamid)
            continue
        store.mark_seen(message.wamid)

        is_owner = message.from_number in config.OWNER_WHATSAPP_NUMBERS

        if message.message_type == "text" and message.text:
            if is_owner:
                background_tasks.add_task(owner_agent.handle_message, message.from_number, message.text)
            else:
                background_tasks.add_task(claude_agent.handle_message, message.from_number, message.text)
            continue

        if message.message_type == "image" and message.media_id and not is_owner:
            background_tasks.add_task(_handle_customer_image, message.from_number, message.media_id)
            continue

        background_tasks.add_task(whatsapp_client.send_text, message.from_number, _UNSUPPORTED_MESSAGE_REPLY)

    # Always ack fast — Meta retries the delivery if it doesn't get a prompt 200.
    return {"status": "received"}
