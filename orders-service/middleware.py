"""
middleware.py - Patrones de Resiliencia: Rate Limiting, Circuit Breaker y Retry with Backoff
LAB 11: Rate Limiting + Circuit Breaker
orders-service/middleware.py
"""

import time
from collections import defaultdict
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
import asyncio
import httpx
import logging

logger = logging.getLogger("orders-service.middleware")


# ─── 2. RATE LIMITER: Limitar las solicitudes ──────────────────────────────
class RateLimiter:
    """
    Controlador de tasa de solicitudes por IP utilizando una ventana deslizante en memoria.
    Evita que una misma dirección IP realice demasiadas solicitudes en un periodo determinado.
    """
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)

    def is_allowed(self, client_id: str) -> bool:
        """
        Comprueba si la solicitud del cliente está permitida dentro de la ventana de tiempo.
        1. Obtiene la hora actual.
        2. Elimina marcas de tiempo con antigüedad superior a window_seconds.
        3. Comprueba si se alcanzó el límite max_requests.
        4. Si está dentro del límite, registra la solicitud actual y retorna True.
        """
        now = time.time()
        # Conservar únicamente las solicitudes realizadas dentro de la ventana de control
        self.requests[client_id] = [
            req_time for req_time in self.requests[client_id]
            if now - req_time < self.window_seconds
        ]

        # Si ya alcanzó el límite de solicitudes, bloquear la nueva solicitud
        if len(self.requests[client_id]) >= self.max_requests:
            return False

        # Registrar la solicitud y permitirla
        self.requests[client_id].append(now)
        return True

    def get_remaining(self, client_id: str) -> int:
        """Retorna la cantidad de solicitudes disponibles restantes para el cliente."""
        now = time.time()
        active = [
            req_time for req_time in self.requests[client_id]
            if now - req_time < self.window_seconds
        ]
        return max(0, self.max_requests - len(active))


# Instancia global del Rate Limiter (100 solicitudes cada 60 segundos por IP)
rate_limiter = RateLimiter(max_requests=100, window_seconds=60)


async def rate_limit_middleware(request: Request, call_next):
    """
    Middleware HTTP de FastAPI para interceptar cada petición y aplicar el Rate Limiter.
    - Identifica la IP del cliente (request.client.host).
    - Si supera el límite permitido, devuelve HTTP 429 con cabecera Retry-After.
    - Si está permitida, continúa hacia el endpoint y devuelve la respuesta.
    """
    # Excluir rutas de documentación para facilitar el uso interactivo de Swagger
    path = request.url.path
    if path in ["/docs", "/openapi.json", "/redoc"]:
        return await call_next(request)

    client_ip = request.client.host if request.client else "127.0.0.1"

    if not rate_limiter.is_allowed(client_ip):
        logger.warning(f"RateLimiter: IP {client_ip} excedió el límite de {rate_limiter.max_requests} req / {rate_limiter.window_seconds}s")
        return JSONResponse(
            status_code=429,
            content={"error": "Too many requests"},
            headers={
                "Retry-After": str(rate_limiter.window_seconds),
                "X-RateLimit-Limit": str(rate_limiter.max_requests),
                "X-RateLimit-Remaining": "0"
            }
        )

    response = await call_next(request)
    # Inyectar cabeceras informativas de Rate Limit en la respuesta
    response.headers["X-RateLimit-Limit"] = str(rate_limiter.max_requests)
    response.headers["X-RateLimit-Remaining"] = str(rate_limiter.get_remaining(client_ip))
    return response


