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

router = APIRouter(prefix="/api")


class CreateCaseIn(BaseModel):
    title: str


class AskIn(BaseModel):
    question: str


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

    suffix = Path(file.filename or "upload.pdf").suffix or ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(file.file.read())
        tmp_path = tmp.name

    try:
        result = sarvam.digitise(tmp_path, language=language, output_format=output_format)
    except sarvam.SarvamError as e:
        raise HTTPException(502, f"Sarvam digitise failed: {e}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    filing_type = extraction.detect_filing_type(result.raw_text)
    doc = store.add_document(
        case_id,
        {
            "fileName": file.filename,
            "filingType": filing_type,
            "jobId": result.job_id,
            "outputFormat": result.output_format,
            "digitisedText": result.raw_text,
            "pageMetrics": result.page_metrics,
            "status": "ready",
        },
    )
    # Don't ship the full text back in the create response; return a preview.
    return {
        "id": doc["id"],
        "caseId": case_id,
        "fileName": doc["fileName"],
        "filingType": filing_type,
        "jobId": result.job_id,
        "status": "ready",
        "preview": result.raw_text[:1200],
        "pageMetrics": result.page_metrics,
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
