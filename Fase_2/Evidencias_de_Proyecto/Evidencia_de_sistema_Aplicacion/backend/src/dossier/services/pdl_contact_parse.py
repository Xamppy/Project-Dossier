"""Parseo de respuestas PDL (person enrich / search)."""
from __future__ import annotations

from typing import Any


def pdl_person_from_enrich(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if isinstance(data, dict) and (data.get("id") or data.get("full_name")):
        return data
    return None


def pdl_people_from_search(payload: Any, *, max_items: int = 5) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    people = payload.get("data")
    if not isinstance(people, list):
        return []
    out: list[dict[str, Any]] = []
    for item in people:
        if isinstance(item, dict) and (item.get("id") or item.get("full_name")):
            out.append(item)
        if len(out) >= max_items:
            break
    return out
