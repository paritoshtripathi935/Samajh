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
  English generation: POST /v1/chat/completions via sarvam-105b

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
import logging
import re
import tempfile
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import httpx
from pypdf import PdfReader, PdfWriter
from sarvamai import SarvamAI

from app.core.settings import settings

CHAT_MODEL = "sarvam-30b"          # default lightweight chat/fallback model
DOCUMENT_CHAT_MODEL = "sarvam-105b"
IPC_SUMMARY_MODEL = "sarvam-105b"
RESEARCH_SEARCH_MODEL = "sarvam-105b"
CHAT_TRANSLATION_MODEL = "sarvam-105b"
TRANSLATION_MODEL = "sarvam-translate:v1"
TRANSLATION_CHUNK_SIZE = 1900
CHAT_TRANSLATION_CHUNK_SIZE = 3000
CHAT_TRANSLATION_MAX_TOKENS = 4096
MAX_DI_PAGES = 10
logger = logging.getLogger(__name__)


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
    logger.info(
        "sarvam.digitise.start file_path=%s batches=%s language=%s output_format=%s",
        file_path,
        len(batches),
        language,
        output_format,
    )
    try:
        if len(batches) > 1:
            return _digitise_batches_parallel(
                batches=batches,
                language=language,
                output_format=output_format,
                poll_interval=poll_interval,
                timeout=timeout,
            )

        result = _digitise_single(batches[0], language, output_format, poll_interval, timeout)
        logger.info("sarvam.digitise.done job_id=%s raw_chars=%s", result.job_id, len(result.raw_text))
        return result
    finally:
        for batch in batches:
            if batch != file_path:
                Path(batch).unlink(missing_ok=True)
                logger.info("sarvam.digitise.batch_cleaned path=%s", batch)


