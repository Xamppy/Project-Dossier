"""Normalización de fechas Microsoft Graph (UTC sin sufijo Z)."""

from dossier.services.graph_calendar import _graph_datetime_to_utc_iso, normalizar_evento


def test_graph_datetime_naive_utc_gets_z_suffix():
    assert _graph_datetime_to_utc_iso("2025-07-06T03:30:00.0000000") == "2025-07-06T03:30:00Z"


def test_graph_datetime_already_z_unchanged():
    assert _graph_datetime_to_utc_iso("2025-07-06T03:30:00Z") == "2025-07-06T03:30:00Z"


def test_graph_datetime_with_offset_converts_to_utc():
    assert _graph_datetime_to_utc_iso("2025-07-05T23:30:00-04:00") == "2025-07-06T03:30:00Z"


def test_normalizar_evento_converts_start_end():
    evento = {
        "id": "abc",
        "subject": "Reunion Nvidia",
        "start": {"dateTime": "2025-07-06T03:30:00.0000000", "timeZone": "UTC"},
        "end": {"dateTime": "2025-07-06T04:00:00.0000000", "timeZone": "UTC"},
        "isAllDay": False,
    }
    out = normalizar_evento(evento)
    assert out["inicio"] == "2025-07-06T03:30:00Z"
    assert out["fin"] == "2025-07-06T04:00:00Z"
