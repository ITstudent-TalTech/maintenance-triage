"""Keyword fallback classifier.

Used when no LLM is configured or the LLM fails. Deliberately simple: it keeps
the pipeline running and gives the reviewer a starting point. Its results are
always sent to human review.
"""
from __future__ import annotations

import re

from .schema import Triage

# keywords in English, Estonian and Russian (lower-case stems)
KEYWORDS = {
    "FIRE_SAFETY": ["fire alarm", "sprinkler", "emergency exit", "exit sign", "tulekahju", "tulekahjusignalisatsioon", "evakuatsioon",
                    "пожар", "спринклер", "эвакуац"],
    "ELEVATOR": ["lift", "elevator", "escalator", "korruste vahele", "лифт"],
    "HVAC": ["ventilat", "air", "stuffy", "radiator", "heating", "cold", "ac unit", "hvac", "exhaust",
             "temperature", "°c", "ventilatsioon", "küte", "radiaator", "külm", "вентиляц", "батаре",
             "холодно", "отоплен", "кондиционер"],
    "PLUMBING": ["water", "leak", "tap", "toilet", "wc", "kraan", "tilgub", "vesi", "leke", "вода", "теч", "кран"],
    "ELECTRICAL": ["light", "socket", "power", "electrical", "burning", "breaker", "valgus", "pistikupesa", "elekter",
                   "свет", "автомат", "фонар", "розетк", "электр"],
    "DOORS_ACCESS": ["door", "gate", "card reader", "access", "uks", "värav", "дверь", "ворот"],
    "CLEANING_WASTE": ["trash", "garbage", "bin", "clean", "prügi", "koristus", "мусор", "уборк"],
}

P1_SIGNS = ["urgent", "asap", "trapped", "stuck", "jäi", "seisma", "burning", "smoke", "fire alarm", "fault",
            "blocked", "rising", "electrical cabinet", "no light", "нет света", "работа стоит", "kiire!"]
P2_SIGNS = ["not working", "stopped", "does not", "cold", "waiting", "cannot", "не работает", "холодно",
            "ei tööta", "külm", "dark", "темно", "stuffy"]
P4_SIGNS = ["quote", "planning", "next month", "thanks", "just letting you know", "pakkumine", "спасибо"]
P3_SIGNS = ["not urgent", "pole kiire", "не срочно", "kas saaks"]


def _contains(text: str, words: list[str]) -> int:
    return sum(1 for w in words if w in text)


def classify(request_id: str, text: str) -> Triage:
    t = text.lower()
    scores = {cat: _contains(t, words) for cat, words in KEYWORDS.items()}
    category, best = max(scores.items(), key=lambda kv: kv[1])
    if best == 0:
        category = "GENERAL"

    if _contains(t, P4_SIGNS):
        priority = "P4"
    elif _contains(t, P3_SIGNS):  # "not urgent" must win over "urgent"
        priority = "P3"
    elif _contains(t, P1_SIGNS):
        priority = "P1"
    elif _contains(t, P2_SIGNS):
        priority = "P2"
    else:
        priority = "P3"

    if category == "GENERAL" and priority != "P1":
        priority = "P4"

    room = re.search(r"(room|ruum|unit|korrus|floor|комнат)\s*\w*\s*(\d{1,4})", t)
    return Triage(
        id=request_id,
        category=category,
        priority=priority,
        summary=text[:120],
        location=room.group(0) if room else "",
        confidence=0.4 if best else 0.2,
        reason=f"keyword score {best}",
        source="rules",
    )
