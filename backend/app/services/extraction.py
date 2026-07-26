"""Document-typed field extraction.

Sarvam's schema-based "Extract" (fields + per-field confidence) is a no-code
dashboard feature with NO public REST API. So we implement extraction here:
digitise the filing, then prompt sarvam-30b to return typed fields grounded
in the digitised text, each with a confidence score and a verbatim source
snippet. Low-confidence fields become the "verify" flags in the UI.

The field sets are document-typed (the scope's thesis): a chargesheet is not
a judgment.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from app.services import sarvam

# Fields to pull, per filing type. Keep these tight and lawyer-meaningful.
_SCHEMAS: Dict[str, List[str]] = {
    "chargesheet": [
        "accused_names",
        "charges",
        "sections",              # IPC/CrPC/special-act sections invoked
        "fir_number",
        "police_station",
        "investigating_officer",
        "date_of_offence",
        "court",
    ],
    "judgment": [
        "case_title",
        "court",
        "coram",                 # judge(s)
        "parties",               # appellant / respondent
        "issues",
        "ratio",                 # ratio decidendi / holding
        "disposition",           # allowed / dismissed / remanded
        "judgment_date",
    ],
}

_SYSTEM = (
    "You are a precise Indian legal-document extractor. You extract facts ONLY "
    "from the provided document text. You never invent values. Output STRICT JSON."
)


def field_schema(filing_type: str) -> List[str]:
    return _SCHEMAS.get(filing_type, _SCHEMAS["chargesheet"])


def extract_fields(text: str, filing_type: str = "chargesheet") -> Dict[str, Any]:
    """Return {field: {value, confidence (0..1), source_snippet}} for the given
    filing type. Fields not found get value=null and confidence=0."""
    fields = field_schema(filing_type)
    user = (
        f"DOCUMENT TEXT (digitised):\n\"\"\"\n{text}\n\"\"\"\n\n"
        f"Extract these fields for this {filing_type}: {', '.join(fields)}.\n"
        "Return a JSON object mapping each field to an object with keys:\n"
        '  "value"          (string or list; null if not present),\n'
        '  "confidence"     (0.0-1.0 -- how sure you are it is correct),\n'
        '  "source_snippet" (a short verbatim quote from the text supporting it, or null).\n'
        "Ground every value strictly in the text. If a field is absent or "
        "unclear, use null with a low confidence. Respond with JSON only."
    )
    raw = sarvam.chat(
        messages=[{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
        temperature=0.1,
    )
    return _safe_json_object(raw)


def detect_filing_type(text: str) -> str:
    """Cheap heuristic + LLM fallback to pick chargesheet vs judgment."""
    head = text[:4000].lower()
    if any(k in head for k in ("charge sheet", "chargesheet", "आरोप पत्र", "challan", "f.i.r", "investigating officer")):
        return "chargesheet"
    if any(k in head for k in ("judgment", "order", "coram", "versus", "appellant", "respondent", "hon'ble")):
        return "judgment"
    ans = sarvam.chat(
        messages=[
            {"role": "system", "content": "Reply with exactly one word."},
            {"role": "user", "content": f"Is this an Indian 'chargesheet' or a 'judgment'? Text:\n{text[:2000]}"},
        ],
        temperature=0.0,
    ).strip().lower()
    return "judgment" if "judg" in ans else "chargesheet"


def _safe_json_object(raw: str) -> Dict[str, Any]:
    """Parse a JSON object out of a model response, tolerating code fences and
    surrounding prose."""
    if not raw:
        return {}
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    candidate = fenced.group(1) if fenced else raw
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        brace = re.search(r"\{.*\}", candidate, re.DOTALL)
        if brace:
            try:
                return json.loads(brace.group(0))
            except json.JSONDecodeError:
                pass
    return {"_raw": raw}
