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
import re
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
    raw_text, pages, files = _read_output(written or out_zip, out_dir)

    metrics = None
    try:
        metrics = job.get_page_metrics()
    except Exception:  # noqa: BLE001 - metrics are best-effort
        pass

    return DigitiseResult(
        job_id=str(job.job_id),
        output_format=output_format,
        content=pages,       # structured layout blocks (bbox/confidence/order)
        raw_text=raw_text,   # rendered md/html — JSON kept out of it
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

    merged_pages: List[Dict[str, Any]] = []
    offset = 0
    for result in results:
        pages = result.content if isinstance(result.content, list) else []
        for page in pages:
            page = dict(page)
            if isinstance(page.get("page_num"), int):
                page["page_num"] += offset
            merged_pages.append(page)
        offset += len(pages)

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
        content=merged_pages,
        raw_text=raw_text,
        output_files=output_files,
        page_metrics=page_metrics,
    )


def _read_output(written: str, fallback_dir: str) -> Tuple[str, List[Dict[str, Any]], List[str]]:
    """The DI download bundle holds the rendered text (document.md/.html) AND a
    per-page layout file (page_NNN.json — blocks with bbox/confidence/reading
    order). Return them SEPARATELY so the JSON never leaks into the text:
    (rendered_text, pages, all_files)."""
    p = Path(written) if written else Path(fallback_dir)
    if p.is_file() and zipfile.is_zipfile(p):
        extract_dir = Path(fallback_dir) / "extracted"
        with zipfile.ZipFile(p, "r") as archive:
            archive.extractall(extract_dir)
        candidates = sorted(f for f in extract_dir.glob("**/*") if f.is_file())
    elif p.is_file():
        candidates = [p]
    else:
        candidates = sorted(f for f in p.glob("**/*") if f.is_file())

    text_parts: List[str] = []
    pages: List[Dict[str, Any]] = []
    for f in candidates:
        suffix = f.suffix.lower()
        if suffix == ".json":
            try:
                blob = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for obj in _iter_json_objects(blob):
                if isinstance(obj, list):
                    pages.extend(x for x in obj if isinstance(x, dict))
                elif isinstance(obj, dict):
                    if isinstance(obj.get("pages"), list):
                        pages.extend(x for x in obj["pages"] if isinstance(x, dict))
                    else:
                        pages.append(obj)
        elif suffix in (".md", ".markdown", ".html", ".htm", ".txt", ""):
            text_parts.append(f.read_text(encoding="utf-8", errors="replace"))
    pages.sort(key=lambda pg: pg.get("page_num") or 0)
    return "\n\n".join(text_parts), pages, [str(f) for f in candidates]


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


_DATA_URI_IMG_RE = re.compile(r"!\[[^\]]*\]\(\s*data:[^)]*\)")
_BARE_DATA_URI_RE = re.compile(r"data:image/[A-Za-z0-9.+-]+;base64,[A-Za-z0-9+/=\s]+")


def strip_data_uris(md: str) -> str:
    """Drop embedded base64 images from digitised Markdown. They must never be
    sent to the translator (they pollute the output) and add nothing to prose."""
    md = _DATA_URI_IMG_RE.sub("", md)
    md = _BARE_DATA_URI_RE.sub("", md)
    return md


# ── DI JSON blocks → clean text (drops watermarks / page chrome) ────────────
#
# The `json` output_format returns per-page blocks, each with coordinates
# (bbox), layout_tag, confidence, reading_order and text. We drop document
# chrome (headers/footers/page numbers/watermark images) and known watermark
# text, keep everything else in reading order. The full blocks are preserved
# separately (content_json) for jump-to-source + confidence flags.

_HEADING_TAGS = {"headline", "title", "section-header", "section_header"}
_NOISE_TAGS = {"header", "footer", "footnote", "page-number", "page_number", "image", "watermark"}
_NOISE_TEXT = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"studocu",
        r"downloaded by\b.*@",
        r"scan to open",
        r"this document is available on",
        r"not sponsored or endorsed",
    )
]


def _iter_json_objects(text: str):
    """Yield JSON values from text that is either one JSON doc, a JSON array,
    or several concatenated / newline-delimited objects."""
    text = text.strip()
    if not text:
        return
    try:
        yield json.loads(text)
        return
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    idx, n = 0, len(text)
    while idx < n:
        while idx < n and text[idx] in " \t\r\n":
            idx += 1
        if idx >= n:
            break
        try:
            obj, end = decoder.raw_decode(text, idx)
        except json.JSONDecodeError:
            break
        yield obj
        idx = end


def blocks_to_markdown(pages: List[Dict[str, Any]], drop_noise: bool = True) -> str:
    """Reconstruct clean Markdown from DI page blocks, in reading order."""
    out: List[str] = []
    for page in sorted(pages, key=lambda p: p.get("page_num") or 0):
        blocks = page.get("blocks") or []
        for b in sorted(blocks, key=lambda x: x.get("reading_order") or 0):
            tag = str(b.get("layout_tag") or "").lower()
            text = str(b.get("text") or "").strip()
            if not text:
                continue
            if drop_noise and (tag in _NOISE_TAGS or any(p.search(text) for p in _NOISE_TEXT)):
                continue
            out.append(f"## {text}" if tag in _HEADING_TAGS else text)
    return "\n\n".join(out)


def translate_to_english(input_text: str, source_language_code: str) -> str:
    """Translate digitised Markdown into English, chunking long legal filings.
    Embedded base64 images are stripped first (the scan stays on the original)."""
    if not input_text.strip():
        return ""
    text = strip_data_uris(input_text)
    if source_language_code.lower() == "en-in":
        return text

    chunks = _chunk_text(text, max_chars=TRANSLATE_CHUNK_SIZE)
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
