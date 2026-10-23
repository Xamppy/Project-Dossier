"""Tests unitarios — entitlements por plan."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from dossier.billing.entitlements import (
    allowed_depths_for_plan,
    assert_corporate_dossier_allowed,
    assert_depth_allowed,
    plan_allows_automation,
    plan_allows_corporate_dossier,
    plan_allows_depth,
)
from dossier.db.models import Organization


def _org(plan: str) -> Organization:
    return Organization(name="Acme", slug=f"acme-{plan}", plan=plan)


def test_free_plan_depth_basic_only():
    assert allowed_depths_for_plan("free") == frozenset({"basic"})
    assert plan_allows_depth("free", "basic")
    assert not plan_allows_depth("free", "standard")


def test_pro_plan_all_depths():
    assert plan_allows_depth("pro", "deep")


def test_free_blocks_automation_and_corporate():
    assert not plan_allows_automation("free")
    assert not plan_allows_corporate_dossier("free")
    assert plan_allows_corporate_dossier("pro")


def test_assert_depth_allowed_raises_for_free_standard():
    with pytest.raises(HTTPException) as exc:
        assert_depth_allowed(_org("free"), "standard")
    assert exc.value.status_code == 403


def test_assert_corporate_dossier_allowed_raises_for_free():
    with pytest.raises(HTTPException) as exc:
        assert_corporate_dossier_allowed(_org("free"))
    assert exc.value.status_code == 403


def test_assert_corporate_dossier_allowed_pro_ok():
    assert_corporate_dossier_allowed(_org("pro")) is None
