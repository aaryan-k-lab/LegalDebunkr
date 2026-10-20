"""Orchestrates the three Azure services into one analysis."""
from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

from . import content_understanding, document_intelligence, language_generation
from .config import settings

log = logging.getLogger(__name__)

# In-memory store so follow-up questions can reuse an analysis. Entries expire
# (STORE_TTL_SECONDS) and the store is size-capped (STORE_MAX_ITEMS) so uploaded
# legal text does not pile up in memory. Use Redis for multi-instance deploys.
_STORE: "OrderedDict[str, tuple[float, dict]]" = OrderedDict()
_LOCK = threading.Lock()


def _put(doc_id: str, analysis: dict) -> None:
    now = time.time()
    with _LOCK:
        for k in [k for k, (t, _) in _STORE.items() if now - t > settings.store_ttl_seconds]:
            del _STORE[k]
        _STORE[doc_id] = (now, analysis)
        while len(_STORE) > settings.store_max_items:
            _STORE.popitem(last=False)

CONTENT_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "tiff": "image/tiff",
    "bmp": "image/bmp",
}


def analyze_document(data: bytes, filename: str) -> dict:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    warnings: list[str] = []

    # 1) Document Intelligence: OCR + layout -> sections
    extracted = document_intelligence.extract(data)
    if not extracted.sections:
        raise ValueError("No readable text found in this file.")
    sections = extracted.sections[: settings.max_sections]
    if len(extracted.sections) > settings.max_sections:
        warnings.append(
            f"Long document: explained the first {settings.max_sections} of "
            f"{len(extracted.sections)} sections."
        )

    # 2) Content Understanding: structured key terms (best-effort)
    fields: dict = {}
    if settings.cu_ready:
        try:
            fields = content_understanding.analyze(
                data, CONTENT_TYPES.get(ext, "application/octet-stream")
            )
        except Exception:  # keep going; the overview can still be generated
            log.exception("Content Understanding failed")
            warnings.append("Key-term extraction was skipped because that service had a problem.")
    else:
        warnings.append("Content Understanding is not configured; key-term extraction was skipped.")

    # 3) Language generation: overview + per-section plain English
    excerpt = extracted.markdown[:10000]
    overview = language_generation.explain_overview(
        fields, [s.heading for s in sections], excerpt
    )

    def explain(section):
        try:
            result = language_generation.explain_section(section.heading, section.text)
        except Exception:
            log.exception("Section explanation failed")
            result = {
                "plain_english": "Could not explain this section. Try uploading again.",
                "jargon": [],
                "watch_out": None,
                "severity": "none",
            }
        return {**section.to_dict(), **result}

    with ThreadPoolExecutor(max_workers=4) as pool:
        explained = list(pool.map(explain, sections))

    doc_id = uuid.uuid4().hex
    analysis = {
        "id": doc_id,
        "filename": filename,
        "page_count": extracted.page_count,
        "fields": fields,
        "overview": overview,
        "sections": explained,
        "warnings": warnings,
        "disclaimer": language_generation.DISCLAIMER,
    }
    _put(doc_id, analysis)
    return analysis


def get_analysis(doc_id: str) -> dict | None:
    with _LOCK:
        item = _STORE.get(doc_id)
    if not item or time.time() - item[0] > settings.store_ttl_seconds:
        return None
    return item[1]
