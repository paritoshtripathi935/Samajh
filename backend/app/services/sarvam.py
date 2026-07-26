"""Sarvam client — wraps the official `sarvamai` SDK.

Verified against docs.sarvam.ai + the SDK surface (v0.1.28), 2026-07-26:

  Base https://api.sarvam.ai · header `api-subscription-key` · auth fail = 403.

  Document Digitization ("Digitise") — the ONLY document REST API. Async job:
      POST /doc-digitization/job/v1                         create_job
      POST /doc-digitization/job/v1/upload-files            get_upload_links
      POST /doc-digitization/job/v1/{job_id}/start          start
      GET  /doc-digitization/job/v1/{job_id}/status         get_status
      POST /doc-digitization/job/v1/{job_id}/download-files  get_download_links
    The SDK's `create_job(...)` returns a job with convenience methods
    (upload_file / start / wait_until_complete / download_output /
    get_page_metrics) that also handle the presigned upload.

  Chat:      POST /v1/chat/completions   models: sarvam-30b | sarvam-105b | sarvam-m
  Translate: POST /translate            models: sarvam-translate:v1 | mayura:v1

  job_parameters:
    language      BCP-47 (default hi-IN): hi-IN, en-IN, bn-IN, ta-IN, te-IN, ...
    output_format "md" (default here) | "html" | "json"   -- NOT "markdown" (400)

  Limits (per the /start validation): file <= 200 MB, <= 10 pages/images per job.
  So a 150-page filing must be split into <=10-page chunks and stitched.

  ⚠️ EXTRACT (schema-based field extraction with per-field confidence) has NO
  public REST endpoint -- it is dashboard-only (dashboard.sarvam.ai). We do
  "extract" ourselves in app.services.extraction by digitising then prompting
  sarvam-30b for typed fields. See that module.

  ⚠️ Whether the `json` output carries page/bbox coordinates is confirmed by
  running scripts/digitise.py --format json on a real file (needs a key).
"""
from __future__ import annotations

import json
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pypdf import PdfReader, PdfWriter
from sarvamai import SarvamAI

from app.core.settings import settings

CHAT_MODEL = "sarvam-30b"          # sarvam-105b for the heavier model
IPC_SUMMARY_MODEL = "sarvam-105b"
TRANSLATE_MODEL = "sarvam-translate:v1"
TRANSLATE_CHUNK_SIZE = 3500
MAX_DI_PAGES = 10


class SarvamError(Exception):
    pass


def _client() -> SarvamAI:
    if not settings.sarvam_api_key:
        raise SarvamError("SARVAM_API_KEY is not set in the backend environment")
    return SarvamAI(api_subscription_key=settings.sarvam_api_key)


# ── Digitise (Document Digitization job) ────────────────────────────────────

@dataclass
class DigitiseResult:
    job_id: str
    output_format: str
    content: Any                 # parsed JSON (dict) when json, else str (md/html)
    raw_text: str                # always the raw text of the output file(s)
    output_files: List[str]
    page_metrics: Optional[Dict[str, Any]]


def digitise(
    file_path: str,
    language: str = "en-IN",
    output_format: str = "md",
    poll_interval: float = 2.0,
    timeout: float = 300.0,
) -> DigitiseResult:
    """Run the full DI job on one PDF (or ZIP of JPEG/PNG) and return the
    digitised output. Blocking; call from a threadpool (sync FastAPI route)."""
    batches = _split_pdf_if_needed(file_path)
    try:
        if len(batches) > 1:
            return _merge_digitise_results(
                [
                    _digitise_single(batch, language, output_format, poll_interval, timeout)
                    for batch in batches
                ]
            )

        return _digitise_single(batches[0], language, output_format, poll_interval, timeout)
    finally:
        for batch in batches:
            if batch != file_path:
                Path(batch).unlink(missing_ok=True)


def _digitise_single(
    file_path: str,
    language: str,
    output_format: str,
    poll_interval: float,
    timeout: float,
) -> DigitiseResult:
    """Run one Sarvam DI job. Caller guarantees PDF page limits are respected."""
    client = _client()
    job = client.document_intelligence.create_job(language=language, output_format=output_format)
    try:
        job.upload_file(file_path)
        job.start()
        status = job.wait_until_complete(poll_interval=poll_interval, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - normalize SDK exceptions at our boundary
        raise SarvamError(str(exc)) from exc

    state = str(getattr(status, "job_state", "")).lower()
    if state not in ("completed", "partiallycompleted"):
        raise SarvamError(f"DI job {job.job_id} ended in state '{state}'")

    out_dir = tempfile.mkdtemp(prefix="samajh_di_")
    out_zip = str(Path(out_dir) / "output.zip")
    written = job.download_output(out_zip)
    raw_text, files = _read_output(written or out_zip, out_dir)

    content: Any = raw_text
    if output_format == "json":
        try:
            content = json.loads(raw_text)
        except json.JSONDecodeError:
            pass  # leave as raw text; caller can inspect

    metrics = None
    try:
        metrics = job.get_page_metrics()
    except Exception:  # noqa: BLE001 - metrics are best-effort
        pass

    return DigitiseResult(
        job_id=str(job.job_id),
        output_format=output_format,
        content=content,
        raw_text=raw_text,
        output_files=files,
        page_metrics=metrics,
    )


def _split_pdf_if_needed(file_path: str) -> List[str]:
    path = Path(file_path)
    if path.suffix.lower() != ".pdf":
        return [file_path]

    try:
        reader = PdfReader(file_path)
    except Exception as exc:  # noqa: BLE001
        raise SarvamError(f"Could not read PDF before digitisation: {exc}") from exc

    total_pages = len(reader.pages)
    if total_pages <= MAX_DI_PAGES:
        return [file_path]

    batch_paths: List[str] = []
    for start in range(0, total_pages, MAX_DI_PAGES):
        writer = PdfWriter()
        for page in reader.pages[start : start + MAX_DI_PAGES]:
            writer.add_page(page)

        tmp = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=f".pages-{start + 1}-{min(start + MAX_DI_PAGES, total_pages)}.pdf",
        )
        with tmp:
            writer.write(tmp)
        batch_paths.append(tmp.name)

    return batch_paths


