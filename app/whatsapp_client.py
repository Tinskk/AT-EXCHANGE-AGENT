"""WhatsApp Cloud API: webhook verification, signature check, incoming-message
parsing, sending replies, and media download/re-upload (for forwarding a
customer's payment-proof photo to the owner).
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

import httpx

import config

_GRAPH_BASE = f"https://graph.facebook.com/{config.GRAPH_API_VERSION}"
_AUTH_HEADER = {"Authorization": f"Bearer {config.WHATSAPP_ACCESS_TOKEN}"}


@dataclass
class IncomingMessage:
    wamid: str
    from_number: str
    message_type: str
    text: str | None
    media_id: str | None
    timestamp: str


def verify_webhook(mode: str | None, token: str | None, challenge: str | None) -> str | None:
    """Meta's GET handshake. Returns the challenge to confirm the webhook, else None."""
    if mode == "subscribe" and token == config.WHATSAPP_VERIFY_TOKEN and challenge is not None:
        return challenge
    return None


def verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """Verify X-Hub-Signature-256 so we only act on requests genuinely from Meta."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(config.WHATSAPP_APP_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    provided = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, provided)


def parse_incoming(payload: dict) -> list[IncomingMessage]:
    """Extract every message (text, image, or otherwise) from a webhook payload.

    Non text/image messages are still returned (with text/media_id=None) so
    the caller can decide how to handle them — a WAMID has to be marked seen
    either way to dedupe correctly.
    """
    messages: list[IncomingMessage] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []):
                message_type = msg.get("type", "unknown")
                messages.append(
                    IncomingMessage(
                        wamid=msg["id"],
                        from_number=msg["from"],
                        message_type=message_type,
                        text=msg.get("text", {}).get("body") if message_type == "text" else None,
                        media_id=msg.get("image", {}).get("id") if message_type == "image" else None,
                        timestamp=msg.get("timestamp", ""),
                    )
                )
    return messages


def send_text(to: str, body: str) -> dict:
    url = f"{_GRAPH_BASE}/{config.WHATSAPP_PHONE_NUMBER_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body},
    }
    response = httpx.post(url, json=payload, headers=_AUTH_HEADER, timeout=15)
    response.raise_for_status()
    return response.json()


def send_image_by_id(to: str, media_id: str, caption: str | None = None) -> dict:
    """Send an image we already hold a media ID for (e.g. one we just
    re-uploaded after downloading it from a customer)."""
    url = f"{_GRAPH_BASE}/{config.WHATSAPP_PHONE_NUMBER_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "image",
        "image": {"id": media_id, **({"caption": caption} if caption else {})},
    }
    response = httpx.post(url, json=payload, headers=_AUTH_HEADER, timeout=15)
    response.raise_for_status()
    return response.json()


def download_media(media_id: str) -> tuple[bytes, str]:
    """Resolve a media ID to its temporary URL and download the bytes.

    Returns (content, mime_type). Media IDs expire and are only ever
    resolvable with our own access token — that's why this is a two-step
    fetch rather than a public link.
    """
    meta_url = f"{_GRAPH_BASE}/{media_id}"
    meta_response = httpx.get(meta_url, headers=_AUTH_HEADER, timeout=15)
    meta_response.raise_for_status()
    meta = meta_response.json()

    content_response = httpx.get(meta["url"], headers=_AUTH_HEADER, timeout=30)
    content_response.raise_for_status()
    return content_response.content, meta.get("mime_type", "image/jpeg")


def upload_media(content: bytes, mime_type: str) -> str:
    """Upload bytes to our own WABA so we can send them onward (e.g.
    forwarding a customer's photo to the owner) — returns the new media ID.
    """
    url = f"{_GRAPH_BASE}/{config.WHATSAPP_PHONE_NUMBER_ID}/media"
    files = {"file": ("proof.jpg", content, mime_type)}
    data = {"messaging_product": "whatsapp"}
    response = httpx.post(url, data=data, files=files, headers=_AUTH_HEADER, timeout=30)
    response.raise_for_status()
    return response.json()["id"]


def forward_image(to: str, media_id: str, caption: str | None = None) -> dict:
    """Download a customer's image and re-upload it so it can be sent to
    someone else (the owner) — a media ID from one webhook isn't directly
    forwardable to an arbitrary recipient.
    """
    content, mime_type = download_media(media_id)
    new_media_id = upload_media(content, mime_type)
    return send_image_by_id(to, new_media_id, caption=caption)
