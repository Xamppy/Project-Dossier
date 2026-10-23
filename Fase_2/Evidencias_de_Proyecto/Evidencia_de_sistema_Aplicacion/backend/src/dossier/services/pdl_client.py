"""Cliente HTTP para People Data Labs API v5 (person enrich / search)."""
from __future__ import annotations

import json
import os
from typing import Any

import requests

DEFAULT_BASE = "https://api.peopledatalabs.com"


class PdlApiError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"PDL HTTP {status}: {body[:500]}")
        self.status = status
        self.body = body

    def parsed(self) -> dict[str, Any]:
        try:
            data = json.loads(self.body or "")
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}


def pdl_error_message(err: PdlApiError) -> str:
    data = err.parsed()
    nested = data.get("error")
    if isinstance(nested, dict):
        msg = str(nested.get("message") or "").strip()
        typ = str(nested.get("type") or "").strip()
        if typ and msg:
            return f"PDL ({typ}): {msg}"
        if msg:
            return f"PDL: {msg}"
    if err.status == 401:
        return "PDL respondió 401: revisa PDL_API_KEY en `.env`."
    if err.status == 402:
        return (
            "PDL: créditos de enriquecimiento agotados. "
            "Se intentó búsqueda alternativa; si no hay resultados, recarga créditos en tu cuenta PDL."
        )
    if err.status == 429:
        return "PDL respondió 429 (límite de tasa). Espera y reintenta."
    return f"PDL HTTP {err.status}: {(err.body or '')[:280]}"


class PdlClient:
    """
    Auth: cabecera ``X-Api-Key`` (dashboard PDL → API Keys).

    Docs: https://docs.peopledatalabs.com/docs/reference-person-enrichment-api
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: int = 90,
    ):
        key = (
            api_key
            or os.getenv("PDL_API_KEY")
            or os.getenv("PEOPLE_DATA_LABS_API_KEY")
            or ""
        ).strip()
        if not key:
            raise ValueError(
                "Falta PDL_API_KEY en el entorno (.env). "
                "Créala en People Data Labs → Dashboard → API Keys."
            )
        self._api_key = key
        self._base = (base_url or os.getenv("PDL_API_URL") or DEFAULT_BASE).rstrip("/")
        self._timeout = timeout
        self._min_likelihood = int(os.getenv("PDL_MIN_LIKELIHOOD", "2"))

    def _headers(self) -> dict[str, str]:
        return {
            "X-Api-Key": self._api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def person_enrich(self, params: dict[str, Any]) -> dict[str, Any] | None:
        """
        GET /v5/person/enrich — match 1:1.

        Devuelve ``None`` en HTTP 404 (sin match, no es error de clave).
        """
        clean = {k: v for k, v in params.items() if v is not None and str(v).strip() != ""}
        if "min_likelihood" not in clean:
            clean["min_likelihood"] = self._min_likelihood
        url = f"{self._base}/v5/person/enrich"
        r = requests.get(url, headers=self._headers(), params=clean, timeout=self._timeout)
        text = r.text or ""
        if r.status_code == 404:
            return None
        if not r.ok:
            raise PdlApiError(r.status_code, text)
        if not text.strip():
            return None
        data = r.json()
        return data if isinstance(data, dict) else None

    def person_search(
        self,
        *,
        sql: str | None = None,
        query: dict[str, Any] | None = None,
        size: int = 5,
    ) -> dict[str, Any]:
        """POST /v5/person/search — SQL o Elasticsearch DSL."""
        body: dict[str, Any] = {"size": min(max(size, 1), 100)}
        if sql:
            body["sql"] = sql
        elif query:
            body["query"] = query
        else:
            raise ValueError("person_search requiere sql o query")
        url = f"{self._base}/v5/person/search"
        r = requests.post(url, headers=self._headers(), json=body, timeout=self._timeout)
        text = r.text or ""
        if not r.ok:
            raise PdlApiError(r.status_code, text)
        data = r.json()
        return data if isinstance(data, dict) else {}

    def check_access(self) -> dict[str, Any]:
        """Comprueba clave: 404 en enrich de prueba = clave válida."""
        result: dict[str, Any] = {
            "api_reachable": True,
            "enrich_access": False,
            "search_access": False,
            "errors": [],
        }
        try:
            match = self.person_enrich({"email": "pdl-healthcheck-invalid@example.com"})
            result["enrich_access"] = True
            result["test_match"] = match is not None
        except PdlApiError as e:
            result["errors"].append({"endpoint": "person/enrich", "http_status": e.status, **e.parsed()})

        try:
            data = self.person_search(
                sql="SELECT * FROM person WHERE job_company_name='People Data Labs'",
                size=1,
            )
            result["search_access"] = isinstance(data.get("data"), list)
            result["search_total_sample"] = data.get("total")
        except PdlApiError as e:
            result["errors"].append({"endpoint": "person/search", "http_status": e.status, **e.parsed()})

        return result
