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
import json
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from app import repositories as repo
from app.services import extraction, legal_search, sarvam, store
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


class DocumentListItemOut(BaseModel):
    id: str
    file_name: str
    filing_type: str
    source_language: Optional[str] = None
    page_count: Optional[int] = None
    status: str
    vector_ingestion_status: Optional[str] = None
    structured_ingestion_status: Optional[str] = None
    file_ref: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None


class DocumentListOut(BaseModel):
    documents: list[DocumentListItemOut]


class EnglishExtractionIn(BaseModel):
    raw_extraction: Optional[str] = None
    pages: Optional[list[dict[str, Any]]] = None
    document_id: Optional[str] = None
    source_language: str = "auto"


class EnglishExtractionOut(BaseModel):
    eng_extraction: str
    document_id: Optional[str] = None


class LegalSearchItemsIn(BaseModel):
    section_title: str
    section_content: str
    filing_type: Optional[str] = None


class LegalSearchItemOut(BaseModel):
    title: str
    query: str
    rationale: str
    kind: str
    results: list["LegalSearchResultOut"]


class LegalSearchResultOut(BaseModel):
    title: str
    url: str
    snippet: str
    source: str
    doc_type: str
    jurisdiction: Optional[str] = None
    citation: Optional[str] = None


class LegalSearchItemsOut(BaseModel):
    items: list[LegalSearchItemOut]
    model: str


# ── MVP: digitise + coordinates first, English generation second ────────────

