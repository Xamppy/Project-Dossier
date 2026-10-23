"""Tests unitarios — política de créditos."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from dossier.billing.credit_policy import (
    PERSON_IDENTITY_CREDITS,
    assert_sufficient_credits,
    calendar_event_credit_estimate,
    person_research_credit_cost,
)
from dossier.db.models import Organization


def _org(*, plan: str = "pro", balance: int = 10) -> Organization:
    return Organization(name="Acme", slug="acme-test", plan=plan, credits_balance=balance)


def test_person_research_cost_is_one_credit():
    assert person_research_credit_cost() == PERSON_IDENTITY_CREDITS == 1


def test_assert_sufficient_credits_ok():
    assert_sufficient_credits(_org(balance=5), 1)


def test_assert_sufficient_credits_insufficient_raises_402():
    with pytest.raises(HTTPException) as exc:
        assert_sufficient_credits(_org(balance=0), 1)
    assert exc.value.status_code == 402


def test_enterprise_unlimited_skips_balance_check():
    assert_sufficient_credits(_org(plan="enterprise", balance=0), 99)


def test_calendar_estimate_corporate_plus_two_persons():
    total = calendar_event_credit_estimate(
        has_corporate=True,
        person_count=2,
        depth="standard",
    )
    assert total == 3 + 2 * PERSON_IDENTITY_CREDITS


def test_calendar_estimate_person_only():
    assert calendar_event_credit_estimate(has_corporate=False, person_count=1) == 1
