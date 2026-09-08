"""App-wide configuration. Fails fast at import time if something required is
missing — better to crash on boot with a clear message than fail mysteriously
on the first webhook.

Local dev reads from .env (via python-dotenv); in production (Render) these
are just process environment variables set in the dashboard.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent

load_dotenv(ROOT / ".env")


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        sys.exit(f"Missing required environment variable: {name} (set it in .env or the host's env vars)")
    return value


# --- LLM ---
ANTHROPIC_API_KEY = _require("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")

# --- WhatsApp Cloud API ---
WHATSAPP_ACCESS_TOKEN = _require("WHATSAPP_ACCESS_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = _require("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_APP_SECRET = _require("WHATSAPP_APP_SECRET")
WHATSAPP_VERIFY_TOKEN = _require("WHATSAPP_VERIFY_TOKEN")
GRAPH_API_VERSION = os.getenv("GRAPH_API_VERSION", "v21.0")

# --- Owner / staff numbers ---
# Comma-separated WhatsApp numbers (in the same "from" format Meta sends,
# e.g. "2348012345678" — no "+", no spaces) that are treated as staff, not
# customers. Messages from these numbers skip the Claude agent entirely and
# go to the deterministic owner-command parser instead.
OWNER_WHATSAPP_NUMBERS = [
    n.strip() for n in _require("OWNER_WHATSAPP_NUMBERS").split(",") if n.strip()
]

# --- App ---
BUSINESS_NAME = os.getenv("BUSINESS_NAME", "AT Exchange")
MAX_HISTORY_TURNS = 20
KNOWLEDGE_BASE_DIR = ROOT / "knowledge_base"
RATES_PATH = ROOT / "data" / "rates.json"
PAYMENT_METHODS_PATH = ROOT / "data" / "payment_methods.json"

# Anchored to app/ by default so it's correct regardless of the process's cwd
# (Render's rootDir, local `cd app && uvicorn ...`, etc.). Override with an
# absolute path via AGENT_DB_PATH if you ever need to.
AGENT_DB_PATH = os.getenv("AGENT_DB_PATH") or str(APP_DIR / "data" / "agent.db")
