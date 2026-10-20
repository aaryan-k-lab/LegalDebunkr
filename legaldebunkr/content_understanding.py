"""Step 2: Azure AI Content Understanding.

Creates (once) a custom document analyzer with a legal-document field schema,
then runs the upload through it to get structured fields: parties, dates,
payment terms, termination, liability, governing law, and so on.

Content Understanding is a REST service, so this module talks to it directly.
"""
from __future__ import annotations

import time

import requests

from .config import settings

FIELD_SCHEMA = {
    "name": "LegalDocumentSchema",
    "description": "Key facts a non-lawyer needs from a legal document.",
    "fields": {
        "DocumentType": {
            "type": "string",
            "method": "generate",
            "description": "What kind of document this is, e.g. lease, NDA, employment offer, terms of service, loan agreement.",
        },
        "Parties": {
            "type": "array",
            "method": "generate",
            "description": "Every person or organization bound by the document and the role each plays.",
            "items": {
                "type": "object",
                "properties": {
                    "Name": {"type": "string", "method": "extract", "description": "Party name."},
                    "Role": {"type": "string", "method": "generate", "description": "Role such as landlord, tenant, employer, employee, licensor."},
                },
            },
        },
        "EffectiveDate": {
            "type": "string",
            "method": "generate",
            "description": "Date the agreement starts or takes effect, as written.",
        },
        "TermAndRenewal": {
            "type": "string",
            "method": "generate",
            "description": "How long the agreement lasts and whether or how it renews.",
        },
        "PaymentObligations": {
            "type": "string",
            "method": "generate",
            "description": "Amounts, due dates, late fees, deposits, and other money one side owes the other.",
        },
        "TerminationConditions": {
            "type": "string",
            "method": "generate",
            "description": "How and when either side can end the agreement, including notice periods and penalties.",
        },
        "LiabilityAndIndemnity": {
            "type": "string",
            "method": "generate",
            "description": "Limits on liability, warranties, and promises to cover the other side's losses.",
        },
        "DisputeResolution": {
            "type": "string",
            "method": "generate",
            "description": "Arbitration, court venue, class-action waivers, or similar dispute terms.",
        },
        "GoverningLaw": {
            "type": "string",
            "method": "generate",
            "description": "Jurisdiction whose law governs the agreement.",
        },
        "KeyObligations": {
            "type": "array",
            "method": "generate",
            "description": "The most important things each party must do or must not do.",
            "items": {"type": "string", "method": "generate"},
        },
    },
}


class ContentUnderstandingError(RuntimeError):
    pass


def _base() -> str:
    return settings.cu_endpoint.rstrip("/")


def _headers(content_type: str = "application/json") -> dict:
    return {"Ocp-Apim-Subscription-Key": settings.cu_key, "Content-Type": content_type}


def _params() -> dict:
    return {"api-version": settings.cu_api_version}


def _analyzer_url() -> str:
    return f"{_base()}/contentunderstanding/analyzers/{settings.cu_analyzer_id}"


def _poll(operation_url: str, timeout: int = 180) -> dict:
    deadline = time.time() + timeout
    delay = 1.0
    while time.time() < deadline:
        resp = requests.get(
            operation_url, headers={"Ocp-Apim-Subscription-Key": settings.cu_key}, timeout=30
        )
        resp.raise_for_status()
        body = resp.json()
        status = (body.get("status") or "").lower()
        if status == "succeeded":
            return body
        if status in {"failed", "canceled"}:
            raise ContentUnderstandingError(f"Operation {status}: {body.get('error')}")
        time.sleep(delay)
        delay = min(delay * 1.5, 5.0)
    raise ContentUnderstandingError("Timed out waiting for Content Understanding.")


def ensure_analyzer() -> None:
    """Create the custom analyzer if it does not exist yet."""
    resp = requests.get(_analyzer_url(), headers=_headers(), params=_params(), timeout=30)
    if resp.status_code == 200:
        return
    if resp.status_code != 404:
        resp.raise_for_status()

    body: dict = {
        "description": "LegalDebunkr: extract key terms from legal documents.",
        "scenario": "document",
        "config": {"returnDetails": True, "enableOcr": True, "enableLayout": True},
        "fieldSchema": FIELD_SCHEMA,
    }
    if settings.cu_base_analyzer_id:
        body["baseAnalyzerId"] = settings.cu_base_analyzer_id
    if settings.cu_completion_model:
        body["models"] = {"completion": settings.cu_completion_model}

    create = requests.put(
        _analyzer_url(), headers=_headers(), params=_params(), json=body, timeout=60
    )
    if create.status_code not in (200, 201, 202):
        raise ContentUnderstandingError(f"Analyzer creation failed: {create.status_code} {create.text}")
    op = create.headers.get("Operation-Location")
    if op:
        _poll(op)


def analyze(data: bytes, content_type: str = "application/octet-stream") -> dict:
    """Run the document through the analyzer and return a flat dict of fields."""
    ensure_analyzer()
    resp = requests.post(
        f"{_analyzer_url()}:analyzeBinary",
        headers=_headers(content_type),
        params=_params(),
        data=data,
        timeout=120,
    )
    if resp.status_code not in (200, 202):
        raise ContentUnderstandingError(f"Analyze failed: {resp.status_code} {resp.text}")
    op = resp.headers.get("Operation-Location")
    body = _poll(op) if op else resp.json()
    return parse_fields(body)


def parse_fields(response: dict) -> dict:
    contents = (response.get("result") or {}).get("contents") or []
    if not contents:
        return {}
    fields = contents[0].get("fields") or {}
    return {name: unwrap(value) for name, value in fields.items()}


def unwrap(field):
    """Collapse Content Understanding's typed field envelope into plain Python."""
    if not isinstance(field, dict):
        return field
    if "valueArray" in field:
        return [unwrap(v) for v in field["valueArray"]]
    if "valueObject" in field:
        return {k: unwrap(v) for k, v in field["valueObject"].items()}
    for key in ("valueString", "valueDate", "valueTime", "valueNumber", "valueInteger", "valueBoolean"):
        if key in field:
            return field[key]
    return field.get("content")
