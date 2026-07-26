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
import time
from pathlib import Path
from typing import Any, Optional

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
    ipc_sections: list[IpcSectionOut]
    pages: Optional[list[dict[str, Any]]] = None
    # Supabase id when persistence succeeded (best-effort); null otherwise.
    document_id: Optional[str] = None
    filing_type: Optional[str] = None


class EnglishExtractionIn(BaseModel):
    raw_extraction: Optional[str] = None
    pages: Optional[list[dict[str, Any]]] = None
    document_id: Optional[str] = None
    source_language: str = "auto"


class EnglishExtractionOut(BaseModel):
    eng_extraction: str
    document_id: Optional[str] = None


# ── MVP: digitise + coordinates first, English generation second ────────────

@router.post("/documents/process", response_model=ProcessDocumentOut)
def process_document(
    file: UploadFile = File(...),
    language: str = Form("en-IN"),
):
    """Digitise to clean text + structured block coordinates, summarize IPC
    refs, and persist. English generation is a separate chat-completion API."""
    start = time.perf_counter()
    logger.info(
        "document.process.start filename=%s content_type=%s language=%s",
        file.filename,
        file.content_type,
        language,
    )
    processed, pages, job_id = _digitise_and_summarise(file=file, language=language)
    logger.info("document.process.detect_filing_type.start raw_chars=%s", len(processed.raw_extraction))
    processed.filing_type = extraction.detect_filing_type(processed.raw_extraction)
    processed.document_id = _persist_process(
        file_name=file.filename or "upload.pdf",
        language=language,
        processed=processed,
        pages=pages,
        job_id=job_id,
    )
    logger.info(
        "document.process.done filename=%s document_id=%s filing_type=%s raw_chars=%s english_chars=%s ipc_count=%s elapsed_ms=%.1f",
        file.filename,
        processed.document_id,
        processed.filing_type,
        len(processed.raw_extraction),
        0,
        len(processed.ipc_sections),
        (time.perf_counter() - start) * 1000,
    )
    return processed


@router.post("/documents/english", response_model=EnglishExtractionOut)
def generate_english(body: EnglishExtractionIn):
    """Generate English text from raw/page extraction using Sarvam chat
    completions. Uses page-level chunks when page blocks are available."""
    start = time.perf_counter()
    logger.info(
        "document.english.start document_id=%s source_language=%s raw_chars=%s pages=%s",
        body.document_id,
        body.source_language,
        len(body.raw_extraction or ""),
        len(body.pages or []),
    )

    source_text = body.raw_extraction or ""
    pages = body.pages
    if body.document_id and not source_text and pages is None:
        bundle = repo.get_document_bundle(body.document_id)
        if not bundle:
            raise HTTPException(404, "document not found")
        digitization = bundle["digitizations"][0] if bundle.get("digitizations") else {}
        source_text = digitization.get("content") or ""
        content_json = digitization.get("content_json")
        pages = content_json if isinstance(content_json, list) else None

    if not source_text.strip() and not pages:
        raise HTTPException(400, "raw_extraction or pages is required")

    try:
        english = sarvam.generate_english_with_chat(
            raw_text=source_text,
            pages=pages,
            source_language=body.source_language,
        )
    except sarvam.SarvamError as exc:
        logger.exception("document.english.sarvam_error document_id=%s", body.document_id)
        raise HTTPException(502, f"Sarvam chat completion failed: {exc}")

    if body.document_id and english:
        try:
            repo.insert_translation(
                document_id=body.document_id,
                target_language="en-IN",
                source_language=body.source_language,
                translated_text=english,
                model=sarvam.CHAT_TRANSLATION_MODEL,
            )
            logger.info("document.english.persist.done document_id=%s", body.document_id)
        except Exception as exc:  # noqa: BLE001 - translation persistence is best-effort
            logger.warning("English persistence failed (continuing): %s", exc)

    logger.info(
        "document.english.done document_id=%s english_chars=%s elapsed_ms=%.1f",
        body.document_id,
        len(english),
        (time.perf_counter() - start) * 1000,
    )
    return EnglishExtractionOut(eng_extraction=english, document_id=body.document_id)


