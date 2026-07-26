"""API routes.

This team's MVP centrepiece is `POST /api/documents/process` — one call that
digitises a filing, translates it to English, and summarises the IPC sections
found. Results are persisted to Supabase (best-effort) so the workbench team
can read them; `GET /api/documents/{id}` returns the stored bundle.

The `/api/cases/...` + `/ask` endpoints (in-memory store) are the workbench
teammate's surface — left intact.
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app import repositories as repo
from app.services import extraction, sarvam, store
from app.services.citations import extract_ipc_references

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


class CreateCaseIn(BaseModel):
    title: str


class AskIn(BaseModel):
    question: str


class IpcSectionOut(BaseModel):
    ipc: str
    summary: str


class ProcessDocumentOut(BaseModel):
    raw_extraction: str
    eng_extraction: str
    ipc_sections: list[IpcSectionOut]
    # Supabase id when persistence succeeded (best-effort); null otherwise.
    document_id: Optional[str] = None
    filing_type: Optional[str] = None


# ── MVP: single-call digitise → translate → IPC summary (+ persist) ─────────

@router.post("/documents/process", response_model=ProcessDocumentOut)
def process_document(
    file: UploadFile = File(...),
    language: str = Form("en-IN"),
):
    """Digitise (structured JSON, watermark/chrome removed), translate to
    English, summarise IPC refs, and persist (with block coords + confidence)."""
    processed, pages, job_id = _digitise_and_summarise(file=file, language=language)
    processed.filing_type = extraction.detect_filing_type(processed.raw_extraction)
    processed.document_id = _persist_process(
        file_name=file.filename or "upload.pdf",
        language=language,
        processed=processed,
        pages=pages,
        job_id=job_id,
    )
    return processed


@router.get("/documents/{document_id}")
def get_document(document_id: str):
    """Return the persisted document with its digitizations/extractions/translations."""
    bundle = repo.get_document_bundle(document_id)
    if not bundle:
        raise HTTPException(404, "document not found")
    return bundle


# ── Workbench teammate's surface (in-memory store) — left intact ────────────

@router.post("/cases")
def create_case(body: CreateCaseIn):
    return store.create_case(body.title)


@router.post("/cases/{case_id}/documents")
def upload_document(
    case_id: str,
    file: UploadFile = File(...),
    output_format: str = Form("md"),
    language: str = Form("en-IN"),
):
    """Upload a filing → run the Sarvam DI job → store the digitised text."""
    if store.get_case(case_id) is None:
        raise HTTPException(404, "case not found")

    processed, _pages, _job_id = _digitise_and_summarise(file=file, language=language)
    raw_text = processed.raw_extraction

    filing_type = extraction.detect_filing_type(raw_text)
    doc = store.add_document(
        case_id,
        {
            "fileName": file.filename,
            "filingType": filing_type,
            "outputFormat": output_format,
            "digitisedText": raw_text,
            "englishText": processed.eng_extraction,
            "ipcSections": [section.model_dump() for section in processed.ipc_sections],
            "status": "ready",
        },
    )
    return {
        "id": doc["id"],
        "caseId": case_id,
        "fileName": doc["fileName"],
        "filingType": filing_type,
        "status": "ready",
        "preview": raw_text[:1200],
        "raw_extraction": processed.raw_extraction,
        "eng_extraction": processed.eng_extraction,
        "ipc_sections": processed.ipc_sections,
    }


@router.post("/cases/{case_id}/documents/{document_id}/extract")
def extract_document(case_id: str, document_id: str):
    """Document-typed field extraction (fields + per-field confidence)."""
    doc = _find_doc(case_id, document_id)
    fields = extraction.extract_fields(doc["digitisedText"], filing_type=doc["filingType"])
    return {"documentId": document_id, "filingType": doc["filingType"], "fields": fields}


@router.post("/cases/{case_id}/ask")
def ask(case_id: str, body: AskIn):
    """Answer grounded ONLY in the case's digitised documents."""
    docs = store.get_documents(case_id)
    if not docs:
        raise HTTPException(400, "no digitised documents in this case yet")

    context = "\n\n".join(
        f"[{d['fileName']} · {d['filingType']}]\n{d['digitisedText']}" for d in docs
    )
    system = (
        "You are Samajh, a legal filing-understanding assistant. Answer ONLY from "
        "the provided document text. If the answer is not in the text, say so. "
        "Cite the document name you used. Do not invent facts or citations."
    )
    user = f"DOCUMENTS:\n{context}\n\nQUESTION: {body.question}"
    answer = sarvam.chat(
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.2,
    )
    return {
        "caseId": case_id,
        "question": body.question,
        "answer": answer,
        "sources": [{"fileName": d["fileName"], "filingType": d["filingType"]} for d in docs],
    }


