"""A deterministic extractive summarizer that preserves exact evidence text."""

from __future__ import annotations

import re

from .models import Source


WORD_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]+")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
    "in", "is", "it", "of", "on", "or", "that", "the", "this", "to", "was",
    "were", "will", "with",
}


def _tokens(text: str) -> set[str]:
    return {word.lower() for word in WORD_RE.findall(text) if word.lower() not in STOP_WORDS}


def summarize_sources(sources: list[Source], focus: str, *, per_source: int = 5) -> list[dict[str, object]]:
    focus_words = _tokens(focus)
    output: list[dict[str, object]] = []

    for source in sources:
        sentences = [
            " ".join(sentence.split())
            for sentence in SENTENCE_RE.split(source.text)
            if 40 <= len(" ".join(sentence.split())) <= 700
        ]
        scored: list[tuple[int, int, str]] = []
        for index, sentence in enumerate(sentences):
            overlap = len(_tokens(sentence) & focus_words)
            # Earlier passages get a small tie breaking advantage.
            scored.append((overlap, -index, sentence))
        scored.sort(reverse=True)
        selected = [item[2] for item in scored[:per_source]]
        output.append(
            {
                "source_id": source.source_id,
                "title": source.title,
                "evidence_passages": selected,
            }
        )
    return output
