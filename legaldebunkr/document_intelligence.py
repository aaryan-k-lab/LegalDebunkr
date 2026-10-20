"""Step 1: Azure AI Document Intelligence.

Runs the prebuilt-layout model to OCR the upload and recover structure
(headings, paragraphs, tables), then groups paragraphs into sections that
can be explained one at a time.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import (
    AnalyzeDocumentRequest,
    DocumentContentFormat,
)
from azure.core.credentials import AzureKeyCredential

from .config import settings

SKIP_ROLES = {"pageHeader", "pageFooter", "pageNumber", "footnote"}
HEADING_ROLES = {"title", "sectionHeading"}
MAX_SECTION_CHARS = 3500
MIN_SECTION_CHARS = 350


@dataclass
class Section:
    heading: str
    text: str
    page: int | None = None

    def to_dict(self) -> dict:
        return {"heading": self.heading, "text": self.text, "page": self.page}


@dataclass
class ExtractedDocument:
    markdown: str
    page_count: int
    sections: list[Section] = field(default_factory=list)


def _client() -> DocumentIntelligenceClient:
    return DocumentIntelligenceClient(
        endpoint=settings.di_endpoint,
        credential=AzureKeyCredential(settings.di_key),
    )


def extract(data: bytes) -> ExtractedDocument:
    """OCR + layout analysis for PDF, DOCX, or image bytes."""
    poller = _client().begin_analyze_document(
        "prebuilt-layout",
        body=AnalyzeDocumentRequest(bytes_source=data),
        output_content_format=DocumentContentFormat.MARKDOWN,
    )
    result = poller.result()

    paragraphs = []
    for p in result.paragraphs or []:
        page = None
        if p.bounding_regions:
            page = p.bounding_regions[0].page_number
        paragraphs.append({"role": p.role, "content": p.content, "page": page})

    return ExtractedDocument(
        markdown=result.content or "",
        page_count=len(result.pages or []),
        sections=build_sections(paragraphs),
    )


def build_sections(paragraphs: list[dict]) -> list[Section]:
    """Group paragraphs under headings, then split/merge to a workable size.

    `paragraphs` is a list of {"role", "content", "page"} dicts so this logic
    can be tested without calling Azure.
    """
    raw: list[Section] = []
    current = Section(heading="Preamble", text="")

    for p in paragraphs:
        role, content = p.get("role"), (p.get("content") or "").strip()
        if not content or role in SKIP_ROLES:
            continue
        if role in HEADING_ROLES:
            if current.text.strip():
                raw.append(current)
            current = Section(heading=content, text="", page=p.get("page"))
        else:
            if current.page is None:
                current.page = p.get("page")
            current.text += content + "\n\n"
    if current.text.strip():
        raw.append(current)

    return _merge_small(_split_large(raw))


def _split_large(sections: list[Section]) -> list[Section]:
    out: list[Section] = []
    for s in sections:
        if len(s.text) <= MAX_SECTION_CHARS:
            out.append(s)
        else:
            out.extend(_chunk_by_size(s))
    return out


def _chunk_by_size(section: Section) -> list[Section]:
    chunks, buf = [], ""
    for para in section.text.split("\n\n"):
        if buf and len(buf) + len(para) > MAX_SECTION_CHARS:
            chunks.append(buf)
            buf = ""
        buf += para + "\n\n"
    if buf.strip():
        chunks.append(buf)
    if len(chunks) == 1:
        return [Section(section.heading, chunks[0].strip(), section.page)]
    return [
        Section(f"{section.heading} (part {i})", c.strip(), section.page)
        for i, c in enumerate(chunks, 1)
    ]


def _merge_small(sections: list[Section]) -> list[Section]:
    merged: list[Section] = []
    for s in sections:
        s.text = s.text.strip()
        if merged and len(merged[-1].text) < MIN_SECTION_CHARS:
            prev = merged[-1]
            prev.heading = f"{prev.heading} / {s.heading}"
            prev.text = f"{prev.text}\n\n{s.heading}\n{s.text}".strip()
        else:
            merged.append(s)
    return merged
