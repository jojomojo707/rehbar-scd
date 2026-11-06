"""A provider with no model and no network.

Use it for every unit test and for CI (section 6): your tests must never call a
real model. It is deterministic: the same input always gives the same output.
"""

from __future__ import annotations

import html
import json
import re

from ...schemas import Answer, Citation, Passage
from .base import Completion


class StubProvider:
    name = "stub"

    def generate(self, question: str, passages: list[Passage]) -> Answer:
        del question
        if not passages:
            return Answer(
                reasoning="stub: nothing was retrieved",
                answer="The documents do not cover this question.",
                citations=[],
                answered_from_context=False,
                confidence="low",
            )
        top = passages[0]
        return Answer(
            reasoning="stub: cites the first retrieved passage",
            answer=f"(stub) The first passage says: {top.text[:240]} "
            f"[{top.source} / {top.section}]",
            citations=[Citation(source=top.source, section=top.section, page=top.page)],
            answered_from_context=True,
            confidence="low",
        )

    def complete(
        self, messages: list[dict[str, str]], schema: dict[str, object], temperature: float
    ) -> Completion:
        del schema, temperature
        content = messages[-1]["content"] if messages else ""
        match = re.search(
            r"<evidence\b([^>]*)>(.*?)</evidence>",
            content,
            re.DOTALL | re.IGNORECASE,
        )
        if match is None:
            answer = {
                "reasoning": "stub: no evidence was supplied",
                "answer": "The documents do not cover this question.",
                "citations": [],
                "answered_from_context": False,
                "confidence": "low",
            }
        else:
            attrs = dict(re.findall(r'([a-z_]+)="([^"]*)"', match.group(1), re.IGNORECASE))
            source = html.unescape(attrs.get("source", "unknown"))
            section = html.unescape(attrs.get("section", ""))
            page = attrs.get("page", "")
            passage = match.group(2).strip()
            cited = f"[{source} / {section}]"
            answer = {
                "reasoning": "stub: cites the first supplied evidence block",
                "answer": f"(stub) The first passage says: {passage[:240]} {cited}",
                "citations": [{"source": source, "section": section,
                               "page": int(page) if page.isdigit() else None}],
                "answered_from_context": True,
                "confidence": "low",
            }
        return Completion(text=json.dumps(answer), tokens_in=0, tokens_out=0, model="stub")