def _digitise_batches_parallel(
    *,
    batches: List[str],
    language: str,
    output_format: str,
    poll_interval: float,
    timeout: float,
) -> DigitiseResult:
    max_workers = max(1, min(settings.sarvam_di_max_workers, len(batches)))
    logger.info(
        "sarvam.digitise.parallel.start batches=%s workers=%s",
        len(batches),
        max_workers,
    )

    ordered_results: List[DigitiseResult | None] = [None] * len(batches)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_digitise_single, batch, language, output_format, poll_interval, timeout): index
            for index, batch in enumerate(batches)
        }
        for future in as_completed(futures):
            index = futures[future]
            ordered_results[index] = future.result()
            logger.info(
                "sarvam.digitise.parallel.batch_done batch_index=%s job_id=%s",
                index,
                ordered_results[index].job_id if ordered_results[index] else "-",
            )

    results = [result for result in ordered_results if result is not None]
    merged = _merge_digitise_results(results)
    logger.info("sarvam.digitise.parallel.done batches=%s raw_chars=%s", len(results), len(merged.raw_text))
    return merged


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
        logger.info("sarvam.di_job.upload.start path=%s", file_path)
        job.upload_file(file_path)
        logger.info("sarvam.di_job.start job_id=%s", job.job_id)
        job.start()
        status = job.wait_until_complete(poll_interval=poll_interval, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - normalize SDK exceptions at our boundary
        raise SarvamError(str(exc)) from exc

    state = str(getattr(status, "job_state", "")).lower()
    logger.info("sarvam.di_job.status job_id=%s state=%s", job.job_id, state)
    if state not in ("completed", "partiallycompleted"):
        raise SarvamError(f"DI job {job.job_id} ended in state '{state}'")

    out_dir = tempfile.mkdtemp(prefix="samajh_di_")
    out_zip = str(Path(out_dir) / "output.zip")
    written = job.download_output(out_zip)
    raw_text, pages, files = _read_output(written or out_zip, out_dir)
    logger.info(
        "sarvam.di_job.output job_id=%s raw_chars=%s pages=%s files=%s",
        job.job_id,
        len(raw_text),
        len(pages),
        len(files),
    )

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
        logger.info("sarvam.pdf.no_split path=%s pages=%s", file_path, total_pages)
        return [file_path]

    logger.info("sarvam.pdf.split path=%s pages=%s batch_size=%s", file_path, total_pages, MAX_DI_PAGES)
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
        logger.info(
            "sarvam.pdf.batch_created path=%s page_start=%s page_end=%s",
            tmp.name,
            start + 1,
            min(start + MAX_DI_PAGES, total_pages),
        )

    return batch_paths


def _merge_digitise_results(results: List[DigitiseResult]) -> DigitiseResult:
    if not results:
        raise SarvamError("No digitisation results to merge")

    raw_text = "\n\n".join(result.raw_text for result in results if result.raw_text)
    logger.info("sarvam.digitise.merge batches=%s raw_chars=%s", len(results), len(raw_text))
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
    logger.info("sarvam.chat.start model=%s messages=%s", model, len(messages))
    resp = client.chat.completions(
        messages=messages, model=model, temperature=temperature, max_tokens=max_tokens
    )
    try:
        content = resp.choices[0].message.content or ""
        logger.info("sarvam.chat.done model=%s chars=%s", model, len(content))
        return content
    except (AttributeError, IndexError):
        logger.warning("sarvam.chat.empty_response model=%s", model)
        return ""


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


def generate_english_with_chat(
    *,
    raw_text: str,
    pages: Optional[List[Dict[str, Any]]] = None,
    source_language: str = "auto",
) -> str:
    """Generate English Markdown using chat completions, not Sarvam Translate.
    Prefer page-level chunks so long filings stay inside context limits."""
    translated = [
        result["text"]
        for result in iter_english_with_chat(
            raw_text=raw_text,
            pages=pages,
            source_language=source_language,
        )
    ]
    return "\n\n".join(part.strip() for part in translated if part.strip())


def iter_english_with_chat(
    *,
    raw_text: str,
    pages: Optional[List[Dict[str, Any]]] = None,
    source_language: str = "auto",
) -> Iterator[Dict[str, Any]]:
    """Yield completed English Markdown chunks in document order."""
    chunks = english_source_chunks(raw_text=raw_text, pages=pages)
    if not chunks:
        return

    logger.info(
        "sarvam.english_chat.chunked chunks=%s raw_chars=%s pages=%s",
        len(chunks),
        len(raw_text),
        len(pages or []),
    )
    for index, chunk in enumerate(chunks, start=1):
        logger.info("sarvam.english_chat.chunk.start index=%s chars=%s", index, len(chunk))
        text = _english_chat_completion_with_fallback(
            chunk,
            index=index,
            total=len(chunks),
            source_language=source_language,
        )
        logger.info("sarvam.english_chat.chunk.done index=%s output_chars=%s", index, len(text))
        yield {
            "index": index,
            "total": len(chunks),
            "text": text,
        }


def iter_english_stream_with_chat(
    *,
    raw_text: str,
    pages: Optional[List[Dict[str, Any]]] = None,
    source_language: str = "auto",
) -> Iterator[Dict[str, Any]]:
    """Yield token deltas from Sarvam streaming chat completions.

    We still chunk by page/layout first so large documents, tables, and page
    ordering follow the same boundaries as the non-streaming endpoint.
    """
    chunks = english_source_chunks(raw_text=raw_text, pages=pages)
    if not chunks:
        return

    logger.info(
        "sarvam.english_chat.stream.chunked chunks=%s raw_chars=%s pages=%s",
        len(chunks),
        len(raw_text),
        len(pages or []),
    )
    yield from iter_english_stream_chunks_with_chat(chunks=chunks, source_language=source_language)


def iter_english_stream_chunks_with_chat(
    *,
    chunks: list[str],
    source_language: str = "auto",
) -> Iterator[Dict[str, Any]]:
    """Yield token deltas from already-packed English source chunks."""
    for index, chunk in enumerate(chunks, start=1):
        logger.info("sarvam.english_chat.stream.chunk.start index=%s chars=%s", index, len(chunk))
        yield {
            "type": "chunk_start",
            "index": index,
            "total": len(chunks),
        }
        text_parts: list[str] = []
        emitted = False
        delta_count = 0
        for delta in _english_chat_completion_stream(chunk, index=index, total=len(chunks), source_language=source_language):
            emitted = True
            delta_count += 1
            if delta_count == 1:
                logger.info("sarvam.english_chat.stream.first_content_delta index=%s chars=%s", index, len(delta))
            text_parts.append(delta)
            yield {
                "type": "delta",
                "index": index,
                "total": len(chunks),
                "delta": delta,
            }

        text = "".join(text_parts)
        if not emitted or not text.strip():
            logger.warning(
                "sarvam.english_chat.stream.empty_chunk index=%s chars=%s retrying_non_stream",
                index,
                len(chunk),
            )
            text = _english_chat_completion_with_fallback(
                chunk,
                index=index,
                total=len(chunks),
                source_language=source_language,
            )
            yield {
                "type": "delta",
                "index": index,
                "total": len(chunks),
                "delta": text,
            }

        logger.info(
            "sarvam.english_chat.stream.chunk.done index=%s output_chars=%s deltas=%s",
            index,
            len(text),
            delta_count,
        )


def iter_english_chunks_with_translate(
    *,
    chunks: list[str],
    source_language: str = "auto",
    completed_indices: Optional[set[int]] = None,
) -> Iterator[Dict[str, Any]]:
    """Translate remaining chunks concurrently and yield them in document order."""
    completed_indices = completed_indices or set()
    remaining = [
        (index, chunk)
        for index, chunk in enumerate(chunks, start=1)
        if index not in completed_indices
    ]
    if not remaining:
        return
    workers = max(1, min(settings.sarvam_translation_max_workers, len(remaining)))
    logger.info(
        "sarvam.translate.parallel.start chunks=%s resume_from=%s workers=%s",
        len(chunks),
        len(completed_indices),
        workers,
    )
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                _translate_chunk,
                chunk,
                source_language=source_language,
                index=index,
                total=len(chunks),
            ): index
            for index, chunk in remaining
        }
        for future in as_completed(futures):
            index = futures[future]
            yield {"type": "chunk_start", "index": index, "total": len(chunks)}
            yield {
                "type": "delta",
                "index": index,
                "total": len(chunks),
                "delta": future.result(),
            }


