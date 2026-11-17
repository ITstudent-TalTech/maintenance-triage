"""Mask personal data before text leaves the company (GDPR data minimisation)."""
import re

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_PHONE = re.compile(r"(\+?\d[\d\s-]{6,}\d)")
_ISIKUKOOD = re.compile(r"\b[1-6]\d{10}\b")  # Estonian personal ID code


def mask(text: str) -> str:
    text = _EMAIL.sub("[EMAIL]", text)
    text = _ISIKUKOOD.sub("[ID]", text)
    text = _PHONE.sub("[PHONE]", text)
    return text
