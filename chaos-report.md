# Informe de Chaos Engineering

**Curso:** Sistemas Distribuidos / Arquitectura de Software  
**Proyecto:** Microservicios de Coworking con FastAPI y Docker Compose  
**Fecha:** 17 de Octubre de 2026  

---

## Test 1: Caída de servicio dependiente (Dependency Outage)

- **Escenario**:  
  Simulación de un fallo total no programado en el microservicio de catálogo (`catalog-service`). Estando el sistema en régimen normal, se procedió a detener forzosamente el contenedor mediante el comando `docker stop catalog-service`, mientras que el servicio dependiente (`orders-service`) continuó en ejecución. Posteriormente se intentó crear una orden de reserva a través de `POST /orders?space_id=1&user_email=chaos@example.com&hours=2`.

- **Impacto**:  
  - Las solicitudes entrantes que requerían validar y cotizar espacios con el catálogo no pudieron completarse.
  - Gracias al manejo de resiliencia implementado en `orders-service` con `httpx.AsyncClient` y la captura de `httpx.RequestError`, el microservicio de órdenes **no colapsó ni sufrió caídas en cascada**.
  - En lugar de generar un error indefinido o bloquear los hilos de ejecución, `orders-service` degradó su servicio de manera controlada y limpia, respondiendo al cliente con el código de estado estándar **`HTTP 503 Service Unavailable`** y el cuerpo:
    ```json
    {"detail": "Catalog service unavailable"}
    ```

- **Tiempo de detección**:  
  **Inmediato (< 20 ms)**. La red de Docker (`coworking-network`) notificó el rechazo inmediato de conexión (`ConnectionRefused` a nivel TCP), activando la captura de excepción de forma instantánea. Adicionalmente, se cuenta con un timeout estricto de 5.0 segundos como salvaguarda ante problemas de alta latencia.

- **Recuperación**:  
  - Al ejecutar `docker start catalog-service`, el contenedor reactivó el proceso Uvicorn en aproximadamente 2 a 3 segundos.
  - No fue necesario reiniciar ni alterar la configuración de `orders-service`.
  - La siguiente petición enviada retornó exitosamente **`HTTP 201 Created`** con la orden generada, evidenciando capacidades de auto-recuperación (self-healing) y desacoplamiento temporal adecuado.

---

## Test 2: Cambio de contrato sin versionar (API Contract Drift)

- **Escenario**:  
  Simulación de un despliegue inadvertido o independiente en `catalog-service` que introdujo un **Breaking Change** en la estructura del payload JSON. El equipo del catálogo renombró el atributo `price_per_hour` por `hourly_rate` sin comunicar el cambio ni actualizar la versión de la API. Se procedió a reconstruir el catálogo (`docker compose up --build -d`) y se intentó crear una orden desde `orders-service`.

- **Impacto**:  
  - Ambos microservicios reportan estado saludable (`GET /health` responde `200 OK` en los puertos 8001 y 8002).
  - La conectividad de red interna es totalmente funcional.
  - Sin embargo, las transacciones de negocio fallan consistentemente con **`HTTP 500 Internal Server Error`**:
    ```json
    {"detail": "Contract error: 'price_per_hour' field missing in catalog response"}
    ```
  - Este tipo de fallo es silencioso y peligroso porque pasa desapercibido ante health-checks superficiales de infraestructura.

- **Causa raíz**:  
  Violación del contrato sintáctico y semántico entre servicios. El consumidor (`orders-service`) dependía rígidamente del campo `space["price_per_hour"]` para efectuar el cálculo financiero de la reserva (`total_price = price_per_hour * hours`). Al no existir dicho campo en la respuesta deserializada, el consumidor no pudo procesar la lógica de negocio.

- **Solución propuesta**:  
  1. **Versionamiento explícito de API**: Implementar versionado por URL (ej. `/v1/spaces` y `/v2/spaces`) o por cabecera (`Accept: application/vnd.coworking.v1+json`). La versión 1 debe mantenerse activa hasta que todos los consumidores hayan migrado.
  2. **Tolerant Reader Pattern & Retrocompatibilidad**: Durante periodos de transición, el productor (`catalog-service`) debe serializar tanto el campo nuevo como el antiguo (`hourly_rate` y `price_per_hour` como alias).
  3. **Consumer-Driven Contract Testing (CDCT)**: Integrar herramientas como **Pact** en la pipeline de CI/CD para validar que ningún cambio en el proveedor rompa las expectativas pactadas con los consumidores antes de desplegar a producción.
  4. **Esquemas fuertemente tipados / OpenAPI / Protobuf**: Utilizar contratos tipados compartidos o especificaciones OpenAPI con validación automática de compatibilidad semántica.
