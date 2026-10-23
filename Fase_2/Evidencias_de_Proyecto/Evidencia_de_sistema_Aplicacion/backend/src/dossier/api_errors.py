"""Códigos de error estables para que el frontend traduzca con i18n."""
from __future__ import annotations


class OrgApiError(Exception):
    """Error de negocio con código traducible en el cliente."""

    def __init__(self, code: str, **params: str) -> None:
        self.code = code
        self.params = params
        super().__init__(code)


def org_api_http_detail(exc: OrgApiError) -> dict[str, str]:
    return {"code": exc.code, **exc.params}


CORPORATE_EMAIL_REQUIRED = "CORPORATE_EMAIL_REQUIRED"
INVITE_WRONG_DOMAIN = "INVITE_WRONG_DOMAIN"
INVITES_WORKSPACE_ONLY = "INVITES_WORKSPACE_ONLY"
