"""Formato de fecha/hora de reuniones de calendario."""

from dossier.services.calendar_event_dossiers import _format_meeting_datetime


def test_meeting_datetime_uses_user_timezone_not_utc_display():
    # 22:40 en Chile (UTC-4) el 5 jul 2026 ≈ 02:40 UTC del 6 jul
    iso = "2026-07-06T02:40:00Z"
    utc_label = _format_meeting_datetime(iso, "UTC")
    assert utc_label == "06/07/2026 02:40"
    santiago = _format_meeting_datetime(iso, "America/Santiago")
    assert santiago == "05/07/2026 22:40"
