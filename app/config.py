"""App-wide configuration. Fails fast at import time if something required is
missing — better to crash on boot with a clear message than fail mysteriously
on the first webhook.

Local dev reads from .env (via python-dotenv); in production (Render) these
are just process environment variables set in the dashboard.
"""

from __future__ import annotations

import os
import shutil
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

# --- Live-editable data (rates, payment methods) ---
# `data/*.json` in the repo is only the SEED — the values as of the last git
# commit. The actual read/write path the app uses is PERSISTENT_DATA_DIR,
# which defaults to the same repo folder for local dev (so nothing changes
# there), but on Render is pointed at the persistent disk (see render.yaml)
# so that rates/payment methods set live via the owner WhatsApp chat survive
# a redeploy instead of being silently reset back to whatever's in git.
# Learned the hard way: only AGENT_DB_PATH was on the persistent disk
# originally, so a routine `git push` (any code change, not just a rate
# change) would blow away live-edited wallet addresses on the next deploy.
_SEED_DATA_DIR = ROOT / "data"
PERSISTENT_DATA_DIR = Path(os.getenv("PERSISTENT_DATA_DIR") or _SEED_DATA_DIR)
RATES_PATH = PERSISTENT_DATA_DIR / "rates.json"
PAYMENT_METHODS_PATH = PERSISTENT_DATA_DIR / "payment_methods.json"


def _seed_if_missing(target: Path, seed_name: str) -> None:
    """Copy the git-tracked seed file to the persistent location, but only
    the first time (i.e. only if the persistent copy doesn't exist yet) —
    once it exists, it's the live source of truth and must never be
    overwritten by a redeploy."""
    if target.exists() or target.resolve() == (_SEED_DATA_DIR / seed_name).resolve():
        return
    seed = _SEED_DATA_DIR / seed_name
    if not seed.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(seed, target)


_seed_if_missing(RATES_PATH, "rates.json")
_seed_if_missing(PAYMENT_METHODS_PATH, "payment_methods.json")

# Anchored to app/ by default so it's correct regardless of the process's cwd
# (Render's rootDir, local `cd app && uvicorn ...`, etc.). Override with an
# absolute path via AGENT_DB_PATH if you ever need to.
AGENT_DB_PATH = os.getenv("AGENT_DB_PATH") or str(APP_DIR / "data" / "agent.db")
