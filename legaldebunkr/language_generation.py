"""Step 3: language generation (Azure OpenAI).

Turns extracted structure and raw legalese into plain-English explanations:
an overview with red flags, per-section translations with a jargon glossary,
and grounded answers to follow-up questions.
"""
from __future__ import annotations

import json

from openai import AzureOpenAI

from .config import settings

DISCLAIMER = (
    "LegalDebunkr explains documents in plain language. It is not a lawyer and "
    "this is not legal advice."
)

SYSTEM = (
    "You translate legal documents into plain English for people with no legal "
    "training. Write at roughly an 8th-grade reading level. Use short sentences "
    "and concrete words. Say 'you' when the reader is likely a party to the "
    "document. Stay faithful to the text: never invent terms, numbers, or dates "
    "that are not in it, and say 'the document doesn't say' when something is "
    "missing. Flag anything unusual, one-sided, or costly. Do not give legal "
    "advice or predict outcomes. Respond with a single JSON object only."
)


def _client() -> AzureOpenAI:
    return AzureOpenAI(
        azure_endpoint=settings.aoai_endpoint,
        api_key=settings.aoai_key,
        api_version=settings.aoai_api_version,
    )


def _chat_json(prompt: str, max_tokens: int = 1500) -> dict:
    resp = _client().chat.completions.create(
        model=settings.aoai_deployment,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
        max_tokens=max_tokens,
    )
    return json.loads(resp.choices[0].message.content or "{}")


def explain_overview(fields: dict, headings: list[str], excerpt: str) -> dict:
    prompt = f"""Summarize this legal document for a non-expert.

Structured facts extracted from the document (may be empty):
{json.dumps(fields, indent=2, default=str)}

Section headings: {json.dumps(headings)}

Opening text of the document:
\"\"\"{excerpt}\"\"\"

Return JSON with exactly these keys:
- "plain_summary": 3-5 sentences on what this document is and what it does.
- "who_is_involved": list of {{"name": str, "role": str, "in_plain_terms": str}}.
- "what_you_must_do": list of short strings.
- "what_you_get": list of short strings.
- "key_dates_and_money": list of {{"label": str, "detail": str}}.
- "red_flags": list of {{"title": str, "why_it_matters": str, "severity": "low"|"medium"|"high"}}.
- "questions_for_a_lawyer": list of 3-6 specific questions worth asking a professional.
"""
    return _chat_json(prompt, max_tokens=2000)


def explain_section(heading: str, text: str) -> dict:
    prompt = f"""Explain this section of a legal document.

Heading: {heading}
Text:
\"\"\"{text}\"\"\"

Return JSON with exactly these keys:
- "plain_english": a clear rewrite of what this section means, in 2-6 sentences.
- "jargon": list of {{"term": str, "meaning": str}} for legal terms used here (max 6).
- "watch_out": one sentence on anything risky or unusual, or null if nothing stands out.
- "severity": "none"|"low"|"medium"|"high".
"""
    return _chat_json(prompt, max_tokens=900)


def answer_question(question: str, context_sections: list[dict], fields: dict) -> dict:
    context = "\n\n".join(f"[{s['heading']}]\n{s['text']}" for s in context_sections)
    prompt = f"""Answer the reader's question using ONLY the document excerpts below.
If the excerpts do not answer it, say so plainly.

Extracted facts:
{json.dumps(fields, indent=2, default=str)}

Excerpts:
\"\"\"{context}\"\"\"

Question: {question}

Return JSON with keys:
- "answer": plain-English answer in 1-4 sentences.
- "sections_used": list of section headings you relied on.
- "confidence": "high"|"medium"|"low".
"""
    return _chat_json(prompt, max_tokens=700)
