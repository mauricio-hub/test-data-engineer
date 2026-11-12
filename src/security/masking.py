"""Detección y enmascaramiento conservador de PII con los patrones existentes."""
from __future__ import annotations

import re


EMAIL = re.compile(r"[\w.!#$%&'*+/=?^`{|}~-]+@[\w-]+(?:\.[\w-]+)+", re.IGNORECASE)
MOBILE = re.compile(r"(?<!\w)(?:\+?57[ .()-]*)?3\d{2}[ .()-]*\d{3}[ .()-]*\d{4}(?!\w)")
DOCUMENT = re.compile(
    r"\b(?:c[eé]dula|c\.?\s*c\.?|documento)\s*(?:n[úu]mero\s*|n[°º]\s*)?[:#-]?\s*"
    r"\d(?:[ .-]?\d){5,11}(?!\w)", re.IGNORECASE,
)
BARE_DOCUMENT = re.compile(r"(?<!\w)\d(?:[ .-]?\d){5,11}(?!\w)")


def mask_pii(text: str) -> tuple[str, bool]:
    """Heurísticas conservadoras; el texto resultante sigue siendo restringido."""
    found = False
    for pattern, replacement in ((EMAIL, "[EMAIL]"), (MOBILE, "[CELULAR]"),
                                 (DOCUMENT, "[DOCUMENTO]"), (BARE_DOCUMENT, "[DOCUMENTO]")):
        text, count = pattern.subn(replacement, text)
        found = found or count > 0
    return text, found
