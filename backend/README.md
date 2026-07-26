# Samajh backend

FastAPI service that wraps **Sarvam** for the golden path: **digitise** a filing →
**extract** typed fields → **ask** cited questions grounded in the digitised text.

## Run it

```bash
cd backend
cp .env.example .env            # then set SARVAM_API_KEY
.venv/bin/uvicorn main:app --reload --port 8000
# docs: http://localhost:8000/docs
```

Get a key from **dashboard.sarvam.ai**. The venv already has deps; otherwise
`uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt`.

## Try digitise from the CLI (no frontend needed)

```bash
./venv/bin/python scripts/digitise.py path/to/filing.pdf --format md
./venv/bin/python scripts/digitise.py filing.pdf --format json           # inspects for page/bbox
./venv/bin/python scripts/digitise.py filing.pdf --format json --extract chargesheet
```

`--format json` prints which layout keys the output carries (`page`, `bbox`, …) —
that's what decides **span-level jump-to-source** vs snippet-level fallback.

## What Sarvam actually gives us

| Capability | How | Endpoint(s) |
|---|---|---|
| **Digitise** (PDF/scan/handwriting → md/html/json, layout-preserving) | `sarvam.digitise()` → SDK job | `POST /doc-digitization/job/v1` → `upload-files` → `{id}/start` → `{id}/status` → `{id}/download-files` |
| **Extract** (typed fields + per-field confidence) | `extraction.extract_fields()` — **digitise then prompt `sarvam-30b`** | *(no public Extract REST API — dashboard-only, so we do it via chat)* |
| **Ask** (grounded answer) | `sarvam.chat()` | `POST /v1/chat/completions` (`sarvam-30b` / `sarvam-105b`) |
| **Translate** (regional → plain) | `sarvam.translate()` | `POST /translate` (`sarvam-translate:v1`) |

- Base `https://api.sarvam.ai` · header `api-subscription-key` · auth fail = **403**.
- `output_format`: `md` \| `html` \| `json` (never `markdown` → 400).
- **Limits:** ≤ 200 MB, **≤ 10 pages per job** → a 150-page filing must be split
  into ≤10-page chunks and stitched.
- Job states: `Accepted` · `Pending` · `Running` · `Completed` · `PartiallyCompleted` · `Failed`.

## HTTP API (this service)

| Method | Path | Does |
|---|---|---|
| `GET` | `/health` | liveness |
| `POST` | `/api/documents/process` | upload PDF → raw Markdown, English Markdown, IPC summaries |
| `POST` | `/api/cases` | create a case |
| `POST` | `/api/cases/{id}/documents` | upload PDF → digitise → store text |
| `POST` | `/api/cases/{id}/documents/{doc}/extract` | typed fields + confidence |
| `POST` | `/api/cases/{id}/ask` | cited answer grounded in the case's docs |

### Single Document Processing API

This is the main API for the current feature slice. It takes one legal PDF,
digitises it with Sarvam Document Intelligence, translates the extracted
Markdown to English when needed, finds IPC references in the Markdown, and uses
Sarvam chat to summarize each unique IPC section.

`POST /api/documents/process` accepts multipart form data:

- `file`: PDF upload
- `language`: Sarvam BCP-47 language hint, defaults to `en-IN`
- `output_format`: `md`, currently the only supported value for this endpoint

Current behavior:

- PDFs over Sarvam's 10-page limit are split into <=10-page batches and stitched
  back into one Markdown string.
- `raw_extraction` is the stitched Markdown from Document Intelligence.
- `eng_extraction` is translated to `en-IN` with `sarvam-translate:v1`; if
  `language=en-IN`, it is returned unchanged.
- `ipc_sections` is built by regex-detecting IPC references like `u/s 420 IPC`,
  `Section 302 IPC`, and `IPC Section 376`, deduplicating section numbers, then
  asking `sarvam-105b` for concise summaries.
- The endpoint is synchronous right now, so larger filings can take a while.

Response:

```json
{
  "raw_extraction": "Markdown from Sarvam Document Intelligence",
  "eng_extraction": "English Markdown translated with Sarvam Translate",
  "ipc_sections": [
    {
      "ipc": "420",
      "summary": "Concise explanation of IPC Section 420"
    }
  ]
}
```

Example:

```bash
curl -X POST "http://127.0.0.1:8000/api/documents/process" \
  -F "file=@/path/to/chargesheet.pdf" \
  -F "language=en-IN" \
  -F "output_format=md"
```

State is in-memory (`app/services/store.py`) for now — **swap for Supabase in M1**.
