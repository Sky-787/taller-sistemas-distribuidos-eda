"""
test_taller5_resilience.py
Suite de pruebas automatizadas completas para el Taller 5:
- LAB 11: Rate Limiting + Circuit Breaker + Retry with Backoff
- Verificación exhaustiva de middleware.py en orders-service
- Pruebas unitarias de clases y funciones
- Pruebas de integración con la API FastAPI
"""

import os
import sys
import time
import asyncio
import unittest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

# Asegurar path para importar orders-service
sys.path.insert(0, os.path.abspath("orders-service"))

from middleware import (
    RateLimiter,
    rate_limiter,
    CircuitBreaker,
    catalog_circuit,
    call_catalog_with_breaker,
    retry_with_backoff,
    rate_limit_middleware
)
from main import app
from fastapi import HTTPException


class TestTaller5Resilience(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        """Reinicia los estados antes de cada prueba unitaria."""
        # Reiniciar rate_limiter global
        rate_limiter.requests.clear()
        # Reiniciar catalog_circuit global
        catalog_circuit.record_success()

    # ─── 1. PRUEBAS DEL RATE LIMITER (Punto 2) ─────────────────────────
    def test_01_rate_limiter_initialization(self):
        """Verifica que la clase RateLimiter inicializa con 100 req y 60s por defecto."""
        rl = RateLimiter()
        self.assertEqual(rl.max_requests, 100)
        self.assertEqual(rl.window_seconds, 60)
        self.assertIsNotNone(rl.requests)
        print(" [PASS] 1. RateLimiter inicializa correctamente con 100 req / 60s")

    def test_02_rate_limiter_allows_under_limit(self):
        """Verifica que solicitudes bajo el límite son permitidas (is_allowed -> True)."""
        rl = RateLimiter(max_requests=5, window_seconds=60)
        client_ip = "192.168.1.10"

        for i in range(5):
            allowed = rl.is_allowed(client_ip)
            self.assertTrue(allowed, f"Solicitud #{i + 1} debió ser permitida")

        self.assertEqual(len(rl.requests[client_ip]), 5)
        print(" [PASS] 2. RateLimiter permite solicitudes dentro del umbral (5/5 permitidas)")

    def test_03_rate_limiter_blocks_exceeding_requests(self):
        """Verifica que al superar max_requests (p. ej. solicitud 101), la solicitud es bloqueada."""
        rl = RateLimiter(max_requests=3, window_seconds=60)
        client_ip = "192.168.1.10"

        self.assertTrue(rl.is_allowed(client_ip))
        self.assertTrue(rl.is_allowed(client_ip))
        self.assertTrue(rl.is_allowed(client_ip))
        # Solicitud 4 debe ser bloqueada
        self.assertFalse(rl.is_allowed(client_ip))
        print(" [PASS] 3. RateLimiter bloquea solicitud excedente (is_allowed -> False)")

    def test_04_rate_limiter_per_ip_isolation(self):
        """Verifica que cada dirección IP tiene un registro independiente (192.168.1.10 vs 192.168.1.20)."""
        rl = RateLimiter(max_requests=2, window_seconds=60)
        ip1 = "192.168.1.10"
        ip2 = "192.168.1.20"

        self.assertTrue(rl.is_allowed(ip1))
        self.assertTrue(rl.is_allowed(ip1))
        self.assertFalse(rl.is_allowed(ip1))  # IP1 agotada

        # IP2 debe seguir teniendo cupo completo
        self.assertTrue(rl.is_allowed(ip2))
        self.assertTrue(rl.is_allowed(ip2))
        self.assertFalse(rl.is_allowed(ip2))
        print(" [PASS] 4. Aislamiento independiente por dirección IP verificado")

    def test_05_rate_limiter_sliding_window_cleanup(self):
        """Verifica la limpieza de solicitudes antiguas fuera de la ventana de 60 segundos."""
        rl = RateLimiter(max_requests=2, window_seconds=2)
        ip = "10.0.0.1"

        # Simular dos solicitudes en el pasado (hace 3 segundos)
        past_time = time.time() - 3.0
        rl.requests[ip] = [past_time, past_time]

        # Al llamar is_allowed, debe limpiar las solicitudes viejas y permitir la nueva
        self.assertTrue(rl.is_allowed(ip))
        self.assertEqual(len(rl.requests[ip]), 1)
        print(" [PASS] 5. Ventana deslizante limpia solicitudes expiradas y restaura cupo")

    # ─── 2. PRUEBAS DEL CIRCUIT BREAKER (Punto 3) ──────────────────────
    def test_06_circuit_breaker_initial_state(self):
        """Verifica que el CircuitBreaker inicia en estado CLOSED, con umbral 5 y timeout 60s."""
        cb = CircuitBreaker()
        self.assertEqual(cb.state, CircuitBreaker.STATE_CLOSED)
        self.assertEqual(cb.failure_threshold, 5)
        self.assertEqual(cb.recovery_timeout, 60)
        self.assertEqual(cb.failure_count, 0)
        self.assertTrue(cb.can_execute())
        print(" [PASS] 6. CircuitBreaker inicia en estado 'closed' con umbral 5 y timeout 60s")

    def test_07_circuit_breaker_opens_after_five_failures(self):
        """Verifica que tras 5 fallos consecutivos, el circuito pasa de CLOSED a OPEN y bloquea llamadas."""
        cb = CircuitBreaker(failure_threshold=5, recovery_timeout=60)

        for i in range(4):
            cb.record_failure()
            self.assertEqual(cb.state, CircuitBreaker.STATE_CLOSED)
            self.assertTrue(cb.can_execute())

        # Quinto fallo consecutivo
        cb.record_failure()
        self.assertEqual(cb.state, CircuitBreaker.STATE_OPEN)
        self.assertFalse(cb.can_execute())
        print(" [PASS] 7. CircuitBreaker transiciona a 'open' al 5to fallo y bloquea ejecución")

    def test_08_circuit_breaker_half_open_recovery_transition(self):
        """Verifica que tras expirar el recovery_timeout, can_execute() transiciona a HALF_OPEN para prueba."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1)
        cb.record_failure()
        cb.record_failure()
        self.assertEqual(cb.state, CircuitBreaker.STATE_OPEN)
        self.assertFalse(cb.can_execute())

        # Simular que transcurrieron los segundos de recuperación
        cb.last_failure_time = time.time() - 2.0

        # Ahora can_execute() debe pasar a HALF_OPEN y permitir la prueba
        self.assertTrue(cb.can_execute())
        self.assertEqual(cb.state, CircuitBreaker.STATE_HALF_OPEN)
        print(" [PASS] 8. CircuitBreaker conmuta de 'open' a 'half_open' tras expirar recovery_timeout")

    def test_09_circuit_breaker_success_in_half_open_closes_circuit(self):
        """Verifica que un éxito en HALF_OPEN restablece el circuito a CLOSED y reinicia errores a cero."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60)
        cb.record_failure()
        cb.record_failure()
        cb.state = CircuitBreaker.STATE_HALF_OPEN

        # Registrar éxito en prueba
        cb.record_success()
        self.assertEqual(cb.state, CircuitBreaker.STATE_CLOSED)
        self.assertEqual(cb.failure_count, 0)
        self.assertTrue(cb.can_execute())
        print(" [PASS] 9. Éxito en 'half_open' cierra el circuito ('closed') y reinicia contador a 0")

    # ─── 3. PRUEBAS DE LLAMADA AL CATÁLOGO CON BREAKER (Punto 3.G) ────
    async def test_10_call_catalog_with_breaker_when_open_raises_503(self):
        """Verifica que si el circuito está OPEN, call_catalog_with_breaker rechaza con 503 sin llamar a la red."""
        catalog_circuit.state = CircuitBreaker.STATE_OPEN
        catalog_circuit.last_failure_time = time.time()

        with self.assertRaises(HTTPException) as ctx:
            await call_catalog_with_breaker("http://catalog-service:8001/spaces/1")

        self.assertEqual(ctx.exception.status_code, 503)
        self.assertIn("Circuit breaker is OPEN", ctx.exception.detail)
        print(" [PASS] 10. call_catalog_with_breaker retorna HTTP 503 inmediato cuando el circuito está OPEN")

    async def test_11_call_catalog_with_breaker_success(self):
        """Verifica que una respuesta exitosa (200) registra éxito y retorna datos JSON."""
        import httpx
        mock_response = httpx.Response(200, json={"id": 1, "name": "Espacio Demo", "hourly_rate": 20.0})

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            data = await call_catalog_with_breaker("http://catalog-service:8001/spaces/1")

        self.assertEqual(data["id"], 1)
        self.assertEqual(catalog_circuit.state, CircuitBreaker.STATE_CLOSED)
        self.assertEqual(catalog_circuit.failure_count, 0)
        print(" [PASS] 11. call_catalog_with_breaker procesa respuesta HTTP 200 y registra éxito")

    async def test_12_call_catalog_with_breaker_failure_records_error_and_returns_503(self):
        """Verifica que una falla de red o error HTTP registra fallo y levanta HTTP 503."""
        with patch("httpx.AsyncClient.get", side_effect=Exception("Conexión rehusada")):
            with self.assertRaises(HTTPException) as ctx:
                await call_catalog_with_breaker("http://catalog-service:8001/spaces/99")

        self.assertEqual(ctx.exception.status_code, 503)
        self.assertEqual(catalog_circuit.failure_count, 1)
        print(" [PASS] 12. call_catalog_with_breaker captura fallo de red, incrementa errores y lanza 503")

    # ─── 4. PRUEBAS DE RETRY WITH BACKOFF (Punto 4) ────────────────────
    async def test_13_retry_with_backoff_success_first_try(self):
        """Verifica que si la función tiene éxito en el primer intento, retorna de inmediato sin esperar."""
        calls = 0

        async def successful_operation():
            nonlocal calls
            calls += 1
            return "resultado_ok"

        res = await retry_with_backoff(successful_operation, max_retries=3, base_delay=0.01)
        self.assertEqual(res, "resultado_ok")
        self.assertEqual(calls, 1)
        print(" [PASS] 13. retry_with_backoff retorna inmediatamente si el primer intento tiene éxito")

    async def test_14_retry_with_backoff_transient_failure_then_success(self):
        """Verifica que reintenta con backoff y recupera si la operación falla inicialmente."""
        calls = 0

        async def flaky_operation():
            nonlocal calls
            calls += 1
            if calls < 2:
                raise ConnectionResetError("Fallo temporal de conexión")
            return "recuperado"

        t_start = time.time()
        res = await retry_with_backoff(flaky_operation, max_retries=3, base_delay=0.05)
        elapsed = time.time() - t_start

        self.assertEqual(res, "recuperado")
        self.assertEqual(calls, 2)
        self.assertGreaterEqual(elapsed, 0.04)  # Esperó al menos base_delay * (2 ** 0) = 0.05s
        print(" [PASS] 14. retry_with_backoff reintenta con retardo progresivo y resuelve éxito en intento #2")

    async def test_15_retry_with_backoff_exhausts_and_raises_last_exception(self):
        """Verifica que tras agotar los 3 intentos, relanza el último error capturado."""
        calls = 0

        async def failing_operation():
            nonlocal calls
            calls += 1
            raise TimeoutError(f"Timeout en intento #{calls}")

        with self.assertRaises(TimeoutError) as ctx:
            await retry_with_backoff(failing_operation, max_retries=3, base_delay=0.01)

        self.assertEqual(calls, 3)
        self.assertIn("Timeout en intento #3", str(ctx.exception))
        print(" [PASS] 15. retry_with_backoff ejecuta 3 intentos y relanza la última excepción")

    # ─── 5. PRUEBAS DE INTEGRACIÓN FASTAPI (Puntos 2.C, 3.F, 5) ────────
    def test_16_fastapi_rate_limiter_middleware_http_429(self):
        """
        Verifica el middleware registrado en FastAPI:
        - Si supera el límite permitido, devuelve HTTP 429.
        - Cuerpo JSON: {"error": "Too many requests"}.
        - Cabecera: Retry-After: "60".
        """
        client = TestClient(app)
        # Configurar límite bajo temporalmente para probar HTTP 429
        rate_limiter.max_requests = 2
        rate_limiter.window_seconds = 60

        r1 = client.get("/")
        self.assertEqual(r1.status_code, 200)

        r2 = client.get("/")
        self.assertEqual(r2.status_code, 200)

        # 3ra solicitud excede el límite
        r3 = client.get("/")
        self.assertEqual(r3.status_code, 429)
        self.assertEqual(r3.json(), {"error": "Too many requests"})
        self.assertEqual(r3.headers.get("retry-after"), "60")
        print(" [PASS] 16. Middleware FastAPI bloquea con HTTP 429, error JSON y cabecera Retry-After: 60")

    def test_17_fastapi_resilience_endpoints_integration(self):
        """Verifica la respuesta de los endpoints de resiliencia del Taller 5."""
        client = TestClient(app)
        rate_limiter.max_requests = 100

        # Endpoint /resilience/circuit-breaker
        r_cb = client.get("/resilience/circuit-breaker")
        self.assertEqual(r_cb.status_code, 200)
        data_cb = r_cb.json()
        self.assertIn("state", data_cb)
        self.assertIn("failure_threshold", data_cb)
        self.assertEqual(data_cb["failure_threshold"], 5)

        # Endpoint /resilience/rate-limiter
        r_rl = client.get("/resilience/rate-limiter")
        self.assertEqual(r_rl.status_code, 200)
        data_rl = r_rl.json()
        self.assertEqual(data_rl["max_requests"], 100)
        self.assertEqual(data_rl["window_seconds"], 60)

        # Endpoint /resilience/retry-demo
        r_retry = client.post("/resilience/retry-demo?fail_attempts=1&base_delay=0.01")
        self.assertEqual(r_retry.status_code, 200)
        self.assertEqual(r_retry.json()["status"], "success")
        self.assertEqual(r_retry.json()["attempts_needed"], 2)

        # Endpoint /resilience/circuit-breaker/reset
        r_reset = client.post("/resilience/circuit-breaker/reset")
        self.assertEqual(r_reset.status_code, 200)
        self.assertEqual(r_reset.json()["circuit_breaker"]["state"], "closed")
        print(" [PASS] 17. Endpoints de telemetría y resiliencia /resilience/* operando con éxito")


if __name__ == "__main__":
    unittest.main()
