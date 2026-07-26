"""Thin data-access layer over the Supabase pipeline tables:
documents · digitizations · extractions · translations.

Every function returns plain dicts (the inserted/selected row). Keeping all
table access here means the schema lives in exactly one place on the backend.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.db import supabase
from app.core.settings import settings


# ── documents ───────────────────────────────────────────────────────────────

def insert_document(
    *,
    file_name: str,
    filing_type: str = "unknown",
    source_language: Optional[str] = None,
    page_count: Optional[int] = None,
    file_ref: Optional[str] = None,
    case_id: Optional[str] = None,
    status: str = "uploaded",
) -> Dict[str, Any]:
    row = {
        "file_name": file_name,
        "filing_type": filing_type,
        "source_language": source_language,
        "page_count": page_count,
        "file_ref": file_ref,
        "case_id": case_id,
        "status": status,
    }
    res = supabase().table("documents").insert(row).execute()
    return res.data[0]


def update_document(document_id: str, **fields: Any) -> Dict[str, Any]:
    res = supabase().table("documents").update(fields).eq("id", document_id).execute()
    return res.data[0]


def get_document(document_id: str) -> Optional[Dict[str, Any]]:
    res = supabase().table("documents").select("*").eq("id", document_id).limit(1).execute()
    return res.data[0] if res.data else None


def list_documents(limit: int = 50) -> List[Dict[str, Any]]:
    res = (
        supabase()
        .table("documents")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


def upload_document_file(*, document_id: str, file_name: str, content: bytes) -> str:
    """Upload an original filing and return its stable Storage object path."""
    safe_name = file_name.replace("\\", "_").replace("/", "_") or "document.pdf"
    path = f"{document_id}/{safe_name}"
    supabase().storage.from_(settings.supabase_documents_bucket).upload(
        path,
        content,
        {"content-type": "application/pdf", "upsert": "true"},
    )
    return path


def download_document_file(file_ref: str) -> bytes:
    """Download a private original filing by its Storage object path."""
    return supabase().storage.from_(settings.supabase_documents_bucket).download(file_ref)


# ── digitizations ───────────────────────────────────────────────────────────

def insert_digitization(
    *,
    document_id: str,
    output_format: str,
    content: Optional[str] = None,
    content_json: Optional[Any] = None,
    page_metrics: Optional[Any] = None,
    sarvam_job_id: Optional[str] = None,
) -> Dict[str, Any]:
    row = {
        "document_id": document_id,
        "output_format": output_format,
        "content": content,
        "content_json": content_json,
        "page_metrics": page_metrics,
        "sarvam_job_id": sarvam_job_id,
    }
    res = supabase().table("digitizations").insert(row).execute()
    return res.data[0]


def latest_digitization(document_id: str) -> Optional[Dict[str, Any]]:
    res = (
        supabase()
        .table("digitizations")
        .select("*")
        .eq("document_id", document_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


# ── extractions ─────────────────────────────────────────────────────────────

def insert_extraction(
    *, document_id: str, filing_type: Optional[str], fields: Dict[str, Any], model: Optional[str] = None
) -> Dict[str, Any]:
    row = {"document_id": document_id, "filing_type": filing_type, "fields": fields, "model": model}
    res = supabase().table("extractions").insert(row).execute()
    return res.data[0]


# ── translations ────────────────────────────────────────────────────────────

def insert_translation(
    *,
    document_id: str,
    target_language: str,
    translated_text: str,
    source_language: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    row = {
        "document_id": document_id,
        "target_language": target_language,
        "translated_text": translated_text,
        "source_language": source_language,
        "model": model,
    }
    res = supabase().table("translations").insert(row).execute()
    return res.data[0]


# ── bundle (document + its pipeline outputs) ────────────────────────────────

def get_document_bundle(document_id: str) -> Optional[Dict[str, Any]]:
    doc = get_document(document_id)
    if not doc:
        return None
    sb = supabase()
    digs = sb.table("digitizations").select("id,output_format,content,content_json,sarvam_job_id,created_at").eq("document_id", document_id).order("created_at", desc=True).execute().data
    exts = sb.table("extractions").select("*").eq("document_id", document_id).order("created_at", desc=True).execute().data
    trans = sb.table("translations").select("id,target_language,source_language,translated_text,model,created_at").eq("document_id", document_id).order("created_at", desc=True).execute().data
    return {"document": doc, "digitizations": digs, "extractions": exts, "translations": trans}