# ─── 3. CIRCUIT BREAKER: Proteger servicios externos ───────────────────────
class CircuitBreaker:
    """
    Patrón Circuit Breaker para evitar sobrecargar servicios externos que fallan.
    Maneja tres estados:
    - CLOSED (Cerrado): Funcionamiento normal, peticiones permitidas.
    - OPEN (Abierto): Servicio bloqueado por superar el umbral de fallos.
    - HALF_OPEN (Semiabierto): Prueba de recuperación para validar si el servicio se restableció.
    """
    STATE_CLOSED = "closed"
    STATE_OPEN = "open"
    STATE_HALF_OPEN = "half_open"

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = self.STATE_CLOSED

    def can_execute(self) -> bool:
        """
        Determina si se permite realizar una llamada al servicio externo.
        - CLOSED: Permite la llamada directamente.
        - OPEN: Comprueba si transcurrió recovery_timeout. Si transcurrió, pasa a HALF_OPEN y permite prueba;
                si no ha transcurrido, bloquea la llamada (retorna False).
        - HALF_OPEN: Permite la llamada de prueba de recuperación.
        """
        now = time.time()
        if self.state == self.STATE_CLOSED:
            return True

        if self.state == self.STATE_OPEN:
            if now - self.last_failure_time > self.recovery_timeout:
                logger.info(f"CircuitBreaker: Transcurrido tiempo de recuperación ({self.recovery_timeout}s) -> Pasando a {self.STATE_HALF_OPEN}")
                self.state = self.STATE_HALF_OPEN
                return True
            return False

        if self.state == self.STATE_HALF_OPEN:
            return True

        return True

    def record_success(self):
        """
        Registra una respuesta exitosa del servicio externo:
        - Reinicia el contador de errores.
        - Cierra el circuito (STATE_CLOSED).
        """
        self.failure_count = 0
        self.state = self.STATE_CLOSED
        logger.info("CircuitBreaker: Éxito registrado. Circuito en estado CLOSED.")

    def record_failure(self):
        """
        Registra un fallo en la llamada al servicio externo:
        - Incrementa el contador de fallos.
        - Actualiza la marca de tiempo del último fallo.
        - Si alcanza o supera el umbral de fallos, abre el circuito (STATE_OPEN).
        """
        self.failure_count += 1
        self.last_failure_time = time.time()
        logger.warning(f"CircuitBreaker: Fallo #{self.failure_count}/{self.failure_threshold} registrado.")

        if self.failure_count >= self.failure_threshold:
            self.state = self.STATE_OPEN
            logger.error(f"CircuitBreaker: Umbral de {self.failure_threshold} fallos alcanzado -> Circuito abierto (OPEN).")

    def get_status(self) -> dict:
        """Retorna telemetría del estado actual del circuito."""
        return {
            "state": self.state,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "last_failure_time": self.last_failure_time,
            "is_available": self.can_execute()
        }


# Instancia global del Circuit Breaker para el servicio de catálogo (5 fallos, 60s de recuperación)
catalog_circuit = CircuitBreaker(
    failure_threshold=5,
    recovery_timeout=60
)


async def call_catalog_with_breaker(url: str) -> dict:
    """
    Conecta la aplicación con el servicio externo 'catalog-service' protegido por el Circuit Breaker.
    - Si el circuito está abierto, devuelve error HTTP 503 sin intentar la conexión.
    - Si está permitido, realiza una petición HTTP esperando máximo 5 segundos.
    - Si responde correctamente (HTTP 200), registra éxito y devuelve los datos en JSON.
    - Si falla o expira, registra el error y devuelve respuesta HTTP 503.
    """
    if not catalog_circuit.can_execute():
        logger.warning(f"call_catalog_with_breaker: Circuito abierto. Bloqueando llamada a {url}")
        raise HTTPException(
            status_code=503,
            detail="Service Unavailable: Circuit breaker is OPEN"
        )

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                catalog_circuit.record_success()
                return response.json()
            elif response.status_code == 404:
                # 404 es una respuesta normal de negocio (recurso no existe), no un fallo del servicio
                raise HTTPException(
                    status_code=404,
                    detail=f"Resource not found at {url}"
                )
            else:
                logger.warning(f"call_catalog_with_breaker: Respuesta HTTP anormal {response.status_code} desde {url}")
                catalog_circuit.record_failure()
                raise HTTPException(
                    status_code=503,
                    detail=f"Service Unavailable: Catalog returned status {response.status_code}"
                )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"call_catalog_with_breaker: Excepción al consultar catálogo: {exc}")
        catalog_circuit.record_failure()
        raise HTTPException(
            status_code=503,
            detail=f"Service Unavailable: {str(exc)}"
        ) from exc


# ─── 4. RETRY WITH BACKOFF: Reintentar operaciones ─────────────────────────
async def retry_with_backoff(
    func,
    max_retries: int = 3,
    base_delay: float = 1.0
):
    """
    Ejecuta una función asíncrona reintentándola progresivamente en caso de fallos.
    - max_retries: Máximo 3 intentos por defecto.
    - base_delay: Espera inicial de 1.0 segundo.
    - Tiempo de espera exponencial: base_delay * (2 ** attempt) -> 1s, 2s.
    - Si todos los intentos fallan, relanza la última excepción capturada.
    """
    last_exception = None

    for attempt in range(max_retries):
        try:
            return await func()
        except Exception as e:
            last_exception = e
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.warning(f"Retry {attempt + 1}/{max_retries} after {delay}s: {str(e)}")
                print(f"Retry {attempt + 1}/{max_retries} after {delay}s: {str(e)}")
                await asyncio.sleep(delay)

    raise last_exception

