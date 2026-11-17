"""End-to-end pipeline: read requests -> mask -> classify -> validate -> route -> flag for review."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from . import llm, rules
from .privacy import mask
from .schema import ROUTING, Triage, ValidationError, validate

log = logging.getLogger(__name__)

REVIEW_CONFIDENCE = float(os.getenv("TRIAGE_REVIEW_BELOW", "0.75"))


def load_requests(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def triage_one(req: dict, provider: str) -> Triage:
    masked = mask(req["text"])
    result: Triage | None = None

    if provider != "rules":
        try:
            raw = llm.classify(provider, req.get("building", ""), masked)
            result = validate(raw, req["id"])
            result.source = f"llm:{provider}"
        except (llm.LLMError, ValidationError) as exc:
            log.error("%s: LLM result rejected (%s), falling back to rules", req["id"], exc)

    safety_net = rules.classify(req["id"], masked)
    if result is None:
        result = safety_net
    else:
        # Safety net: a cheap keyword check runs next to the LLM. Tests showed a small local model
        # downgrading real emergencies (burning smell, power loss) and inventing details.
        if safety_net.priority == "P1" and result.priority != "P1":
            result.review_reasons.append(f"safety keywords - escalated from {result.priority} to P1")
            result.priority = "P1"
        if safety_net.confidence >= 0.4 and safety_net.category != result.category:
            result.review_reasons.append(f"rules suggest {safety_net.category}")

    result.assignee = ROUTING[result.category]

    # Human-in-the-loop: decide what a person must look at before work orders go out
    if result.source == "rules":
        result.review_reasons.append("no LLM result")
    if result.confidence < REVIEW_CONFIDENCE:
        result.review_reasons.append(f"low confidence {result.confidence:.2f}")
    if result.priority == "P1":
        result.review_reasons.append("P1 - confirm by phone")
    if result.category == "GENERAL":
        result.review_reasons.append("no clear category")
    result.needs_review = bool(result.review_reasons)
    return result


def run(requests: list[dict], provider: str) -> list[Triage]:
    results = []
    for req in requests:
        t = triage_one(req, provider)
        log.info("%s -> %s %s (%s, conf %.2f)%s", t.id, t.category, t.priority, t.source, t.confidence,
                 " REVIEW" if t.needs_review else "")
        results.append(t)
    return results
