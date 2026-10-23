"""Conversión de HTML a texto plano (calendarios, títulos de dossier)."""
from __future__ import annotations

import html
import re


def strip_html_to_text(raw: str | None) -> str:
    """Convierte HTML a texto plano conservando saltos de línea."""
    if not raw or not str(raw).strip():
        return ""
    t = str(raw)
    t = re.sub(r"(?i)<br\s*/?>", "\n", t)
    t = re.sub(r"(?i)</(p|div|li|tr|h[1-6]|pre)>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    lines: list[str] = []
    for ln in t.splitlines():
        cleaned = re.sub(r"[ \t]+", " ", ln).strip()
        if not cleaned:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        lines.append(cleaned)
    return "\n".join(lines).strip()


def strip_html_to_plain_line(raw: str | None, *, max_len: int | None = None) -> str:
    """Una sola línea legible (títulos, asuntos de reunión)."""
    text = strip_html_to_text(raw)
    line = re.sub(r"\s+", " ", text).strip()
    if max_len is not None and max_len > 0:
        line = line[:max_len]
    return line
