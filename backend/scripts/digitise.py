#!/usr/bin/env python
"""Getting-started: run Sarvam Document Digitization end-to-end on one file.

    cd backend
    ./venv/bin/python scripts/digitise.py path/to/filing.pdf
    ./venv/bin/python scripts/digitise.py filing.pdf --format json --lang hi-IN
    ./venv/bin/python scripts/digitise.py filing.pdf --format json --extract chargesheet

Needs SARVAM_API_KEY in backend/.env (or the environment). Prints a summary,
saves the digitised output next to the input, and -- with --format json --
reports whether the output carries page numbers / bounding boxes / confidence
(the fact that decides span-level jump-to-source vs snippet-level).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make `app` importable when run from backend/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import extraction, sarvam  # noqa: E402


def _scan_for_layout(obj, found=None):
    """Walk a JSON structure and report which layout keys appear."""
    found = found if found is not None else set()
    keys_of_interest = {
        "page", "page_number", "page_no", "bbox", "bounding_box", "boundingBox",
        "polygon", "coordinates", "x", "y", "width", "height", "confidence", "score",
    }
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys_of_interest:
                found.add(k)
            _scan_for_layout(v, found)
    elif isinstance(obj, list):
        for item in obj[:50]:
            _scan_for_layout(item, found)
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description="Digitise a filing with Sarvam DI.")
    ap.add_argument("file", help="PDF (or ZIP of JPEG/PNG), <=200MB, <=10 pages")
    ap.add_argument("--format", default="md", choices=["md", "html", "json"])
    ap.add_argument("--lang", default="en-IN", help="BCP-47, e.g. en-IN, hi-IN")
    ap.add_argument("--extract", default=None,
                    help="After digitising, extract typed fields: chargesheet | judgment")
    args = ap.parse_args()

    src = Path(args.file)
    if not src.exists():
        print(f"! file not found: {src}", file=sys.stderr)
        return 2

    print(f"→ digitising {src.name}  (format={args.format}, lang={args.lang}) …")
    try:
        result = sarvam.digitise(str(src), language=args.lang, output_format=args.format)
    except sarvam.SarvamError as e:
        print(f"! {e}", file=sys.stderr)
        return 1

    print(f"✓ job {result.job_id} completed")
    if result.page_metrics:
        print(f"  page metrics: {json.dumps(result.page_metrics)[:300]}")

    ext = {"md": ".md", "html": ".html", "json": ".json"}[args.format]
    out_path = src.with_suffix(f".digitised{ext}")
    out_path.write_text(result.raw_text, encoding="utf-8")
    print(f"  saved → {out_path}  ({len(result.raw_text):,} chars)")
    print("\n--- first 800 chars ---\n" + result.raw_text[:800])

    if args.format == "json" and isinstance(result.content, (dict, list)):
        layout = _scan_for_layout(result.content)
        print("\n=== layout keys present in JSON output ===")
        print(" ", sorted(layout) or "(none found)")
        has_page = bool(layout & {"page", "page_number", "page_no"})
        has_bbox = bool(layout & {"bbox", "bounding_box", "boundingBox", "polygon", "coordinates"})
        print(f"  page location : {'YES' if has_page else 'no'}")
        print(f"  bounding boxes: {'YES → span-level jump-to-source is possible' if has_bbox else 'no → fall back to snippet-level'}")

    if args.extract:
        print(f"\n→ extracting {args.extract} fields via sarvam-30b …")
        fields = extraction.extract_fields(result.raw_text, filing_type=args.extract)
        print(json.dumps(fields, ensure_ascii=False, indent=2)[:2000])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