# ── helpers ─────────────────────────────────────────────────────────────────

def _find_doc(case_id: str, document_id: str):
    if store.get_case(case_id) is None:
        raise HTTPException(404, "case not found")
    for d in store.get_documents(case_id):
        if d["id"] == document_id:
            return d
    raise HTTPException(404, "document not found")


def _digitise_and_summarise(file: UploadFile, language: str):
    """Digitise to structured JSON, rebuild clean text (no watermark/base64),
    translate, and summarise IPC. Returns (ProcessDocumentOut, pages, job_id)."""
    suffix = Path(file.filename or "upload.pdf").suffix or ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(file.file.read())
        tmp_path = tmp.name

    try:
        # DI job accepts md/html only; the bundle also ships per-page layout
        # JSON (blocks w/ bbox + confidence), which digitise() returns as pages.
        result = sarvam.digitise(tmp_path, language=language, output_format="md")
        pages = result.content if isinstance(result.content, list) else []
        clean_md = (
            sarvam.blocks_to_markdown(pages) if pages else sarvam.strip_data_uris(result.raw_text)
        )
        eng_extraction = sarvam.translate_to_english(clean_md, source_language_code=language)
        ipc_sections = _summarize_ipc_sections(clean_md)
        processed = ProcessDocumentOut(
            raw_extraction=clean_md,
            eng_extraction=eng_extraction,
            ipc_sections=ipc_sections,
        )
        return processed, pages, str(result.job_id)
    except sarvam.SarvamError as e:
        raise HTTPException(502, f"Sarvam request failed: {e}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _summarize_ipc_sections(markdown: str) -> list[IpcSectionOut]:
    refs = extract_ipc_references(markdown)
    unique_sections = sorted({ref.section for ref in refs}, key=_section_sort_key)
    return [
        IpcSectionOut(ipc=section, summary=sarvam.summarize_ipc_section(section))
        for section in unique_sections
    ]


def _section_sort_key(section: str) -> tuple[int, str]:
    numeric = "".join(ch for ch in section if ch.isdigit())
    suffix = "".join(ch for ch in section if not ch.isdigit())
    return (int(numeric or 0), suffix)


def _persist_process(
    *,
    file_name: str,
    language: str,
    processed: ProcessDocumentOut,
    pages: Optional[list] = None,
    job_id: Optional[str] = None,
) -> Optional[str]:
    """Best-effort: persist the processed result to Supabase. Never fail the
    request on a DB error — the MVP demo must still return its result.
    `content` = clean text; `content_json` = DI blocks (bbox + confidence)."""
    try:
        doc = repo.insert_document(
            file_name=file_name,
            filing_type=processed.filing_type or "unknown",
            source_language=language,
            page_count=len(pages) if pages else None,
            status="ready",
        )
        repo.insert_digitization(
            document_id=doc["id"],
            output_format="json",
            content=processed.raw_extraction,
            content_json=pages or None,
            sarvam_job_id=job_id,
        )
        if processed.eng_extraction:
            repo.insert_translation(
                document_id=doc["id"],
                target_language="en-IN",
                source_language=language,
                translated_text=processed.eng_extraction,
                model=sarvam.TRANSLATE_MODEL,
            )
        if processed.ipc_sections:
            repo.insert_extraction(
                document_id=doc["id"],
                filing_type=processed.filing_type,
                fields={"ipc_sections": [s.model_dump() for s in processed.ipc_sections]},
                model=sarvam.IPC_SUMMARY_MODEL,
            )
        return doc["id"]
    except Exception as exc:  # noqa: BLE001 - persistence is best-effort for the MVP
        logger.warning("Supabase persistence failed (continuing without it): %s", exc)
        return None
