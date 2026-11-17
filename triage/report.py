"""Write results to Excel (with a review column), CSV and a short Markdown summary."""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from .schema import CATEGORIES, PRIORITIES, Triage

COLUMNS = ["id", "received_at", "building", "category", "priority", "assignee", "summary", "request_text", "location",
           "language", "confidence", "source", "needs_review", "review_reasons", "reason"]


def _rows(results: list[Triage], requests: list[dict]) -> list[dict]:
    by_id = {r["id"]: r for r in requests}
    rows = []
    for t in results:
        row = t.to_row()
        row["received_at"] = by_id[t.id].get("received_at", "")
        row["building"] = by_id[t.id].get("building", "")
        row["request_text"] = by_id[t.id].get("text", "")  # reviewer checks the AI summary against the original
        rows.append({c: row.get(c, "") for c in COLUMNS})
    # most urgent first
    return sorted(rows, key=lambda r: (r["priority"], not r["needs_review"], r["received_at"]))


def write_csv(rows: list[dict], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)


def write_excel(rows: list[dict], path: Path) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    ws = wb.active
    ws.title = "Work orders"
    headers = COLUMNS + ["reviewer_decision", "reviewer_note"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F3A5F")

    fills = {"P1": "F8D7DA", "P2": "FFF3CD", "P3": "FFFFFF", "P4": "E2E3E5"}
    for r in rows:
        ws.append([r[c] for c in COLUMNS] + ["", ""])
        for cell in ws[ws.max_row]:
            cell.fill = PatternFill("solid", fgColor=fills[r["priority"]])

    # reviewer picks from a dropdown instead of free text
    dv = DataValidation(type="list", formula1='"Approve,Change category,Change priority,Reject"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"{chr(64 + len(COLUMNS) + 1)}2:{chr(64 + len(COLUMNS) + 1)}{ws.max_row}")

    widths = {"summary": 50, "request_text": 60, "reason": 50, "review_reasons": 35, "assignee": 24, "building": 22}
    for i, h in enumerate(headers, start=1):
        ws.column_dimensions[chr(64 + i)].width = widths.get(h, 14)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    s = wb.create_sheet("Summary")
    s.append(["Priority", "Meaning", "Count"])
    pc = Counter(r["priority"] for r in rows)
    for p, meaning in PRIORITIES.items():
        s.append([p, meaning, pc.get(p, 0)])
    s.append([])
    s.append(["Category", "Meaning", "Count"])
    cc = Counter(r["category"] for r in rows)
    for c, meaning in CATEGORIES.items():
        s.append([c, meaning, cc.get(c, 0)])
    s.column_dimensions["B"].width = 60
    wb.save(path)


def write_summary(rows: list[dict], path: Path, provider: str) -> str:
    p1 = [r for r in rows if r["priority"] == "P1"]
    review = [r for r in rows if r["needs_review"]]
    lines = [
        f"# Maintenance triage summary ({len(rows)} requests, engine: {provider})",
        "",
        f"- P1 critical: **{len(p1)}**, sent to human review: **{len(review)}**",
        "",
        "## P1 - act now",
        "",
        *[f"- {r['id']} {r['building']}: {r['summary']} -> {r['assignee']}" for r in p1],
        "",
        "## By category",
        "",
        *[f"- {c}: {n}" for c, n in Counter(r["category"] for r in rows).most_common()],
    ]
    text = "\n".join(lines) + "\n"
    path.write_text(text, encoding="utf-8")
    return text