@router.get("/documents/{document_id}")
def get_document(document_id: str):
    """Return the persisted document with its digitizations/extractions/translations."""
    logger.info("document.get.start document_id=%s", document_id)
    bundle = repo.get_document_bundle(document_id)
    if not bundle:
        logger.info("document.get.not_found document_id=%s", document_id)
        raise HTTPException(404, "document not found")
    logger.info("document.get.done document_id=%s", document_id)
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
            "englishText": "",
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
        "eng_extraction": "",
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
    and summarise IPC. Returns (ProcessDocumentOut, pages, job_id)."""
    suffix = Path(file.filename or "upload.pdf").suffix or ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(file.file.read())
        tmp_path = tmp.name
    file_size = Path(tmp_path).stat().st_size
    logger.info(
        "document.upload.saved filename=%s tmp_path=%s bytes=%s",
        file.filename,
        tmp_path,
        file_size,
    )

    try:
        # DI job accepts md/html only; the bundle also ships per-page layout
        # JSON (blocks w/ bbox + confidence), which digitise() returns as pages.
        logger.info("document.digitise.start filename=%s language=%s", file.filename, language)
        result = sarvam.digitise(tmp_path, language=language, output_format="md")
        pages = result.content if isinstance(result.content, list) else []
        clean_md = (
            sarvam.blocks_to_markdown(pages) if pages else sarvam.strip_data_uris(result.raw_text)
        )
        logger.info(
            "document.digitise.done filename=%s job_id=%s raw_chars=%s clean_chars=%s pages=%s output_files=%s",
            file.filename,
            result.job_id,
            len(result.raw_text),
            len(clean_md),
            len(pages),
            len(result.output_files),
        )
        logger.info("document.ipc.start filename=%s", file.filename)
        ipc_sections = _summarize_ipc_sections(clean_md)
        logger.info("document.ipc.done filename=%s ipc_sections=%s", file.filename, [s.ipc for s in ipc_sections])
        processed = ProcessDocumentOut(
            raw_extraction=clean_md,
            ipc_sections=ipc_sections,
            pages=pages or None,
        )
        return processed, pages, str(result.job_id)
    except sarvam.SarvamError as e:
        logger.exception("document.process.sarvam_error filename=%s", file.filename)
        raise HTTPException(502, f"Sarvam request failed: {e}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)
        logger.info("document.upload.cleaned tmp_path=%s", tmp_path)


def _summarize_ipc_sections(markdown: str) -> list[IpcSectionOut]:
    refs = extract_ipc_references(markdown)
    unique_sections = sorted({ref.section for ref in refs}, key=_section_sort_key)
    logger.info("document.ipc.detected refs=%s unique_sections=%s", len(refs), unique_sections)
    summaries: list[IpcSectionOut] = []
    for section in unique_sections:
        logger.info("document.ipc.summary.start section=%s", section)
        summary = sarvam.summarize_ipc_section(section)
        logger.info("document.ipc.summary.done section=%s summary_chars=%s", section, len(summary))
        summaries.append(IpcSectionOut(ipc=section, summary=summary))
    return summaries


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
        logger.info("document.persist.start file_name=%s filing_type=%s", file_name, processed.filing_type)
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
        if processed.ipc_sections:
            repo.insert_extraction(
                document_id=doc["id"],
                filing_type=processed.filing_type,
                fields={"ipc_sections": [s.model_dump() for s in processed.ipc_sections]},
                model=sarvam.IPC_SUMMARY_MODEL,
            )
        logger.info("document.persist.done document_id=%s", doc["id"])
        return doc["id"]
    except Exception as exc:  # noqa: BLE001 - persistence is best-effort for the MVP
        logger.warning("Supabase persistence failed (continuing without it): %s", exc)
        return None
