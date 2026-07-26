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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sarvamai import SarvamAI

from app.core.settings import settings

CHAT_MODEL = "sarvam-30b"          # sarvam-105b for the heavier model
TRANSLATE_MODEL = "sarvam-translate:v1"


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
    client = _client()
    job = client.document_intelligence.create_job(language=language, output_format=output_format)
    job.upload_file(file_path)
    job.start()
    status = job.wait_until_complete(poll_interval=poll_interval, timeout=timeout)

    state = str(getattr(status, "job_state", "")).lower()
    if state not in ("completed", "partiallycompleted"):
        raise SarvamError(f"DI job {job.job_id} ended in state '{state}'")

    out_dir = tempfile.mkdtemp(prefix="samajh_di_")
    written = job.download_output(out_dir)
    raw_text, files = _read_output(written, out_dir)

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


def _read_output(written: str, fallback_dir: str) -> Tuple[str, List[str]]:
    """download_output may return a file path or a directory. Read either."""
    p = Path(written) if written else Path(fallback_dir)
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