def _merge_digitise_results(results: List[DigitiseResult]) -> DigitiseResult:
    if not results:
        raise SarvamError("No digitisation results to merge")

    raw_text = "\n\n".join(result.raw_text for result in results if result.raw_text)
    output_files = [file for result in results for file in result.output_files]
    page_metrics = {
        "batches": [
            {
                "job_id": result.job_id,
                "page_metrics": result.page_metrics,
            }
            for result in results
        ]
    }

    return DigitiseResult(
        job_id=",".join(result.job_id for result in results),
        output_format=results[0].output_format,
        content=raw_text,
        raw_text=raw_text,
        output_files=output_files,
        page_metrics=page_metrics,
    )


def _read_output(written: str, fallback_dir: str) -> Tuple[str, List[str]]:
    """download_output may return a file path or a directory. Read either."""
    p = Path(written) if written else Path(fallback_dir)
    if p.is_file() and zipfile.is_zipfile(p):
        extract_dir = Path(fallback_dir) / "extracted"
        with zipfile.ZipFile(p, "r") as archive:
            archive.extractall(extract_dir)
        files = sorted(f for f in extract_dir.glob("**/*") if f.is_file())
        texts = [f.read_text(encoding="utf-8", errors="replace") for f in files]
        return "\n\n".join(texts), [str(f) for f in files]
    if p.is_file():
        return p.read_text(encoding="utf-8", errors="replace"), [str(p)]
    # directory: concatenate every output file (usually one)
    files = sorted(f for f in p.glob("**/*") if f.is_file())
    texts = [f.read_text(encoding="utf-8", errors="replace") for f in files]
    return "\n\n".join(texts), [str(f) for f in files]


# ── Chat (grounded answers over digitised text) ─────────────────────────────

def chat(
    messages: List[Dict[str, str]],
    model: str = CHAT_MODEL,
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
) -> str:
    client = _client()
    resp = client.chat.completions(
        messages=messages, model=model, temperature=temperature, max_tokens=max_tokens
    )
    try:
        return resp.choices[0].message.content or ""
    except (AttributeError, IndexError):
        return ""


# ── Translate (regional -> plain Hindi/English) ─────────────────────────────

def translate(
    input_text: str,
    target_language_code: str,
    source_language_code: str = "auto",
    mode: str = "formal",
) -> str:
    client = _client()
    resp = client.text.translate(
        input=input_text,
        source_language_code=source_language_code,
        target_language_code=target_language_code,
        model=TRANSLATE_MODEL,
        mode=mode,
    )
    return getattr(resp, "translated_text", "") or ""


def translate_to_english(input_text: str, source_language_code: str) -> str:
    """Translate digitised Markdown into English, chunking long legal filings."""
    if not input_text.strip():
        return ""
    if source_language_code.lower() == "en-in":
        return input_text

    chunks = _chunk_text(input_text, max_chars=TRANSLATE_CHUNK_SIZE)
    translated = [
        translate(
            chunk,
            source_language_code=source_language_code,
            target_language_code="en-IN",
            mode="formal",
        )
        for chunk in chunks
    ]
    return "\n\n".join(part for part in translated if part)


def summarize_ipc_section(section: str) -> str:
    system = (
        "You are a legal assistant specializing in Indian criminal law. "
        "When given an IPC section number, explain what the section covers, "
        "the offence it defines, and the punishment prescribed. Be concise. "
        "Do not invent details; mention uncertainty if needed."
    )
    return chat(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": f"Explain IPC Section {section}."},
        ],
        model=IPC_SUMMARY_MODEL,
        temperature=0.1,
    )


def _chunk_text(text: str, max_chars: int) -> List[str]:
    chunks: List[str] = []
    current = ""

    for block in re_split_paragraphs(text):
        if len(block) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            chunks.extend(block[i : i + max_chars] for i in range(0, len(block), max_chars))
            continue

        candidate = f"{current}\n\n{block}".strip() if current else block
        if len(candidate) > max_chars:
            chunks.append(current.strip())
            current = block
        else:
            current = candidate

    if current.strip():
        chunks.append(current.strip())
    return chunks


def re_split_paragraphs(text: str) -> List[str]:
    return [block.strip() for block in text.split("\n\n") if block.strip()]
