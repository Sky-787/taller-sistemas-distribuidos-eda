# Parte 2: Taller 2 - De Microservicios a Sistemas Distribuidos Inteligentes
## CLASE 3: Serverless - Migración Event-Driven (EDA)

---

### 1. Objetivo del Taller
Migrar el microservicio síncrono `catalog-service` hacia una arquitectura Serverless basada en **AWS Lambda** y **Amazon API Gateway**, publicando eventos en **Amazon EventBridge** ante cualquier cambio en la disponibilidad o tarifa de los espacios de coworking. A su vez, desacoplar `orders-service` permitiendo que consuma dichos eventos mediante **Amazon SQS** y una **Lambda Consumidora**, implementando el patrón **Event-Carried State Transfer** para garantizar resiliencia ante caídas y prevenir fallos en cascada (resolviendo las debilidades observadas en los Labs de Chaos Engineering del Taller 1).

---

### 2. Diagrama de Arquitectura

```
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│   API Gateway   │ ────> │     Lambda      │ ────> │   EventBridge   │
│    /spaces      │       │   catalog-fn    │       │  SpaceChanged   │
└─────────────────┘       └─────────────────┘       └─────────────────┘
                                                             │
                                                             ▼
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│ orders-service  │ <──── │     Lambda      │ <──── │    SQS Queue    │
│  (FastAPI/ECS)  │       │   consumer-fn   │       │ catalog-events  │
└─────────────────┘       └─────────────────┘       └─────────────────┘
```

#### Descripción del flujo:
1. **API Gateway (`/spaces`)**: Expone la interfaz REST pública para listar espacios y actualizar su disponibilidad.
2. **Lambda `catalog-fn`**: Procesa la lógica de negocio de catálogo de forma serverless.
3. **Amazon EventBridge (`SpaceChanged`)**: Recibe eventos cuando cambia la disponibilidad o tarifa de un espacio de coworking.
4. **Amazon SQS (`catalog-events`)**: Cola amortiguadora (buffer) que garantiza entrega desacoplada y cuenta con Dead Letter Queue (DLQ).
5. **Lambda `consumer-fn`**: Procesa los lotes de mensajes de SQS y notifica los cambios de estado.
6. **`orders-service`**: Mantiene una caché local alimentada por eventos (**Event-Carried State Transfer**), permitiendo operar incluso si el catálogo síncrono se cae.

---

### 3. LAB 6: Lambda `catalog-service`

#### Archivo: `lambda-catalog/requirements.txt`
```txt
boto3==1.34.0
```

#### Archivo: `lambda-catalog/handler.py`
Función Serverless encargada de:
- Atender peticiones `GET /spaces` y `GET /spaces/{id}`.
- Atender peticiones `PUT /spaces/{id}/availability`.
- Emitir el evento `SpaceChanged` hacia el bus de EventBridge cuando cambia el estado (`publish_space_changed_event`).

---

### 4. LAB 7: Consumer Lambda que recibe eventos

#### 4.1. Archivo: `lambda-consumer/requirements.txt`
```txt
boto3==1.34.0
httpx==0.25.2
```

#### 4.2. Archivo: `lambda-consumer/handler.py`
Función Serverless que:
- Se suscribe a la cola SQS `catalog-events`.
- Procesa lotes de mensajes con soporte para `ReportBatchItemFailures`.
- Invoca el webhook de sincronización en `orders-service` (`POST /events/space-changed`).

#### 4.3. Infraestructura como Código: `template.yaml` (AWS SAM)
Define de manera declarativa todos los recursos serverless requeridos:
- `CatalogApi`: API Gateway con CORS habilitado.
- `CatalogFunction`: Lambda `catalog-fn` con permisos para publicar en EventBridge (`events:PutEvents`).
- `CatalogEventsDLQ`: Dead Letter Queue para retener mensajes fallidos por hasta 14 días.
- `CatalogEventsQueue`: Cola SQS principal con reintentos configurados (`maxReceiveCount: 3`).
- `SpaceChangedRule`: Regla de EventBridge filtrada por `source: coworking.catalog` y `detail-type: SpaceChanged`.
- `ConsumerFunction`: Lambda `consumer-fn` conectada al Event Source Mapping de SQS.

#### 4.4. Resiliencia en `orders-service` (Event-Carried State Transfer)
En el Taller 1 (Lab 4 y 5), la caída del catálogo provocaba un error `HTTP 503` inmediato. En este laboratorio se implementa:
1. Webhook `POST /events/space-changed`: Sincroniza la caché local cada vez que la Lambda consumidora procesa un evento.
2. Endpoint `GET /catalog-cache`: Inspecciona los espacios cacheados en memoria.
3. Fallback Resiliente en `POST /orders`: Si el catálogo síncrono no responde, toma los datos del espacio desde la caché de eventos y emite la orden exitosamente (`HTTP 201 Created`).

#### 4.5. Guía de Despliegue en AWS (SAM CLI):
```bash
# 1. Construir artefactos
sam build

# 2. Despliegue guiado (primera vez)
sam deploy --guided

# 3. Despliegues subsiguientes
sam deploy
```

#### 4.6. Pruebas y Validación:
- **Suite automatizada (5/5 PASS):**
  ```bash
  python test_serverless_pipeline.py
  ```
- **Simulador interactivo por consola:**
  ```bash
  python scripts/simulate_event_flow.py
  ```
- **LocalStack & Docker Compose:**
  ```bash
  docker-compose -f docker-compose.serverless.yml up --build -d
  ```

---

### 5. Comparativa Arquitectónica

| Criterio | Taller 1: Microservicios Síncronos (Labs 1-5) | Taller 2: Serverless Event-Driven (Labs 6-7) |
| :--- | :--- | :--- |
| **Protocolo** | HTTP síncrono bloqueante | Eventos asíncronos en EventBridge + SQS |
| **Resiliencia** | Caída del catálogo = Caída de órdenes (503) | Desacoplamiento temporal; órdenes operan con caché |
| **Escalabilidad** | Escalado manual por contenedor | Escalado automático por petición (AWS Lambda) |
| **Costo** | Servidores 24/7 encendidos | Pay-per-use (Cero costo sin tráfico) |