def _translate_chunk(chunk: str, *, source_language: str, index: int, total: int) -> str:
    logger.info("sarvam.translate.chunk.start index=%s total=%s chars=%s", index, total, len(chunk))
    detected_source = _indic_source_language(chunk)
    if not detected_source:
        logger.info("sarvam.translate.chunk.passthrough index=%s script=latin", index)
        return chunk.strip()
    # Digitization language is a recognition hint selected at upload time, not
    # reliable language metadata for mixed-language judgments.
    translation_source = detected_source or source_language
    try:
        response = _client().text.translate(
            input=chunk,
            source_language_code=translation_source,
            target_language_code="en-IN",
            mode="formal",
            model=TRANSLATION_MODEL,
        )
        text = str(response.translated_text or "").strip()
        if text:
            residual_before = _indic_character_count(text)
            if residual_before:
                logger.warning(
                    "sarvam.translate.chunk.residual_indic index=%s chars=%s",
                    index,
                    residual_before,
                )
                revised = _english_chat_completion(
                    text,
                    index=index,
                    total=total,
                    source_language=translation_source,
                ).strip()
                if revised and _indic_character_count(revised) < residual_before:
                    text = revised
            logger.info("sarvam.translate.chunk.done index=%s output_chars=%s", index, len(text))
            return text
    except Exception as exc:  # noqa: BLE001 - fall back to chat for one failed chunk
        logger.warning("sarvam.translate.chunk.error index=%s error=%s", index, exc)
    return _english_chat_completion_with_fallback(
        chunk,
        index=index,
        total=total,
        source_language=translation_source,
    )


def _indic_source_language(text: str) -> Optional[str]:
    """Infer Sarvam's source code from Unicode script without another API call."""
    script_ranges = (
        ("\u0900", "\u097f", "hi-IN"),  # Devanagari; Hindi is the safest default
        ("\u0980", "\u09ff", "bn-IN"),
        ("\u0a00", "\u0a7f", "pa-IN"),
        ("\u0a80", "\u0aff", "gu-IN"),
        ("\u0b00", "\u0b7f", "od-IN"),
        ("\u0b80", "\u0bff", "ta-IN"),
        ("\u0c00", "\u0c7f", "te-IN"),
        ("\u0c80", "\u0cff", "kn-IN"),
        ("\u0d00", "\u0d7f", "ml-IN"),
    )
    counts = {
        language: sum(start <= char <= end for char in text)
        for start, end, language in script_ranges
    }
    language, count = max(counts.items(), key=lambda item: item[1])
    return language if count else None


def _indic_character_count(text: str) -> int:
    return sum("\u0900" <= char <= "\u0d7f" for char in text)


