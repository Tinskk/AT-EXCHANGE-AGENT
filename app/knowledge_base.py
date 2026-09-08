"""Simple keyword-based search over knowledge_base/*.md and *.txt.

Deliberately no embeddings/vector DB for v1 — keyword scoring is enough at
small-business scale and content volume, and it's trivial to reason about
when a customer's question isn't being answered well. Files are re-scanned
whenever the folder's contents change (checked by mtime), so dropping in new
content needs no redeploy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import config

_CHUNK_WORDS = 300
_CHUNK_OVERLAP = 50

_cache: dict = {"mtime": None, "chunks": []}


@dataclass
class Chunk:
    source_file: str
    text: str


def _split_into_chunks(text: str) -> list[str]:
    # Prefer splitting on markdown headings (any level) when present — gives
    # more focused, topic-sized chunks than a blind word-count window. Real
    # knowledge base files tend to mix "#" and "##" freely, so split on both.
    heading_split = re.split(r"(?m)^#{1,6}\s+", text)
    if len(heading_split) > 1:
        return [c.strip() for c in heading_split if c.strip()]

    words = text.split()
    if not words:
        return []
    chunks = []
    step = _CHUNK_WORDS - _CHUNK_OVERLAP
    for start in range(0, len(words), step):
        chunks.append(" ".join(words[start : start + _CHUNK_WORDS]))
        if start + _CHUNK_WORDS >= len(words):
            break
    return chunks


def _dir_mtime() -> float:
    if not config.KNOWLEDGE_BASE_DIR.exists():
        return 0.0
    return max(
        (p.stat().st_mtime for p in config.KNOWLEDGE_BASE_DIR.rglob("*") if p.is_file()),
        default=0.0,
    )


def _load_chunks() -> list[Chunk]:
    mtime = _dir_mtime()
    if _cache["mtime"] == mtime:
        return _cache["chunks"]

    chunks: list[Chunk] = []
    if config.KNOWLEDGE_BASE_DIR.exists():
        for path in sorted(config.KNOWLEDGE_BASE_DIR.rglob("*")):
            if path.suffix.lower() not in (".md", ".txt"):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            chunks.extend(Chunk(source_file=path.name, text=piece) for piece in _split_into_chunks(text))

    _cache["mtime"] = mtime
    _cache["chunks"] = chunks
    return chunks


def search(query: str, top_k: int = 3) -> list[dict]:
    keywords = [w for w in re.findall(r"\w+", query.lower()) if len(w) > 2]
    if not keywords:
        return []

    scored = []
    for chunk in _load_chunks():
        text_lower = chunk.text.lower()
        score = sum(text_lower.count(kw) for kw in keywords)
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [{"source_file": chunk.source_file, "text": chunk.text} for _, chunk in scored[:top_k]]
