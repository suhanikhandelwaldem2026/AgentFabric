"""
fabric/rag.py — lightweight keyword-section retrieval over data/policies.md.

Both agents call retrieve_policy(); neither writes its own retrieval logic.
Splits the policy doc into sections by '##' header, scores each section by
keyword overlap with the query, returns the top-scoring section's full text.
"""
from __future__ import annotations

import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
POLICY_FILE = DATA_DIR / "policies.md"

_STOPWORDS = {
    "the", "a", "an", "is", "are", "of", "to", "for", "and", "or", "in",
    "on", "with", "this", "that", "be", "if", "not", "do", "does", "what",
}


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z\-]*", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 1}


def _split_sections(markdown_text: str) -> list[tuple[str, str]]:
    """
    Splits on '## ' headers. Returns list of (header, full_section_text)
    where full_section_text includes the header line.
    """
    lines = markdown_text.splitlines()
    sections: list[tuple[str, list[str]]] = []
    current_header = None
    current_body: list[str] = []

    for line in lines:
        if line.startswith("## "):
            if current_header is not None:
                sections.append((current_header, current_body))
            current_header = line[3:].strip()
            current_body = [line]
        else:
            if current_header is not None:
                current_body.append(line)
    if current_header is not None:
        sections.append((current_header, current_body))

    return [(header, "\n".join(body).strip()) for header, body in sections]


def _load_sections() -> list[tuple[str, str]]:
    with open(POLICY_FILE, "r", encoding="utf-8") as f:
        text = f.read()
    return _split_sections(text)


def retrieve_policy(query: str) -> str:
    """
    Scores each '##' section of data/policies.md by keyword overlap with
    the query and returns the full text of the top-scoring section.
    """
    query_tokens = _tokenize(query)
    if not query_tokens:
        return ""

    sections = _load_sections()
    if not sections:
        return ""

    best_section_text = ""
    best_score = -1

    for header, body in sections:
        section_tokens = _tokenize(body)
        overlap = len(query_tokens & section_tokens)
        # Small boost if a query token appears in the header itself —
        # this is what reliably separates "Finance" vs "Procurement"
        # queries even when both sections share generic words like
        # "escalate" or "threshold".
        header_tokens = _tokenize(header)
        header_boost = 2 * len(query_tokens & header_tokens)
        score = overlap + header_boost

        if score > best_score:
            best_score = score
            best_section_text = body

    return best_section_text
