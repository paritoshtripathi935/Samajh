"""Citation formatter — extract and structure Indian legal citations from text.
Supports AIR, SCC, SCR, ILR case formats and Section/Article references.

For a chargesheet, "under which sections?" is a core question -- so section/
article detection turns a plain answer into clickable, source-linkable refs.
"""
from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field
from typing import List, Set


@dataclass
class Citation:
    text: str
    citation_type: str  # "case" | "statute"
    url: str = ""       # optional deeplink back to source


@dataclass
class IpcReference:
    section: str
    raw_text: str
    start_offset: int
    end_offset: int


_PATTERNS = {
    # AIR 2023 SC 1234  /  AIR 2022 Bom 567
    "air": re.compile(r"AIR\s+\d{4}\s+[A-Z][A-Za-z]+\s+\d+"),
    # (2023) 5 SCC 678
    "scc": re.compile(r"\(\d{4}\)\s+\d+\s+SCC\s+\d+"),
    # 2023 SCR 1 45
    "scr": re.compile(r"\d{4}\s+SCR\s+\d+\s+\d+"),
    # ILR 2022 Delhi 890
    "ilr": re.compile(r"ILR\s+\d{4}\s+[A-Z][A-Za-z]+\s+\d+"),
    # Section 302 of the Indian Penal Code  /  Section 138 NI Act
    "section": re.compile(
        r"[Ss]ection\s+\d+[A-Z]?(?:\([a-z]\))?"
        r"(?:\s+(?:of\s+(?:the\s+)?)?[A-Z][A-Za-z\s]{2,30})?(?=[\s,\.\;]|$)"
    ),
    # Article 21 of the Constitution
    "article": re.compile(
        r"[Aa]rticle\s+\d+[A-Z]?"
        r"(?:\s+(?:of\s+(?:the\s+)?)?[A-Z][A-Za-z\s]{2,30})?(?=[\s,\.\;]|$)"
    ),
}

_CASE_TYPES = {"air", "scc", "scr", "ilr"}

_IPC_PATTERN = re.compile(
    r"(?P<raw>"
    r"(?:(?:Section|Sec\.?|u/s|U/S|S\.?)\s*(?P<section_a>\d+[A-Z]?)\s*(?:of\s+)?(?:IPC|I\.P\.C\.))"
    r"|"
    r"(?:(?:IPC|I\.P\.C\.)\s*(?:Section|Sec\.?)?\s*(?P<section_b>\d+[A-Z]?))"
    r")",
    re.IGNORECASE,
)


def extract_citations(text: str) -> List[Citation]:
    """Extract all Indian legal citations from a block of text."""
    citations: List[Citation] = []
    seen: Set[str] = set()

    for ctype, pattern in _PATTERNS.items():
        for match in pattern.finditer(text):
            raw = match.group().strip()
            if raw in seen:
                continue
            seen.add(raw)

            kind = "case" if ctype in _CASE_TYPES else "statute"
            url = _build_ik_search_url(raw) if kind == "case" else ""
            citations.append(Citation(text=raw, citation_type=kind, url=url))

    return citations


def extract_ipc_references(text: str) -> List[IpcReference]:
    """Extract IPC section references with source offsets for UI highlighting."""
    refs: List[IpcReference] = []
    seen_ranges: Set[tuple[int, int]] = set()

    for match in _IPC_PATTERN.finditer(text):
        start, end = match.span()
        if (start, end) in seen_ranges:
            continue

        section = match.group("section_a") or match.group("section_b")
        if not section:
            continue

        refs.append(
            IpcReference(
                section=section.upper(),
                raw_text=match.group("raw"),
                start_offset=start,
                end_offset=end,
            )
        )
        seen_ranges.add((start, end))

    return refs


def extract_suggested_steps(text: str) -> List[str]:
    """Parse a '**Suggested Next Steps**' section into plain-text step strings."""
    section_match = re.search(
        r"\*{0,2}Suggested Next Steps\*{0,2}\s*:?\s*\n(.*?)(?=\n\*{0,2}[A-Z]|\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not section_match:
        return []

    steps: List[str] = []
    for line in section_match.group(1).splitlines():
        line = line.strip()
        step_match = re.match(r"^(?:\d+[\.\)]\s*|-\s*)(.+)$", line)
        if step_match:
            steps.append(step_match.group(1).strip())
    return steps


def _build_ik_search_url(citation: str) -> str:
    return f"https://indiankanoon.org/search/?formInput={urllib.parse.quote(citation)}"
