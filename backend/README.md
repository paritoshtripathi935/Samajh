# Samajh backend

FastAPI service that wraps **Sarvam** for the golden path: **digitise** a filing →
**extract** typed fields → **ask** cited questions grounded in the digitised text.

## Run it

```bash
cd backend
cp .env.example .env            # then set SARVAM_API_KEY
./venv/bin/uvicorn main:app --reload --port 8000
# docs: http://localhost:8000/docs
```

Get a key from **dashboard.sarvam.ai**. The venv already has deps; otherwise
`pip install -r requirements.txt`.

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
| `POST` | `/api/cases` | create a case |
| `POST` | `/api/cases/{id}/documents` | upload PDF → digitise → store text |
| `POST` | `/api/cases/{id}/documents/{doc}/extract` | typed fields + confidence |
| `POST` | `/api/cases/{id}/ask` | cited answer grounded in the case's docs |

State is in-memory (`app/services/store.py`) for now — **swap for Supabase in M1**.
