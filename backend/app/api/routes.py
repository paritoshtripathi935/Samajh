"""Golden-path routes: create a case, upload+digitise a filing, extract typed
fields, and ask a cited question grounded in the digitised text.

State lives in an in-memory store (app.services.store) for now — swap for
Supabase in M1. Shapes line up with the frontend's lib/api.ts.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.services import extraction, sarvam, store
from app.services.citations import extract_ipc_references

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


@router.post("/cases")
def create_case(body: CreateCaseIn):
    return store.create_case(body.title)


@router.post("/documents/process", response_model=ProcessDocumentOut)
def process_document(
    file: UploadFile = File(...),
    language: str = Form("en-IN"),
    output_format: str = Form("md"),
):
    """Single-call API: digitise, translate to English, and summarize IPC refs."""
    if output_format != "md":
        raise HTTPException(400, "single process API currently supports output_format=md only")
    return _process_upload(file=file, language=language, output_format=output_format)


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

    processed = _process_upload(file=file, language=language, output_format=output_format)
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
    # Don't ship the full text back in the create response; return a preview.
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


def _find_doc(case_id: str, document_id: str):
    if store.get_case(case_id) is None:
        raise HTTPException(404, "case not found")
    for d in store.get_documents(case_id):
        if d["id"] == document_id:
            return d
    raise HTTPException(404, "document not found")


def _process_upload(file: UploadFile, language: str, output_format: str) -> ProcessDocumentOut:
    suffix = Path(file.filename or "upload.pdf").suffix or ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(file.file.read())
        tmp_path = tmp.name

    try:
        result = sarvam.digitise(tmp_path, language=language, output_format=output_format)
        raw_extraction = result.raw_text
        eng_extraction = sarvam.translate_to_english(raw_extraction, source_language_code=language)
        ipc_sections = _summarize_ipc_sections(raw_extraction)
        return ProcessDocumentOut(
            raw_extraction=raw_extraction,
            eng_extraction=eng_extraction,
            ipc_sections=ipc_sections,
        )
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
