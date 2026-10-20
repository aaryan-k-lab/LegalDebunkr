"""Tiny keyword retriever used to ground follow-up questions."""
from __future__ import annotations

import math
import re
from collections import Counter

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "is", "are", "be", "for", "on",
    "this", "that", "it", "my", "i", "do", "does", "can", "what", "if", "with", "as",
    "by", "at", "me", "we", "you", "your", "how", "when", "will", "any",
}


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9']+", text.lower()) if t not in STOPWORDS]


def top_sections(question: str, sections: list[dict], k: int = 4) -> list[dict]:
    q_terms = tokenize(question)
    if not q_terms or not sections:
        return sections[:k]

    docs = [tokenize(s["heading"] + " " + s["text"]) for s in sections]
    n = len(docs)
    df = Counter(t for d in docs for t in set(d))
    scores = []
    for idx, d in enumerate(docs):
        tf = Counter(d)
        length = len(d) or 1
        score = 0.0
        for t in q_terms:
            if t in tf:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                score += idf * (tf[t] / length) * 10
        scores.append((score, idx))
    scores.sort(reverse=True)
    picked = [sections[i] for s, i in scores[:k] if s > 0]
    return picked or sections[:k]
