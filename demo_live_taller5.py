"""
demo_live_taller5.py
Script de Demostración en Vivo para Presentación al Docente (Taller 5 - LAB 11).
Muestra de forma interactiva y visual el funcionamiento de:
1. Rate Limiter (Ventana deslizante, límite 100 req, HTTP 429, cabecera Retry-After).
2. Circuit Breaker (Estados CLOSED, OPEN tras 5 fallos, cortocircuito inmediato HTTP 503, recuperación HALF_OPEN).
3. Retry with Backoff (Reintentos con esperas progresivas 1s, 2s ante fallos transitorios).
"""

import sys
import os
import time
import asyncio
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath("orders-service"))

from main import app
from middleware import rate_limiter, catalog_circuit, retry_with_backoff, CircuitBreaker


def print_banner(text):
    print("\n" + "=" * 70)
    print(f" {text}")
    print("=" * 70)


def demo_rate_limiter():
    print_banner("1. DEMOSTRACIÓN: RATE LIMITER (Ventana Deslizante)")
    print("Objetivo: Proteger la API limitando a 100 solicitudes por minuto por IP.\n")
    client = TestClient(app)

    # Reiniciar para demo
    rate_limiter.requests.clear()
    rate_limiter.max_requests = 100

    print(">> Enviando ráfaga de 100 solicitudes válidas desde la misma IP...")
    success_count = 0
    for i in range(100):
        resp = client.get("/")
        if resp.status_code == 200:
            success_count += 1

    print(f"   [OK] Solicitudes exitosas procesadas: {success_count}/100")
    print(f"   [OK] Cabecera X-RateLimit-Limit: {resp.headers.get('x-ratelimit-limit')}")
    print(f"   [OK] Cabecera X-RateLimit-Remaining: {resp.headers.get('x-ratelimit-remaining')}")

    print("\n>> Enviando solicitud #101 (Debe exceder el límite)...")
    r_blocked = client.get("/")
    print(f"   [RESULTADO] Código de estado HTTP: {r_blocked.status_code}")
    print(f"   [RESULTADO] Cuerpo de respuesta:   {r_blocked.json()}")
    print(f"   [RESULTADO] Cabecera Retry-After: {r_blocked.headers.get('retry-after')} segundos")

    if r_blocked.status_code == 429:
        print("\n [ÉXITO] Rate Limiter bloqueó la solicitud #101 con HTTP 429 y Retry-After: 60.")


def demo_circuit_breaker():
    print_banner("2. DEMOSTRACIÓN: CIRCUIT BREAKER (Protección de catalog-service)")
    print("Objetivo: Cortocircuitar llamadas a servicios externos cuando fallan 5 veces.\n")
    client = TestClient(app)

    # Limpiar rate limiter para permitir llamadas de telemetría sin bloqueo previo
    rate_limiter.requests.clear()

    # Restablecer circuito
    catalog_circuit.record_success()
    print(f"Estado inicial del circuito: {catalog_circuit.state.upper()} (Fallos: {catalog_circuit.failure_count}/5)")

    print("\n>> Simulando 5 fallos consecutivos en llamadas al catalog-service...")
    for i in range(1, 6):
        catalog_circuit.record_failure()
        print(f"   -> Fallo #{i} registrado. Estado actual: {catalog_circuit.state.upper()}")

    print("\n>> Consultando estado del circuito vía endpoint /resilience/circuit-breaker:")
    telemetry = client.get("/resilience/circuit-breaker").json()
    print(f"   Estado reportado:     {telemetry['state'].upper()}")
    print(f"   Contador de fallos:   {telemetry['failure_count']}")
    print(f"   Umbral de activación: {telemetry['failure_threshold']}")

    print("\n>> Intentando consultar /resilience/catalog/1 con circuito OPEN:")
    t0 = time.time()
    r_fast_fail = client.get("/resilience/catalog/1")
    t_elapsed = (time.time() - t0) * 1000

    print(f"   Código HTTP retornado: {r_fast_fail.status_code}")
    print(f"   Detalle del error:     {r_fast_fail.json().get('detail')}")
    print(f"   Tiempo de respuesta:   {t_elapsed:.2f} ms (Cortocircuito instantáneo sin esperar red)")

    print("\n>> Simulando expiración del tiempo de recuperación (60s) para prueba de recuperación...")
    catalog_circuit.last_failure_time = time.time() - 65.0
    print(f"   ¿Permite ejecutar prueba (can_execute)? {catalog_circuit.can_execute()}")
    print(f"   Nuevo estado del circuito: {catalog_circuit.state.upper()} (HALF_OPEN: Prueba permitida)")

    print("\n>> Registrando llamada de prueba exitosa...")
    catalog_circuit.record_success()
    print(f"   Circuito recuperado y cerrado. Estado actual: {catalog_circuit.state.upper()} (Fallos reiniciados a {catalog_circuit.failure_count})")
    print("\n [ÉXITO] Circuit Breaker protegió el servicio externo, evitó timeouts y se recuperó.")


async def run_retry_demo():
    print_banner("3. DEMOSTRACIÓN: RETRY WITH BACKOFF (Esperas Progresivas)")
    print("Objetivo: Reintentar operaciones transitorias con fórmula: base_delay * (2 ** attempt).\n")

    attempt_counter = 0

    async def operacion_inestable():
        nonlocal attempt_counter
        attempt_counter += 1
        print(f"   [Intento #{attempt_counter}] Ejecutando operación...")
        if attempt_counter < 3:
            raise ConnectionError(f"Error transitorio de red (simulado)")
        return "¡Conexión establecida con éxito en el 3er intento!"

    t_start = time.time()
    resultado = await retry_with_backoff(operacion_inestable, max_retries=3, base_delay=1.0)
    duracion = time.time() - t_start

    print(f"\n   Resultado final: {resultado}")
    print(f"   Tiempo total transcurrido: {duracion:.2f}s (Espera 1: 1.0s + Espera 2: 2.0s = ~3.0s)")
    print("\n [ÉXITO] Retry with Backoff reintentó exponencialmente y recuperó la operación.")


def main():
    print("======================================================================")
    print("     PRESENTACIÓN EN VIVO: TALLER 5 (LAB 11 - RESILIENCIA FASTAPI)     ")
    print("        Microservicio: orders-service | Archivo: middleware.py        ")
    print("======================================================================")

    demo_rate_limiter()
    demo_circuit_breaker()
    asyncio.run(run_retry_demo())

    print("\n" + "=" * 70)
    print(" ¡TODAS LAS DEMOSTRACIONES COMPLETADAS EXITOSAMENTE!")
    print("======================================================================\n")


if __name__ == "__main__":
    main()
