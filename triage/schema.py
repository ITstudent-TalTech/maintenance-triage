"""Data model for a triaged maintenance request and validation of AI output."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

CATEGORIES = {
    "HVAC": "Heating, ventilation, cooling",
    "ELECTRICAL": "Power, lighting, sockets",
    "PLUMBING": "Water, leaks, sanitary",
    "FIRE_SAFETY": "Fire alarm, sprinklers, emergency exits",
    "ELEVATOR": "Lifts and escalators",
    "DOORS_ACCESS": "Doors, gates, access control",
    "CLEANING_WASTE": "Cleaning and waste",
    "GENERAL": "Other / information only",
}

# Priority -> target response time
PRIORITIES = {
    "P1": "Critical - respond within 2 h (safety risk or business stopped)",
    "P2": "High - same working day",
    "P3": "Normal - within 5 working days",
    "P4": "Planned - quote, request or info only",
}

# Which team gets the work order
ROUTING = {
    "HVAC": "HVAC technician",
    "ELECTRICAL": "Electrician",
    "PLUMBING": "Plumber",
    "FIRE_SAFETY": "Fire safety contractor",
    "ELEVATOR": "Elevator service company",
    "DOORS_ACCESS": "Doors & access contractor",
    "CLEANING_WASTE": "Cleaning service",
    "GENERAL": "Property manager",
}


@dataclass
class Triage:
    id: str
    category: str
    priority: str
    summary: str  # one line in English, for the work order
    location: str = ""  # floor / room / unit if mentioned
    language: str = ""  # et / en / ru
    confidence: float = 0.0  # 0..1, model's own estimate
    reason: str = ""  # short justification
    source: str = ""  # which engine produced it: llm:<provider> or rules
    assignee: str = ""
    needs_review: bool = False
    review_reasons: list[str] = field(default_factory=list)

    def to_row(self) -> dict:
        row = asdict(self)
        row["review_reasons"] = "; ".join(self.review_reasons)
        return row


class ValidationError(ValueError):
    pass


def validate(raw: dict, request_id: str) -> Triage:
    """Turn untrusted model output into a Triage, or raise ValidationError."""
    if not isinstance(raw, dict):
        raise ValidationError("output is not a JSON object")

    category = str(raw.get("category", "")).strip().upper()
    priority = str(raw.get("priority", "")).strip().upper()
    if category not in CATEGORIES:
        raise ValidationError(f"unknown category {category!r}")
    if priority not in PRIORITIES:
        raise ValidationError(f"unknown priority {priority!r}")

    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = min(max(confidence, 0.0), 1.0)

    summary = str(raw.get("summary", "")).strip()
    if not summary:
        raise ValidationError("empty summary")

    return Triage(
        id=request_id,
        category=category,
        priority=priority,
        summary=summary[:200],
        location=str(raw.get("location", "")).strip()[:80],
        language=str(raw.get("language", "")).strip().lower()[:5],
        confidence=confidence,
        reason=str(raw.get("reason", "")).strip()[:300],
    )
