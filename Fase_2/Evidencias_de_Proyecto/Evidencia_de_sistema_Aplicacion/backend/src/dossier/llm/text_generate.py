"""
Generación de texto con DeepSeek.

Usada por el grafo LangGraph, dossiers de persona y síntesis corporativa.
"""
from __future__ import annotations

from dossier.llm.client import chat_completion


def generate_text_with_llm(
    prompt: str,
    *,
    model: str | None = None,
    system_instruction: str | None = None,
    max_retries: int = 4,
) -> str:
    return chat_completion(
        prompt,
        system_instruction=system_instruction,
        model=model,
        max_retries=max_retries,
    )
