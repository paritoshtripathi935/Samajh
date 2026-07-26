"""Dead-simple in-memory store so the golden path runs before Supabase is wired.

DEMO ONLY — process-local, not persistent. Replace with Supabase in M1
(cases / documents / answers / corrections tables). Kept behind these helpers
so swapping the backing store is a one-file change.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

_CASES: Dict[str, Dict[str, Any]] = {}
_DOCUMENTS: Dict[str, List[Dict[str, Any]]] = {}  # case_id -> [document, ...]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_case(title: str) -> Dict[str, Any]:
    case_id = str(uuid.uuid4())
    case = {"id": case_id, "title": title, "createdAt": _now()}
    _CASES[case_id] = case
    _DOCUMENTS[case_id] = []
    return case


def get_case(case_id: str) -> Dict[str, Any] | None:
    return _CASES.get(case_id)


def add_document(case_id: str, doc: Dict[str, Any]) -> Dict[str, Any]:
    doc = {"id": str(uuid.uuid4()), "caseId": case_id, "createdAt": _now(), **doc}
    _DOCUMENTS.setdefault(case_id, []).append(doc)
    return doc


def get_documents(case_id: str) -> List[Dict[str, Any]]:
    return _DOCUMENTS.get(case_id, [])