def english_source_chunks(
    *,
    raw_text: str,
    pages: Optional[List[Dict[str, Any]]] = None,
) -> list[str]:
    if pages:
        page_chunks = []
        for page in sorted(pages, key=lambda p: p.get("page_num") or 0):
            page_text = blocks_to_markdown([page])
            if page_text.strip():
                page_no = page.get("page_num") or page.get("page_number") or page.get("page") or len(page_chunks) + 1
                page_chunks.append(f"[Page {page_no}]\n{page_text}")
        return _pack_chunks(page_chunks, max_chars=TRANSLATION_CHUNK_SIZE)

    text = strip_data_uris(raw_text)
    return _chunk_text(text, max_chars=TRANSLATION_CHUNK_SIZE)


def _pack_chunks(parts: list[str], max_chars: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for part in parts:
        if len(part) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            chunks.extend(_chunk_text(part, max_chars=max_chars))
            continue
        candidate = f"{current}\n\n{part}".strip() if current else part
        if len(candidate) > max_chars:
            chunks.append(current.strip())
            current = part
        else:
            current = candidate
    if current.strip():
        chunks.append(current.strip())
    return chunks


def _english_chat_completion(chunk: str, *, index: int, total: int, source_language: str) -> str:
    messages = _english_messages(chunk=chunk, index=index, total=total, source_language=source_language)
    return chat(
        messages=messages,
        model=CHAT_TRANSLATION_MODEL,
        temperature=0.0,
        max_tokens=CHAT_TRANSLATION_MAX_TOKENS,
    )


def _english_chat_completion_stream(chunk: str, *, index: int, total: int, source_language: str) -> Iterator[str]:
    logger.info("sarvam.chat.stream.start model=%s chunk_index=%s", CHAT_TRANSLATION_MODEL, index)
    try:
        yield from _chat_completion_stream_http(
            messages=_english_messages(chunk=chunk, index=index, total=total, source_language=source_language),
            model=CHAT_TRANSLATION_MODEL,
            temperature=0.0,
            max_tokens=CHAT_TRANSLATION_MAX_TOKENS,
            chunk_index=index,
        )
    except Exception as exc:  # noqa: BLE001 - normalize SDK exceptions at our boundary
        raise SarvamError(str(exc)) from exc
    finally:
        logger.info("sarvam.chat.stream.done model=%s chunk_index=%s", CHAT_TRANSLATION_MODEL, index)


def _chat_completion_stream_http(
    *,
    messages: List[Dict[str, str]],
    model: str,
    temperature: float,
    max_tokens: int,
    chunk_index: int,
) -> Iterator[str]:
    """Stream chat completions directly so we control SSE parsing.

    The Sarvam SDK parser currently only accepts `data: ` lines. This parser is
    deliberately more forgiving and also handles JSONL-style lines.
    """
    if not settings.sarvam_api_key:
        raise SarvamError("SARVAM_API_KEY is not set in the backend environment")

    payload = {
        "messages": messages,
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }
    headers = {
        "api-subscription-key": settings.sarvam_api_key,
        "content-type": "application/json",
        "accept": "text/event-stream",
    }
    first_line = True
    saw_reasoning = False
    saw_content = False
    stream_started = time.perf_counter()
    with httpx.stream(
        "POST",
        "https://api.sarvam.ai/v1/chat/completions",
        json=payload,
        headers=headers,
        timeout=None,
    ) as response:
        if not (200 <= response.status_code < 300):
            body = response.read().decode("utf-8", errors="replace")
            raise SarvamError(f"Chat stream failed with {response.status_code}: {body}")

        for line in response.iter_lines():
            if not line:
                continue
            if first_line:
                logger.info(
                    "sarvam.chat.stream.first_sse_line chunk_index=%s prefix=%s",
                    chunk_index,
                    line[:40],
                )
                first_line = False
            data = _sse_data_from_line(line)
            if not data:
                continue
            if data.strip() == "[DONE]":
                return
            try:
                chunk_event = json.loads(data)
            except json.JSONDecodeError:
                logger.debug("sarvam.chat.stream.non_json_line chunk_index=%s line=%s", chunk_index, line[:80])
                continue
            content = _stream_delta_content(chunk_event)
            if content:
                if not saw_content:
                    logger.info(
                        "sarvam.chat.stream.first_content chunk_index=%s elapsed_ms=%.1f",
                        chunk_index,
                        (time.perf_counter() - stream_started) * 1000,
                    )
                    saw_content = True
                yield content
            reasoning = _stream_reasoning_delta_content(chunk_event)
            if reasoning and not saw_reasoning:
                logger.info(
                    "sarvam.chat.stream.first_reasoning chunk_index=%s elapsed_ms=%.1f",
                    chunk_index,
                    (time.perf_counter() - stream_started) * 1000,
                )
                saw_reasoning = True


def _sse_data_from_line(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith("data:"):
        return stripped[len("data:") :].lstrip()
    if stripped.startswith("{"):
        return stripped
    return ""


def _stream_delta_content(chunk_event: Any) -> str:
    choices = (
        chunk_event.get("choices")
        if isinstance(chunk_event, dict)
        else getattr(chunk_event, "choices", None)
    )
    if not choices:
        return ""
    choice = choices[0]
    delta = choice.get("delta") if isinstance(choice, dict) else getattr(choice, "delta", None)
    content = delta.get("content") if isinstance(delta, dict) else getattr(delta, "content", None)
    if not content:
        message = choice.get("message") if isinstance(choice, dict) else getattr(choice, "message", None)
        content = message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
    return str(content) if content else ""


def _stream_reasoning_delta_content(chunk_event: Any) -> str:
    choices = (
        chunk_event.get("choices")
        if isinstance(chunk_event, dict)
        else getattr(chunk_event, "choices", None)
    )
    if not choices:
        return ""
    choice = choices[0]
    delta = choice.get("delta") if isinstance(choice, dict) else getattr(choice, "delta", None)
    content = (
        delta.get("reasoning_content")
        if isinstance(delta, dict)
        else getattr(delta, "reasoning_content", None)
    )
    return str(content) if content else ""


def _english_messages(chunk: str, *, index: int, total: int, source_language: str) -> List[Dict[str, str]]:
    system = (
        "You are a precise Indian court-document translator and OCR cleanup editor. "
        "Return the entire input in English Markdown. Translate every word written in an "
        "Indic script, including headings, table cells, labels, witness descriptions, and "
        "legal phrases. Transliterate proper names into Latin script; never leave Devanagari "
        "or another Indic script in the output. Preserve page labels, paragraph numbering, "
        "dates, FIR/CNR/case numbers, statutory section numbers, and the exact content order. "
        "Preserve valid Markdown or HTML table structure and keep every row and column aligned. "
        "Remove only obvious adjacent OCR duplicates. Do not summarize, omit, interpret, add "
        "facts, citations, or commentary. Return only cleaned English Markdown without a "
        "preface or code fence."
    )
    user = (
        f"Source language hint: {source_language}\n"
        f"Chunk {index} of {total}. Return only the English Markdown for this chunk.\n\n"
        f"{chunk}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _english_chat_completion_with_fallback(chunk: str, *, index: int, total: int, source_language: str) -> str:
    output = _english_chat_completion(chunk, index=index, total=total, source_language=source_language)
    if output.strip():
        return output

    logger.warning(
        "sarvam.english_chat.empty_chunk index=%s chars=%s retrying_with_smaller_chunks",
        index,
        len(chunk),
    )
    smaller_chunks = _chunk_text(chunk, max_chars=1200)
    retry_outputs: list[str] = []
    for retry_index, retry_chunk in enumerate(smaller_chunks, start=1):
        retry_output = _english_chat_completion(
            retry_chunk,
            index=retry_index,
            total=len(smaller_chunks),
            source_language=source_language,
        )
        if retry_output.strip():
            retry_outputs.append(retry_output)
        else:
            logger.warning(
                "sarvam.english_chat.empty_retry original_index=%s retry_index=%s using_source_text",
                index,
                retry_index,
            )
            retry_outputs.append(retry_chunk)
    return "\n\n".join(part.strip() for part in retry_outputs if part.strip())


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


def generate_legal_search_items(
    *,
    section_title: str,
    section_content: str,
    filing_type: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Turn one analysis section into focused legal-research searches.

    Sarvam supplies the research framing; the backend validates its JSON and
    returns validated structured queries for the source-search pipeline.
    """
    system = (
        "You are an Indian legal research strategist. Given one analysis section "
        "from a filing, generate 3 to 5 precise research searches grounded in the "
        "section's actual facts and legal issues. Cover useful combinations of "
        "precedent, statutory interpretation, procedure, ingredients, defences, "
        "or evidentiary questions only when supported by the content. Do not merely "
        "search for the IPC section number. Return only a JSON array. Each object "
        "must contain: title (short label), query (a search-engine-ready Indian "
        "legal query), rationale (one sentence), and kind (one of precedent, "
        "statute, procedure, evidence, defence)."
    )
    user = (
        f"Filing type: {filing_type or 'unknown'}\n"
        f"Analysis section: {section_title}\n\n"
        f"Section content:\n{section_content[:8000]}"
    )
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    failures: List[str] = []
    for attempt, model in enumerate(dict.fromkeys((RESEARCH_SEARCH_MODEL, CHAT_MODEL)), start=1):
        try:
            raw = chat(
                messages=messages,
                model=model,
                temperature=0.1 if attempt > 1 else 0.15,
                max_tokens=1800,
            )
            payload = _json_from_chat(raw)
            if isinstance(payload, dict):
                payload = (
                    payload.get("items")
                    or payload.get("search_items")
                    or payload.get("queries")
                )
            items = _normalise_search_items(payload)
            if items:
                return items
            failures.append(f"{model}: no valid items")
        except SarvamError as exc:
            failures.append(f"{model}: {exc}")

    logger.warning(
        "sarvam.legal_search.fallback section=%r failures=%s",
        section_title,
        "; ".join(failures),
    )
    return _fallback_legal_search_items(section_title, section_content)


def _normalise_search_items(payload: Any) -> List[Dict[str, str]]:
    if not isinstance(payload, list):
        return []
    allowed_kinds = {"precedent", "statute", "procedure", "evidence", "defence"}
    items: List[Dict[str, str]] = []
    for value in payload[:5]:
        if not isinstance(value, dict):
            continue
        title = str(value.get("title") or "").strip()
        query = str(value.get("query") or "").strip()
        rationale = str(value.get("rationale") or "").strip()
        kind = str(value.get("kind") or "precedent").strip().lower()
        if not title or not query or not rationale:
            continue
        if kind not in allowed_kinds:
            kind = "precedent"
        items.append(
            {
                "title": title[:120],
                "query": query[:500],
                "rationale": rationale[:500],
                "kind": kind,
            }
        )
    return items


def _json_from_chat(text: str) -> Any:
    if not text or not text.strip():
        raise SarvamError("Sarvam returned an empty response for legal search items")
    cleaned = text.lstrip("\ufeff").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL | re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        start = min((index for index in (cleaned.find("["), cleaned.find("{")) if index >= 0), default=-1)
        if start >= 0:
            decoder = json.JSONDecoder()
            try:
                value, _ = decoder.raw_decode(cleaned[start:])
                return value
            except json.JSONDecodeError:
                pass
        raise SarvamError("Sarvam returned invalid JSON for legal search items") from exc


def _fallback_legal_search_items(section_title: str, section_content: str) -> List[Dict[str, str]]:
    """Keep source search usable when Sarvam returns an empty/malformed completion."""
    source = re.sub(r"[#*_`>\[\](){}|]", " ", f"{section_title} {section_content}")
    words = re.findall(r"[A-Za-z][A-Za-z'-]{2,}", source.lower())
    stopwords = {
        "about", "after", "also", "analysis", "been", "being", "could", "from",
        "have", "into", "legal", "more", "section", "that", "their", "there",
        "these", "this", "those", "under", "upon", "were", "which", "with",
        "would", "ipc", "indian",
    }
    keywords: List[str] = []
    for word in words:
        if word not in stopwords and word not in keywords:
            keywords.append(word)
        if len(keywords) == 10:
            break
    topic = " ".join(keywords) or section_title.strip() or "criminal allegation"
    return [
        {
            "title": "Governing precedents",
            "query": f"{topic} Supreme Court India governing test precedent",
            "rationale": "Finds Indian decisions applying the legal issues and facts identified in this analysis.",
            "kind": "precedent",
        },
        {
            "title": "Ingredients and proof",
            "query": f"{topic} essential ingredients burden of proof evidence Indian criminal law",
            "rationale": "Researches the required ingredients and evidentiary burden for the identified conduct.",
            "kind": "evidence",
        },
        {
            "title": "Procedure and defences",
            "query": f"{topic} criminal procedure available defences India",
            "rationale": "Finds procedural requirements and defences relevant to the analysis.",
            "kind": "procedure",
        },
    ]


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
