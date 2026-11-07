"""
resilience.py - Patrones de Resiliencia: Circuit Breaker y Rate Limiting
Taller 4: Backend Avanzado FastAPI
"""

import time
import logging
from enum import Enum
from typing import Dict, Tuple, Optional
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger("orders-service.resilience")


# ─── 1. PATRÓN CIRCUIT BREAKER ─────────────────────────────────────
class CircuitState(str, Enum):
    CLOSED = "CLOSED"         # Normal: peticiones pasan al servicio
    OPEN = "OPEN"             # Circuito abierto: falla rápida al fallback
    HALF_OPEN = "HALF_OPEN"   # Prueba controlada: evalúa recuperación


class CircuitBreaker:
    """
    Implementación del patrón Circuit Breaker para llamadas a servicios externos.
    Evita sobrecargar dependencias caídas y redirige inmediatamente al fallback.
    """
    def __init__(self, failure_threshold: int = 3, recovery_time_seconds: float = 15.0):
        self.failure_threshold = failure_threshold
        self.recovery_time_seconds = recovery_time_seconds
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_state_change = time.time()
        self.last_failure_time: Optional[float] = None

    def can_execute(self) -> bool:
        """Determina si una llamada síncrona debe permitirse o cortocircuitarse."""
        now = time.time()
        if self.state == CircuitState.OPEN:
            if now - self.last_state_change >= self.recovery_time_seconds:
                logger.info("CircuitBreaker: Periodo de recuperación expirado -> Transicionando a HALF_OPEN")
                self.state = CircuitState.HALF_OPEN
                self.last_state_change = now
                return True
            return False
        return True

    def record_success(self):
        """Registra una llamada exitosa. Si estaba en HALF_OPEN, cierra el circuito."""
        self.failure_count = 0
        if self.state != CircuitState.CLOSED:
            logger.info("CircuitBreaker: Servicio recuperado con éxito -> Transicionando a CLOSED")
            self.state = CircuitState.CLOSED
            self.last_state_change = time.time()

    def record_failure(self):
        """Registra un fallo. Si excede el umbral, abre el circuito."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        logger.warning(f"CircuitBreaker: Fallo #{self.failure_count}/{self.failure_threshold} registrado")
        if self.failure_count >= self.failure_threshold and self.state != CircuitState.OPEN:
            logger.error("CircuitBreaker: Umbral de fallos superado -> Transicionando a OPEN (Cortocircuito)")
            self.state = CircuitState.OPEN
            self.last_state_change = time.time()

    def get_status(self) -> Dict[str, any]:
        """Retorna telemetría del estado actual del Circuit Breaker."""
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_time_seconds": self.recovery_time_seconds,
            "is_available": self.state != CircuitState.OPEN,
            "last_state_change": self.last_state_change,
            "last_failure_time": self.last_failure_time
        }


# Instancia global del Circuit Breaker para las llamadas al catalog-service
catalog_circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_time_seconds=15.0)


# ─── 2. PATRÓN RATE LIMITING ──────────────────────────────────────
class SlidingWindowRateLimiter:
    """
    Rate Limiter basado en ventana deslizante en memoria.
    Limita la cantidad de solicitudes permitidas por cliente en un intervalo de tiempo.
    """
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # cliente -> lista de timestamps
        self.requests: Dict[str, list] = {}

    def is_rate_limited(self, client_id: str) -> Tuple[bool, int, int]:
        """
        Evalúa si el cliente ha excedido la tasa permitida.
        Retorna (is_limited, remaining_requests, retry_after_seconds).
        """
        now = time.time()
        window_start = now - self.window_seconds

        # Limpiar marcas de tiempo fuera de la ventana
        timestamps = self.requests.get(client_id, [])
        valid_timestamps = [t for t in timestamps if t > window_start]

        if len(valid_timestamps) >= self.max_requests:
            oldest = valid_timestamps[0]
            retry_after = max(1, int(self.window_seconds - (now - oldest)))
            self.requests[client_id] = valid_timestamps
            return True, 0, retry_after

        valid_timestamps.append(now)
        self.requests[client_id] = valid_timestamps
        remaining = self.max_requests - len(valid_timestamps)
        return False, remaining, 0


# Instancia global: 60 peticiones por minuto por cliente/IP
rate_limiter = SlidingWindowRateLimiter(max_requests=60, window_seconds=60)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware de FastAPI para aplicar Rate Limiting automático a las rutas."""
    async def dispatch(self, request: Request, call_next):
        # Excluir rutas de salud y documentación de límites estrictos
        path = request.url.path
        if path in ["/health", "/docs", "/openapi.json", "/redoc"]:
            return await call_next(request)

        # Identificar al cliente por IP o Authorization header
        client_ip = request.client.host if request.client else "anonymous"
        auth_header = request.headers.get("Authorization", "")
        client_id = f"{client_ip}:{auth_header[:25]}" if auth_header else client_ip

        is_limited, remaining, retry_after = rate_limiter.is_rate_limited(client_id)

        if is_limited:
            logger.warning(f"RateLimitMiddleware: Límite excedido para {client_id}. Retry-After: {retry_after}s")
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": "Demasiadas solicitudes. Límite de tasa excedido (Rate Limit Exceeded).",
                    "retry_after_seconds": retry_after
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(rate_limiter.max_requests),
                    "X-RateLimit-Remaining": "0"
                }
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(rate_limiter.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response

