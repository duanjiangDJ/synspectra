from __future__ import annotations

import re


def extract_text_from_file(filepath: str) -> str:
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read().strip()


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"(https?://\S+|ftp://\S+|www\.\S+)", " ", text)
    text = text.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return re.sub(r"\s+", " ", text).strip()