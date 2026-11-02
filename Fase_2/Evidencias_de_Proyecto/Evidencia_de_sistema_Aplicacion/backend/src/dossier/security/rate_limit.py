"""
Limitación de tasa (S5.8).

Ventana deslizante en memoria del proceso. Basta porque la API corre con un solo proceso
(``docker-entrypoint.sh``: ``--workers 1``, a propósito por los trabajadores en segundo
plano). Con varios procesos habría que mover los contadores a Redis.

Tres límites, configurables con ``N/S`` (N peticiones cada S segundos) u ``off``:

- ``AUTH_RATE_LIMIT`` (20/60 por omisión): por IP, en las rutas de autenticación
  (inicio de sesión, registro, renovación, recuperación y Google). Frena la fuerza bruta.
- ``LOGIN_FAILURE_RATE_LIMIT`` (5/300): inicios de sesión **fallidos** por correo. Frena
  probar contraseñas contra una cuenta desde muchas IP. Un inicio correcto los limpia.
- ``GENERATION_RATE_LIMIT`` (10/60): por usuario, en la generación de dossiers. Evita
  gastar créditos y cuota de proveedores externos en ráfaga.

Al superar el límite la API responde **429** con ``Retry-After`` y ``detail.code =
"rate_limited"``. Un rechazo no cuenta como petición: quien insiste sale del bloqueo
cuando la ventana avanza.
"""
from __future__ import annotations

import hashlib
import ipaddress
import math
import os
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Header, HTTPException, Request
from jwt.exceptions import PyJWTError

from dossier.security.jwt_tokens import decode_access_token


@dataclass(frozen=True)
class Limit:
    max_requests: int
    window_seconds: int


def _reloj() -> float:
    return time.monotonic()


def parse_limit(raw: str | None, default: Limit) -> Limit | None:
    """``"N/S"`` → ``Limit(N, S)``; ``"off"`` o ``0`` → ``None`` (sin límite); inválido → ``default``."""
    if raw is None:
        return default
    texto = raw.strip().lower()
    if texto in ("off", "0"):
        return None
    partes = texto.split("/")
    if len(partes) != 2:
        return default
    try:
        n, s = int(partes[0].strip()), int(partes[1].strip())
    except ValueError:
        return default
    if n == 0:
        return None
    if n < 0 or s <= 0:
        return default
    return Limit(n, s)


def limit_from_env(nombre: str, default: Limit) -> Limit | None:
    return parse_limit(os.getenv(nombre), default)


class SlidingWindowLimiter:
    """Registro de instantes por clave; seguro entre hilos."""

    def __init__(
        self,
        limit: Callable[[], Limit | None],
        *,
        clock: Callable[[], float] | None = None,
        max_keys: int = 50_000,
    ) -> None:
        self._limit = limit
        self._clock = clock or (lambda: _reloj())
        self._max_keys = max_keys
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _vigentes(self, clave: str, ahora: float, ventana: int) -> deque[float]:
        cola = self._hits.get(clave)
        if cola is None:
            return deque()
        while cola and cola[0] <= ahora - ventana:
            cola.popleft()
        if not cola:
            self._hits.pop(clave, None)
        return cola

    def _espera(self, cola: deque[float], ahora: float, limite: Limit) -> int | None:
        if len(cola) < limite.max_requests:
            return None
        return max(1, math.ceil(cola[0] + limite.window_seconds - ahora))

    def check(self, clave: str) -> int | None:
        """Segundos de espera si la clave está bloqueada; ``None`` si puede pasar. No registra."""
        limite = self._limit()
        if limite is None:
            return None
        with self._lock:
            ahora = self._clock()
            return self._espera(self._vigentes(clave, ahora, limite.window_seconds), ahora, limite)

    def hit(self, clave: str) -> int | None:
        """Registra una petición. Devuelve los segundos de espera si se rechaza (y no la registra)."""
        limite = self._limit()
        if limite is None:
            return None
        with self._lock:
            ahora = self._clock()
            cola = self._vigentes(clave, ahora, limite.window_seconds)
            espera = self._espera(cola, ahora, limite)
            if espera is not None:
                return espera
            if clave not in self._hits:
                if len(self._hits) >= self._max_keys:
                    self._podar()
                self._hits[clave] = cola
            cola.append(ahora)
            return None

    def _podar(self) -> None:
        # Descarta la mitad más antigua (los dict conservan el orden de inserción).
        for clave in list(self._hits)[: max(1, len(self._hits) // 2)]:
            del self._hits[clave]

    def clear(self, clave: str) -> None:
        with self._lock:
            self._hits.pop(clave, None)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def key_count(self) -> int:
        with self._lock:
            return len(self._hits)


AUTH_LIMITER = SlidingWindowLimiter(lambda: limit_from_env("AUTH_RATE_LIMIT", Limit(20, 60)))
LOGIN_FAILURE_LIMITER = SlidingWindowLimiter(lambda: limit_from_env("LOGIN_FAILURE_RATE_LIMIT", Limit(5, 300)))
GENERATION_LIMITER = SlidingWindowLimiter(lambda: limit_from_env("GENERATION_RATE_LIMIT", Limit(10, 60)))


def reset_all() -> None:
    for limitador in (AUTH_LIMITER, LOGIN_FAILURE_LIMITER, GENERATION_LIMITER):
        limitador.reset()


def email_key(correo: str) -> str:
    """Clave por correo sin guardarlo en claro (y sin distinguir mayúsculas)."""
    return "correo:" + hashlib.sha256(correo.strip().lower().encode("utf-8")).hexdigest()


def client_ip(request: Request) -> str:
    """IP de la conexión. Detrás de Caddy, uvicorn ``--proxy-headers`` ya la corrige;
    la cabecera ``X-Forwarded-For`` del cliente no se lee aquí (se podría falsear)."""
    host = request.client.host if request.client else ""
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        return host or "desconocida"


def too_many_requests(espera: int) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail={
            "code": "rate_limited",
            "message": f"Demasiadas solicitudes. Intenta de nuevo en {espera} segundos.",
            "retry_after": espera,
        },
        headers={"Retry-After": str(espera)},
    )


def limit_auth(request: Request) -> None:
    """Dependencia: límite por IP en las rutas de autenticación."""
    espera = AUTH_LIMITER.hit(f"ip:{client_ip(request)}")
    if espera is not None:
        raise too_many_requests(espera)


def limit_generation(request: Request, authorization: str | None = Header(default=None)) -> None:
    """Dependencia: límite por usuario (o por IP si el token no es válido) en la generación."""
    clave = f"ip:{client_ip(request)}"
    if authorization and authorization.lower().startswith("bearer "):
        try:
            sub = decode_access_token(authorization[7:].strip()).get("sub")
            if isinstance(sub, str) and sub:
                clave = f"usuario:{sub}"
        except (PyJWTError, RuntimeError, ValueError):
            pass
    espera = GENERATION_LIMITER.hit(clave)
    if espera is not None:
        raise too_many_requests(espera)
