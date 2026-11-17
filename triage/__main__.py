"""Command line entry point.

    python -m triage                      # uses TRIAGE_PROVIDER or 'rules'
    python -m triage --provider lmstudio
    python -m triage --eval               # also score against data/labels.csv
"""
from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from . import evaluate, pipeline, report

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    ap = argparse.ArgumentParser(description="AI triage of building maintenance requests")
    ap.add_argument("--input", default=ROOT / "data" / "requests.jsonl", type=Path)
    ap.add_argument("--out", default=ROOT / "output", type=Path)
    ap.add_argument("--provider", default=os.getenv("TRIAGE_PROVIDER", "rules"),
                    choices=["anthropic", "openai", "lmstudio", "rules"])
    ap.add_argument("--eval", action="store_true", help="compare with data/labels.csv")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(args.out / "run.log", encoding="utf-8")],
    )

    requests = pipeline.load_requests(args.input)
    results = pipeline.run(requests, args.provider)
    rows = report._rows(results, requests)
    report.write_csv(rows, args.out / "work_orders.csv")
    report.write_excel(rows, args.out / "work_orders.xlsx")
    print(report.write_summary(rows, args.out / "summary.md", args.provider))

    if args.eval:
        print(evaluate.score(results, ROOT / "data" / "labels.csv"))


if __name__ == "__main__":
    main()
