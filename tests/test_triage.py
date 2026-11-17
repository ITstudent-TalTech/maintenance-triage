import pytest

from triage import llm, pipeline, rules
from triage.privacy import mask
from triage.schema import ValidationError, validate

REQ = {"id": "T-1", "building": "Test House", "text": "Lift stuck between floors, person inside! Call +372 5555 1234"}


def test_mask_removes_personal_data():
    out = mask("Write to anna.tamm@example.com or call +372 5555 1234, ID 38001010000")
    assert "anna" not in out and "5555" not in out and "38001010000" not in out
    assert "[EMAIL]" in out and "[PHONE]" in out and "[ID]" in out


def test_validate_rejects_unknown_category():
    with pytest.raises(ValidationError):
        validate({"category": "ROOF", "priority": "P1", "summary": "x"}, "T-1")


def test_validate_clamps_confidence():
    t = validate({"category": "hvac", "priority": "p2", "summary": "Cold office", "confidence": 7}, "T-1")
    assert t.category == "HVAC" and t.priority == "P2" and t.confidence == 1.0


def test_llm_result_is_used_and_masked(monkeypatch):
    seen = {}

    def fake_classify(provider, building, text):
        seen["text"] = text
        return {"category": "ELEVATOR", "priority": "P1", "summary": "Person trapped in lift",
                "confidence": 0.95, "language": "en"}

    monkeypatch.setattr(llm, "classify", fake_classify)
    t = pipeline.triage_one(REQ, "anthropic")
    assert t.source == "llm:anthropic" and t.category == "ELEVATOR"
    assert t.assignee == "Elevator service company"
    assert "5555" not in seen["text"]  # personal data never reaches the model
    assert t.needs_review and "P1" in t.review_reasons[0]


def test_falls_back_to_rules_when_llm_returns_garbage(monkeypatch):
    monkeypatch.setattr(llm, "classify", lambda *a: {"category": "???", "priority": "P9"})
    t = pipeline.triage_one(REQ, "openai")
    assert t.source == "rules"
    assert "no LLM result" in t.review_reasons


def test_falls_back_when_llm_unreachable(monkeypatch):
    def boom(*a):
        raise llm.LLMError("connection refused")

    monkeypatch.setattr(llm, "classify", boom)
    assert pipeline.triage_one(REQ, "lmstudio").source == "rules"


def test_extract_json_from_chatty_answer():
    raw = 'Sure! Here it is:\n```json\n{"category": "HVAC", "priority": "P3", "summary": "x"}\n```'
    assert llm._extract_json(raw)["category"] == "HVAC"


@pytest.mark.parametrize("text,cat,pri", [
    ("Several lights flickering, not urgent", "ELECTRICAL", "P3"),
    ("Radiators are cold in the office", "HVAC", "P2"),
    ("Please quote two extra sockets next month", "ELECTRICAL", "P4"),
])
def test_rules(text, cat, pri):
    t = rules.classify("T", text)
    assert (t.category, t.priority) == (cat, pri)


def test_safety_net_escalates_missed_emergency(monkeypatch):
    # a real failure seen with a small local model: burning smell rated P2
    monkeypatch.setattr(llm, "classify", lambda *a: {"category": "ELECTRICAL", "priority": "P2",
                                                     "summary": "Burning smell", "confidence": 0.95})
    req = {"id": "T-2", "building": "B", "text": "Smell of burning plastic near the electrical room"}
    t = pipeline.triage_one(req, "lmstudio")
    assert t.priority == "P1" and t.needs_review
    assert any("escalated from P2" in r for r in t.review_reasons)