@router.get("/documents", response_model=DocumentListOut)
def list_documents(limit: int = 50):
    """Return recently uploaded filings for the dashboard."""
    capped_limit = max(1, min(limit, 100))
    logger.info("document.list.start limit=%s", capped_limit)
    try:
        documents = repo.list_documents(limit=capped_limit)
    except Exception as exc:  # noqa: BLE001
        logger.exception("document.list.failed")
        raise HTTPException(502, f"Supabase document list failed: {exc}") from exc
    logger.info("document.list.done count=%s", len(documents))
    return DocumentListOut(documents=documents)

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
    original_pdf = file.file.read()
    file.file.seek(0)
    processed, pages, job_id = _digitise_and_summarise(file=file, language=language)
    logger.info("document.process.detect_filing_type.start raw_chars=%s", len(processed.raw_extraction))
    processed.filing_type = extraction.detect_filing_type(processed.raw_extraction)
    processed.document_id = _persist_process(
        file_name=file.filename or "upload.pdf",
        language=language,
        processed=processed,
        pages=pages,
        job_id=job_id,
        original_pdf=original_pdf,
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

    source_text, pages = _resolve_english_source(body)

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


@router.post("/documents/english/stream")
def stream_english(body: EnglishExtractionIn):
    """Stream English Markdown as newline-delimited JSON events.

    Each `delta` event is emitted from Sarvam's `stream=True` chat completion.
    The final `done` event includes the stitched Markdown.
    """
    start = time.perf_counter()
    logger.info(
        "document.english_stream.start document_id=%s source_language=%s raw_chars=%s pages=%s",
        body.document_id,
        body.source_language,
        len(body.raw_extraction or ""),
        len(body.pages or []),
    )
    source_text, pages = _resolve_english_source(body)
    chunks = sarvam.english_source_chunks(raw_text=source_text, pages=pages)

    def events():
        translated: list[str] = []
        try:
            yield _json_line(
                {
                    "type": "start",
                    "document_id": body.document_id,
                    "chunks": len(chunks),
                    "model": sarvam.CHAT_TRANSLATION_MODEL,
                }
            )
            current_chunk_index = 0
            for event in sarvam.iter_english_stream_chunks_with_chat(
                chunks=chunks,
                source_language=body.source_language,
            ):
                event_type = str(event.get("type") or "delta")
                index = int(event["index"])
                if event_type == "chunk_start":
                    yield _json_line(
                        {
                            "type": "chunk_start",
                            "index": index,
                            "total": event["total"],
                        }
                    )
                    continue
                if index != current_chunk_index:
                    if translated and not translated[-1].endswith("\n\n"):
                        separator = "\n\n"
                        translated.append(separator)
                        yield _json_line(
                            {
                                "type": "delta",
                                "index": index,
                                "total": event["total"],
                                "text": separator,
                            }
                        )
                    current_chunk_index = index
                delta = str(event["delta"])
                translated.append(delta)
                yield _json_line(
                    {
                        "type": "delta",
                        "index": index,
                        "total": event["total"],
                        "text": delta,
                    }
                )

            english = "".join(translated).strip()

            if body.document_id and english:
                try:
                    repo.insert_translation(
                        document_id=body.document_id,
                        target_language="en-IN",
                        source_language=body.source_language,
                        translated_text=english,
                        model=sarvam.CHAT_TRANSLATION_MODEL,
                    )
                    logger.info("document.english_stream.persist.done document_id=%s", body.document_id)
                except Exception as exc:  # noqa: BLE001 - translation persistence is best-effort
                    logger.warning("English stream persistence failed (continuing): %s", exc)

            logger.info(
                "document.english_stream.done document_id=%s english_chars=%s elapsed_ms=%.1f",
                body.document_id,
                len(english),
                (time.perf_counter() - start) * 1000,
            )
            yield _json_line(
                {
                    "type": "done",
                    "document_id": body.document_id,
                    "eng_extraction": english,
                }
            )
        except sarvam.SarvamError as exc:
            logger.exception("document.english_stream.sarvam_error document_id=%s", body.document_id)
            yield _json_line({"type": "error", "message": f"Sarvam chat completion failed: {exc}"})

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/documents/search-items", response_model=LegalSearchItemsOut)
def generate_search_items(body: LegalSearchItemsIn):
    """Generate contextual legal-research searches from an analysis section."""
    if not body.section_title.strip() or not body.section_content.strip():
        raise HTTPException(400, "section_title and section_content are required")
    try:
        generated = sarvam.generate_legal_search_items(
            section_title=body.section_title,
            section_content=body.section_content,
            filing_type=body.filing_type,
        )
        items = legal_search.search_generated_items(generated)
    except sarvam.SarvamError as exc:
        logger.exception("document.search_items.sarvam_error section=%s", body.section_title)
        raise HTTPException(502, f"Sarvam search generation failed: {exc}") from exc
    return LegalSearchItemsOut(items=items, model=sarvam.RESEARCH_SEARCH_MODEL)


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


@router.get("/documents/{document_id}/pdf")
def get_document_pdf(document_id: str):
    """Serve the original PDF kept in the private Supabase Storage bucket."""
    doc = repo.get_document(document_id)
    if not doc:
        raise HTTPException(404, "document not found")
    file_ref = doc.get("file_ref")
    if not file_ref:
        raise HTTPException(404, "original PDF was not stored")
    try:
        content = repo.download_document_file(file_ref)
    except Exception as exc:  # noqa: BLE001
        logger.warning("document.pdf.download_failed document_id=%s error=%s", document_id, exc)
        raise HTTPException(502, "could not retrieve original PDF") from exc
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{doc["file_name"]}"'},
    )


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


def _resolve_english_source(body: EnglishExtractionIn) -> tuple[str, Optional[list[dict[str, Any]]]]:
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
    return source_text, pages


def _json_line(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"


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
        summary = sarvam.summarize_ipc_section(section) or ""
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
    original_pdf: Optional[bytes] = None,
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
        if original_pdf:
            try:
                file_ref = repo.upload_document_file(
                    document_id=doc["id"],
                    file_name=file_name,
                    content=original_pdf,
                )
                repo.update_document(doc["id"], file_ref=file_ref)
            except Exception as exc:  # noqa: BLE001
                # Keep the extraction available even if Storage is temporarily
                # unavailable; file_ref remains null and the PDF endpoint says so.
                logger.warning(
                    "Supabase PDF upload failed document_id=%s (continuing): %s",
                    doc["id"],
                    exc,
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
