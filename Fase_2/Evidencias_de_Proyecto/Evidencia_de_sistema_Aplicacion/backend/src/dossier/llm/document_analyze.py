"""
Análisis de documentos (HTML, texto) con DeepSeek.

Extrae texto del archivo, lo trunca si hace falta y lo envía como prompt.
"""
from __future__ import annotations

import html
import os
import re
from pathlib import Path

from dossier.config import load_env
from dossier.llm.client import chat_completion

MAX_BYTES_WARN = 45 * 1024 * 1024
DEFAULT_MAX_DOCUMENT_CHARS = 120_000


def _strip_html_to_text(raw: str) -> str:
    t = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    t = re.sub(r"(?i)</(p|div|li|tr|h[1-6])>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    lines: list[str] = []
    for ln in t.splitlines():
        cleaned = re.sub(r"[ \t]+", " ", ln).strip()
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines).strip()


def _bytes_to_document_text(data: bytes, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    text = data.decode("utf-8", errors="replace")
    if suffix in (".html", ".htm", ".xhtml"):
        return _strip_html_to_text(text)
    return text.strip()


def _max_document_chars() -> int:
    load_env()
    for name in ("DEEPSEEK_MAX_DOCUMENT_CHARS", "GEMINI_MAX_UPLOAD_BYTES"):
        raw = (os.getenv(name) or "").strip()
        if raw.isdigit():
            return max(4000, int(raw))
    return DEFAULT_MAX_DOCUMENT_CHARS


def _truncate_document_text(text: str, filename: str, limit: int) -> tuple[str, str]:
    if len(text) <= limit:
        return text, ""
    cut = text[:limit]
    note = (
        f"\n\n[Nota del sistema: el archivo «{filename}» solo se envió truncado a "
        f"los primeros ~{len(cut) // 1024} KiB de texto. Analiza solo el fragmento visible.]"
    )
    return cut, note


def analyze_document_bytes(
    data: bytes,
    filename: str,
    prompt: str,
    *,
    model: str | None = None,
) -> str:
    if len(data) > MAX_BYTES_WARN:
        raise ValueError(
            f"El archivo supera ~{MAX_BYTES_WARN // (1024 * 1024)} MB; "
            "reduce tamaño o divide el documento."
        )

    body, trunc_note = _truncate_document_text(
        _bytes_to_document_text(data, filename),
        filename,
        _max_document_chars(),
    )
    if not body.strip():
        raise RuntimeError(f"No se pudo extraer texto legible de «{filename}».")

    user_prompt = (
        f"{prompt.strip()}\n\n"
        f"---\n"
        f"### Documento: {filename}\n\n"
        f"{body}"
        f"{trunc_note}"
    )
    return chat_completion(user_prompt, model=model)
