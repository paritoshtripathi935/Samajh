"""Contextual Indian legal search, adapted from MiniHarvey.

Sarvam generates focused queries from an analysis section. This module executes
each query against Indian Kanoon and Google CSE in parallel, then returns a
small, source-balanced result set for the workbench.
"""
from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

import requests

from app.core.settings import settings

logger = logging.getLogger(__name__)
_IK_SEARCH_URL = "https://api.indiankanoon.org/search/"
_IK_BROWSE_URL = "https://indiankanoon.org/doc/{tid}/"
_GOOGLE_CSE_URL = "https://www.googleapis.com/customsearch/v1"


def search_generated_items(items: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Attach live legal-source results to every Sarvam-generated search item."""
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=min(4, len(items))) as executor:
        futures = {executor.submit(_search_one, item["query"]): index for index, item in enumerate(items)}
        results_by_index: Dict[int, List[Dict[str, Any]]] = {}
        for future in as_completed(futures):
            index = futures[future]
            try:
                results_by_index[index] = future.result()
            except Exception as exc:  # noqa: BLE001
                logger.warning("legal_search.item_failed index=%s error=%s", index, exc)
                results_by_index[index] = []
    return [{**item, "results": results_by_index.get(index, [])} for index, item in enumerate(items)]


def _search_one(query: str) -> List[Dict[str, Any]]:
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(_search_indian_kanoon, query),
            executor.submit(_search_google, query),
        ]
        source_results = [future.result() for future in futures]

    balanced: List[Dict[str, Any]] = []
    for index in range(max((len(values) for values in source_results), default=0)):
        for values in source_results:
            if index < len(values):
                balanced.append(values[index])

    seen: set[str] = set()
    deduped: List[Dict[str, Any]] = []
    per_item_limit = max(1, min(settings.max_search_results, 6))
    for result in balanced:
        if result["url"] in seen:
            continue
        seen.add(result["url"])
        deduped.append(result)
        if len(deduped) >= per_item_limit:
            break
    return deduped


def _search_indian_kanoon(query: str) -> List[Dict[str, Any]]:
    if not settings.indian_kanoon_api_token:
        return []
    try:
        response = requests.post(
            _IK_SEARCH_URL,
            data={"formInput": query, "pagenum": 0},
            headers={
                "Authorization": f"Token {settings.indian_kanoon_api_token}",
                "Accept": "application/json",
            },
            timeout=8,
        )
        response.raise_for_status()
        docs = response.json().get("docs", [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Indian Kanoon search failed: %s", exc)
        return []

    results = []
    for doc in docs[: settings.max_search_results]:
        tid = str(doc.get("tid") or "").strip()
        if not tid:
            continue
        results.append(
            {
                "title": str(doc.get("title") or "Untitled"),
                "url": _IK_BROWSE_URL.format(tid=tid),
                "snippet": re.sub(r"<[^>]+>", "", str(doc.get("headline") or "")).strip(),
                "source": "indian_kanoon",
                "doc_type": "judgment" if doc.get("doctype") == "judgment" else "act",
                "jurisdiction": str(doc.get("court") or doc.get("docsource") or "") or None,
                "citation": str(doc.get("citation") or "") or None,
            }
        )
    return results


def _search_google(query: str) -> List[Dict[str, Any]]:
    if not settings.google_api_key or not settings.google_search_cx:
        return []
    try:
        response = requests.get(
            _GOOGLE_CSE_URL,
            params={
                "key": settings.google_api_key,
                "cx": settings.google_search_cx,
                "q": f"{query} India law",
                "num": min(settings.max_search_results, 10),
            },
            timeout=8,
        )
        response.raise_for_status()
        items = response.json().get("items", [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Google legal search failed: %s", exc)
        return []

    results = []
    for item in items[: settings.max_search_results]:
        url = str(item.get("link") or "").strip()
        if not url:
            continue
        domain = str(item.get("displayLink") or "")
        doc_type = "judgment" if "indiankanoon" in domain else "act" if "indiacode" in domain else "article"
        results.append(
            {
                "title": str(item.get("title") or "Untitled"),
                "url": url,
                "snippet": str(item.get("snippet") or ""),
                "source": "google",
                "doc_type": doc_type,
                "jurisdiction": None,
                "citation": None,
            }
        )
    return results
