"""Measure accuracy against hand-labelled data, so engines and prompts can be compared."""
from __future__ import annotations

import csv
from pathlib import Path

from .schema import Triage


def score(results: list[Triage], labels_path: Path) -> str:
    with open(labels_path, encoding="utf-8") as f:
        gold = {r["id"]: r for r in csv.DictReader(f)}

    n = cat_ok = pri_ok = p1_missed = 0
    errors = []
    for t in results:
        g = gold.get(t.id)
        if not g:
            continue
        n += 1
        cat_ok += t.category == g["category"]
        pri_ok += t.priority == g["priority"]
        if g["priority"] == "P1" and t.priority != "P1":
            p1_missed += 1
        if t.category != g["category"] or t.priority != g["priority"]:
            errors.append(f"  {t.id}: got {t.category}/{t.priority}, expected {g['category']}/{g['priority']}")

    lines = [
        f"Evaluation on {n} labelled requests",
        f"  category accuracy: {cat_ok}/{n} ({cat_ok / n:.0%})",
        f"  priority accuracy: {pri_ok}/{n} ({pri_ok / n:.0%})",
        f"  P1 requests missed: {p1_missed}  (the number that matters most)",
    ]
    if errors:
        lines += ["  mismatches:"] + errors
    return "\n".join(lines)
