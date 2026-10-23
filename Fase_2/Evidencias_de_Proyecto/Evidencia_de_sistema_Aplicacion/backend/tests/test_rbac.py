"""Tests unitarios — RBAC de organización."""
from __future__ import annotations

from dossier.security.rbac import (
    can_manage_organization,
    can_mutate_dossiers,
    normalize_org_role,
    role_at_least,
)


def test_viewer_cannot_mutate():
    assert not can_mutate_dossiers("viewer")


def test_user_and_admin_can_mutate():
    assert can_mutate_dossiers("user")
    assert can_mutate_dossiers("admin")
    assert can_mutate_dossiers("api_user")


def test_only_admin_manages_org():
    assert can_manage_organization("admin")
    assert not can_manage_organization("user")


def test_normalize_unknown_role_defaults_user():
    assert normalize_org_role("unknown") == "user"


def test_role_hierarchy():
    assert role_at_least("admin", "user")
    assert not role_at_least("viewer", "user")
