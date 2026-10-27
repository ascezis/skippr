import re
import unicodedata

PUNCTUATION_RE = re.compile(r"[^\w\s]", re.UNICODE)
SPACES_RE = re.compile(r"\s+", re.UNICODE)


def normalize_text(text: str) -> str:
    """
    Normalizes text for matching:
    - Unicode NFC normalization
    - Lowercase
    - Replace 'ё' with 'е'
    - Replace hyphens/dashes with spaces
    - Remove punctuation
    - Collapse multiple whitespace
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFC", str(text))
    text = text.lower().replace("ё", "е")
    # Replace dashes/slashes with space so composite words match separated words
    text = re.sub(r"[-–—/]+", " ", text)
    # Remove remaining punctuation
    text = PUNCTUATION_RE.sub(" ", text)
    # Collapse spaces
    text = SPACES_RE.sub(" ", text).strip()
    return text


def tokenize_text(text: str) -> list[str]:
    """Normalizes and splits text into list of words."""
    norm = normalize_text(text)
    return norm.split() if norm else []
