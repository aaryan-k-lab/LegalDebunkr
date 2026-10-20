import sys
from pathlib import Path


from legaldebunkr.content_understanding import parse_fields, unwrap
from legaldebunkr.document_intelligence import MAX_SECTION_CHARS, build_sections
from legaldebunkr.retrieval import top_sections


def test_sections_group_under_headings_and_skip_chrome():
    paras = [
        {"role": "title", "content": "Residential Lease", "page": 1},
        {"role": "pageHeader", "content": "CONFIDENTIAL", "page": 1},
        {"role": None, "content": "A" * 400, "page": 1},
        {"role": "sectionHeading", "content": "1. Rent", "page": 1},
        {"role": None, "content": "Rent is due on the first. " * 20, "page": 1},
        {"role": "pageNumber", "content": "1", "page": 1},
    ]
    sections = build_sections(paras)
    assert [s.heading for s in sections] == ["Residential Lease", "1. Rent"]
    assert all("CONFIDENTIAL" not in s.text for s in sections)


def test_large_section_is_split():
    paras = [{"role": None, "content": ("word " * 200).strip(), "page": 1} for _ in range(10)]
    sections = build_sections(paras)
    assert len(sections) > 1
    assert all(len(s.text) <= MAX_SECTION_CHARS + 1100 for s in sections)


def test_unwrap_typed_fields():
    assert unwrap({"type": "string", "valueString": "Lease"}) == "Lease"
    nested = {
        "type": "array",
        "valueArray": [
            {"type": "object", "valueObject": {"Name": {"valueString": "Acme"}, "Role": {"valueString": "Landlord"}}}
        ],
    }
    assert unwrap(nested) == [{"Name": "Acme", "Role": "Landlord"}]


def test_parse_fields_handles_empty():
    assert parse_fields({}) == {}
    resp = {"result": {"contents": [{"fields": {"GoverningLaw": {"valueString": "Virginia"}}}]}}
    assert parse_fields(resp) == {"GoverningLaw": "Virginia"}


def test_retrieval_prefers_relevant_section():
    sections = [
        {"heading": "Rent", "text": "Rent is due monthly. Late fees apply after five days."},
        {"heading": "Termination", "text": "Either party may terminate with sixty days written notice."},
        {"heading": "Governing law", "text": "This lease is governed by the laws of Virginia."},
    ]
    assert top_sections("Can I terminate early?", sections, k=1)[0]["heading"] == "Termination"
