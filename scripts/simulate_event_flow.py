"""
scripts/simulate_event_flow.py
Demostración interactiva del flujo Serverless Event-Driven (Taller 2 / Parte 2).
Permite ejecutar el ciclo completo en terminal sin necesidad de desplegar en AWS real.
"""

import json
import time
import importlib.util
from pathlib import Path

# Cargar dinámicamente los módulos
catalog_spec = importlib.util.spec_from_file_location("catalog_handler", Path("lambda-catalog/handler.py").resolve())
catalog_handler = importlib.util.module_from_spec(catalog_spec)
catalog_spec.loader.exec_module(catalog_handler)

consumer_spec = importlib.util.spec_from_file_location("consumer_handler", Path("lambda-consumer/handler.py").resolve())
consumer_handler = importlib.util.module_from_spec(consumer_spec)
consumer_spec.loader.exec_module(consumer_handler)

def print_separator(title: str):
    print("\n" + "=" * 70)
    print(f" {title}")
    print("=" * 70)

def main():
    print_separator("TALLER 2: SIMULACIÓN DE ARQUITECTURA EVENT-DRIVEN SERVERLESS")
    print("Flujo: API Gateway -> Lambda catalog-fn -> EventBridge -> SQS -> Lambda consumer-fn -> orders-service")

    # PASO 1: Consulta inicial de espacios vía API Gateway
    print_separator("PASO 1: Consulta inicial de espacios vía API Gateway (/spaces)")
    event_get = {
        "httpMethod": "GET",
        "path": "/spaces",
        "headers": {}
    }
    resp_get = catalog_handler.lambda_handler(event_get, None)
    spaces = json.loads(resp_get["body"])
    print(f"Status Code: {resp_get['statusCode']}")
    print(f"Total de espacios en catálogo: {len(spaces)}")
    print(f"Espacio #1: {spaces[0]['name']} | Disponible: {spaces[0]['available']} | Tarifa: ${spaces[0]['price_per_hour']}/h")

    # PASO 2: Cambio de disponibilidad que dispara EventBridge
    print_separator("PASO 2: Actualización de disponibilidad en catalog-fn")
    print("Se actualiza Espacio #1: available = False (Reserva confirmada / mantenimiento)")
    event_put = {
        "httpMethod": "PUT",
        "path": "/spaces/1/availability",
        "pathParameters": {"id": "1"},
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({
            "available": False,
            "reason": "Reserva confirmada para evento corporativo",
            "hourly_rate": 20.0
        })
    }
    resp_put = catalog_handler.lambda_handler(event_put, None)
    put_data = json.loads(resp_put["body"])
    print(f"Respuesta de API Gateway: {put_data['message']}")
    print(f"Evento emitido a EventBridge:")
    print(json.dumps(put_data["event_published"]["detail"], indent=2))

    # PASO 3: EventBridge enruta el evento hacia la cola SQS
    print_separator("PASO 3: Recepción del mensaje en SQS (catalog-events)")
    sqs_message = {
        "Records": [
            {
                "messageId": "sqs-msg-uuid-98765",
                "receiptHandle": "AQEBz81s...",
                "body": json.dumps({
                    "version": "0",
                    "id": "eb-evt-112233",
                    "detail-type": "SpaceChanged",
                    "source": "coworking.catalog",
                    "time": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "detail": put_data["event_published"]["detail"]
                })
            }
        ]
    }
    print(f"Mensaje encolado en SQS con ID: {sqs_message['Records'][0]['messageId']}")

    # PASO 4: Invocación de Lambda consumer-fn desde SQS
    print_separator("PASO 4: Consumo por Lambda consumer-fn")
    consumer_result = consumer_handler.lambda_handler(sqs_message, None)
    print(f"Resultado del procesamiento en Lambda Consumidora:")
    print(json.dumps(consumer_result, indent=2))

    # PASO 5: Verificación de estado desacoplado
    print_separator("RESUMEN DE LA ARQUITECTURA COMPLETADA")
    print("1. [OK] El catálogo ahora es Serverless (AWS Lambda + API Gateway).")
    print("2. [OK] Los cambios de disponibilidad se transmiten asíncronamente mediante EventBridge.")
    print("3. [OK] La cola SQS actúa como amortiguador (buffer) evitando pérdidas de datos.")
    print("4. [OK] orders-service se desacopló temporalmente y no sufrirá caídas si el catálogo se apaga.")
    print("=" * 70)

if __name__ == "__main__":
    main()
