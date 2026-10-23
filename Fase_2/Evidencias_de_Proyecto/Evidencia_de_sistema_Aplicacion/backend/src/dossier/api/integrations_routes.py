"""Estado de integraciones externas (PDL)."""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["Integraciones"])


@router.get("/integrations/pdl/health")
def pdl_integration_health():
    """
    Comprueba ``PDL_API_KEY`` y acceso a People Data Labs.

    Un enrich de prueba con 404 indica clave válida pero sin match (esperado).
    """
    key = (
        (os.getenv("PDL_API_KEY") or os.getenv("PEOPLE_DATA_LABS_API_KEY") or "").strip()
    )
    if not key:
        return {
            "configured": False,
            "status": "missing_key",
            "message": "Define PDL_API_KEY en .env (PDL Dashboard → API Keys).",
        }

    try:
        from dossier.services.pdl_client import PdlApiError, PdlClient, pdl_error_message

        client = PdlClient(api_key=key)
        access = client.check_access()
        if access.get("enrich_access") or access.get("search_access"):
            return {
                "configured": True,
                "status": "ok",
                "api_reachable": True,
                "enrich_access": access.get("enrich_access"),
                "search_access": access.get("search_access"),
                "test_match": access.get("test_match"),
                "message": "Clave PDL válida y API accesible.",
            }
        errors = access.get("errors") or []
        first = errors[0] if errors else {}
        status = int(first.get("http_status") or 502)
        if status == 401:
            raise HTTPException(status_code=502, detail=pdl_error_message(PdlApiError(401, str(first)))) from None
        return {
            "configured": True,
            "status": "error",
            "api_reachable": True,
            "errors": errors,
            "message": "No se pudo usar la API PDL con esta clave.",
        }
    except HTTPException:
        raise
    except PdlApiError as e:
        raise HTTPException(status_code=502, detail=pdl_error_message(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"No se pudo contactar PDL: {e}") from e
