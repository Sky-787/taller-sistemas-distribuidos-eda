# Taller: Sistemas Distribuidos y Arquitectura de Software (UTP - TDS)
## Microservicios, Chaos Engineering y Migración Serverless Event-Driven (EDA)

Proyecto práctico completo que abarca desde la orquestación de microservicios síncronos con FastAPI y Docker Compose hasta la migración hacia una arquitectura desacoplada y resiliente basada en eventos y Serverless (AWS Lambda, EventBridge, SQS).

---

## 🏗️ Arquitectura del Sistema

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

---

## 📋 Estructura de Laboratorios

### Taller 1: Microservicios y Chaos Engineering
- **LAB 1**: Microservicio `catalog-service` con FastAPI (puerto 8001).
- **LAB 2**: Microservicio `orders-service` dependiente de catálogo (puerto 8002).
- **LAB 3**: Orquestación de contenedores con Docker Compose y red compartida.
- **LAB 4**: Chaos Engineering: simulación de caída de servicio dependiente.
- **LAB 5**: Chaos Engineering: ruptura de contrato API sin versionar.

### Taller 2: Serverless y Event-Driven Architecture (EDA)
- **LAB 6**: Función Serverless `catalog-service` con API Gateway y publicación de eventos `SpaceChanged` en Amazon EventBridge.
- **LAB 7**: Función Serverless Consumidora suscrita a Amazon SQS, desacoplamiento con `orders-service` mediante el patrón **Event-Carried State Transfer**, plantilla AWS SAM (`template.yaml`), suite de pruebas y despliegue.

---

## 🚀 Despliegue en Render (1-Click Blueprint)

El repositorio incluye [`render.yaml`](render.yaml) configurado para desplegar automáticamente los servicios en Render:

1. Ve a tu panel en [Render Dashboard](https://dashboard.render.com).
2. Selecciona **New +** > **Blueprint**.
3. Conecta este repositorio de GitHub.
4. Render desplegará automáticamente:
   - `orders-service-coworking` (con webhook de eventos y caché local).
   - `catalog-service-coworking` (API REST de espacios).

---

## ☁️ Despliegue en AWS (Serverless Application Model - SAM)

Para desplegar la arquitectura Serverless en AWS:

```bash
# 1. Compilar artefactos
sam build

# 2. Desplegar en AWS
sam deploy --guided
```

---

## 🧪 Pruebas Locales (Docker y Python)

### 1. Ejecutar con Docker Compose
```bash
docker-compose up --build -d
```
- Catálogo: `http://localhost:8001/spaces`
- Órdenes: `http://localhost:8002/orders`

### 2. Ejecutar la Suite de Pruebas Automatizadas
```bash
python test_serverless_pipeline.py
```
*(Valida el 100% de los 5 casos de prueba de la arquitectura Serverless)*

### 3. Simulación Interactiva en Consola
```bash
python scripts/simulate_event_flow.py
```

---

## 📄 Documentación Académica

- [Parte 2.docx](Parte%202.docx): Guía completa oficial del Taller 2 en formato Word.
- [PARTE_2.md](PARTE_2.md): Guía del Taller 2 en Markdown.
- [chaos-report.md](chaos-report.md): Informe técnico de los experimentos de Chaos Engineering.
- [AGENT.md](AGENT.md): Contexto técnico y checklist de entrega.
