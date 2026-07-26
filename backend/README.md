# Samajh backend

FastAPI service. **MVP:** one call digitises a filing (Sarvam Vision), returns
clean raw extraction plus coordinate annotations, and summarises IPC sections.
A second call generates English Markdown with Sarvam chat completions and then
persists that translation to Supabase. The frontend uses the streaming variant
so the English pane fills chunk-by-chunk instead of waiting for the full filing.

## Run it

```bash
cd backend
# .env already has SARVAM_API_KEY + Supabase (project "Samajh")
./.venv/bin/uvicorn main:app --reload --port 8000   # docs: http://localhost:8000/docs
```

Frontend: `cd frontend && npm run dev` → http://localhost:3000 (upload a PDF).

## API

| Method | Path | Does |
|---|---|---|
| `GET`  | `/health` | liveness |
| `POST` | `/api/documents/process` | upload PDF → digitise → coordinate pages → IPC summaries → persist. Returns `{raw_extraction, pages, ipc_sections[], document_id, filing_type}` |
| `POST` | `/api/documents/english` | generate English Markdown from `{raw_extraction, pages, document_id}` using Sarvam chat completions |
| `POST` | `/api/documents/english/stream` | same English generation as NDJSON events: `start`, repeated `chunk`, then `done` with stitched `eng_extraction` |
| `GET`  | `/api/documents/{id}` | persisted document + digitizations/extractions/translations |
| `POST` | `/api/cases…`, `/ask` | workbench teammate's surface (in-memory store) — left intact |

## How it works

- **Digitise** — the only Sarvam document REST API (async job, `sarvamai` SDK). PDFs
  over the **10-page/job** limit are auto-split with `pypdf` and stitched (`app/services/sarvam.py`).
- **English generation** — uses `sarvam-105b` chat completions, not the Translate API.
  Page/block JSON is used for page-level chunking where available; long fallback text is
  chunked by character budget. Streaming is chunk-level, not token-level, so tables and
  page order use the same chunk packing as the non-streaming endpoint.
- **IPC** — `citations.extract_ipc_references()` finds section refs; each is summarised by
  `sarvam-105b`. (Sarvam's schema "Extract" has no REST API — it's dashboard-only — so
  `app/services/extraction.py` does typed extraction via the chat model.)

## Supabase

Project **Samajh** (`smngfmejqgyjkhpozcwr`, ap-south-1). Tables `documents` ·
`digitizations` · `extractions` · `translations` (`app/repositories.py`). Persistence in
`/documents/process` is **best-effort** — a DB hiccup never fails the request. RLS is on
with **open demo policies**; tighten + use the service-role key before production.

## CLI

```bash
./.venv/bin/python scripts/digitise.py path/to/filing.pdf --format json --extract chargesheet
```
