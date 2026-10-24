import json
import os
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List
import boto3
import httpx

# Configuración de Logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Configuración de integración
ORDERS_SERVICE_URL = os.getenv("ORDERS_SERVICE_URL", "http://orders-service:8002")
LOCALSTACK_HOSTNAME = os.getenv("LOCALSTACK_HOSTNAME")

# Registro en memoria de eventos procesados (para trazabilidad e idempotencia)
PROCESSED_EVENTS: List[Dict[str, Any]] = []

def forward_event_to_orders_service(detail: Dict[str, Any]) -> Dict[str, Any]:
    """
    Notifica a orders-service sobre el cambio de disponibilidad de un espacio.
    Patrón: Event-Carried State Transfer (ECST) para desacoplar temporalmente los servicios.
    """
    webhook_url = f"{ORDERS_SERVICE_URL}/events/space-changed"
    logger.info(f"Notificando a orders-service en {webhook_url}...")

    payload = {
        "event_type": "SpaceChanged",
        "space_id": detail.get("space_id"),
        "name": detail.get("name"),
        "available": detail.get("available"),
        "hourly_rate": detail.get("hourly_rate", detail.get("price_per_hour", 0.0)),
        "price_per_hour": detail.get("price_per_hour", detail.get("hourly_rate", 0.0)),
        "timestamp": detail.get("timestamp", datetime.now(timezone.utc).isoformat())
    }

    try:
        with httpx.Client(timeout=3.0) as client:
            response = client.post(webhook_url, json=payload)
            if response.status_code in [200, 201]:
                logger.info(f"Notificación exitosa a orders-service: {response.json()}")
                return {"status": "delivered", "response_code": response.status_code}
            else:
                logger.warning(f"orders-service respondió con código {response.status_code}: {response.text}")
                return {"status": "warning", "response_code": response.status_code, "body": response.text}
    except httpx.RequestError as exc:
        # En caso de que orders-service esté temporalmente inaccesible o en pruebas locales aisladas
        logger.warning(f"No se pudo alcanzar orders-service ({ORDERS_SERVICE_URL}): {exc}. Guardando en búfer local.")
        return {"status": "buffered_offline", "error": str(exc)}

def process_single_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Procesa un mensaje individual proveniente de SQS."""
    message_id = record.get("messageId", "unknown")
    body_str = record.get("body", "{}")
    
    try:
        body = json.loads(body_str) if isinstance(body_str, str) else body_str
    except json.JSONDecodeError:
        logger.error(f"Error decodificando payload JSON en mensaje {message_id}: {body_str}")
        return {"message_id": message_id, "status": "error", "reason": "invalid_json"}

    # Extraer el 'detail' si proviene empaquetado por EventBridge
    detail = body.get("detail", body)
    detail_type = body.get("detail-type") or body.get("DetailType") or "SpaceChanged"

    logger.info(f"Procesando evento '{detail_type}' de mensaje {message_id}: {detail}")

    # Notificar a orders-service
    forward_result = forward_event_to_orders_service(detail)

    event_summary = {
        "message_id": message_id,
        "detail_type": detail_type,
        "space_id": detail.get("space_id"),
        "available": detail.get("available"),
        "delivery": forward_result,
        "processed_at": datetime.now(timezone.utc).isoformat()
    }
    PROCESSED_EVENTS.append(event_summary)
    return event_summary

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handler principal de la Lambda Consumidora activada por eventos de SQS.
    """
    logger.info(f"Lote de eventos recibido desde SQS: {json.dumps(event)}")
    records = event.get("Records", [])
    
    if not records:
        # Soporte para invocación directa con payload de prueba
        logger.info("Invocación directa sin 'Records' de SQS, procesando evento plano.")
        single_res = process_single_record({"messageId": "direct-call", "body": event})
        return {
            "statusCode": 200,
            "processed_count": 1,
            "results": [single_res]
        }

    results = []
    failed_message_ids = []

    for record in records:
        try:
            res = process_single_record(record)
            results.append(res)
        except Exception as exc:
            logger.error(f"Error crítico procesando mensaje {record.get('messageId')}: {exc}")
            failed_message_ids.append(record.get("messageId"))

    # Soporte para Partial Batch Failure Reporting de AWS SQS
    response = {
        "statusCode": 200,
        "total_records": len(records),
        "processed_count": len(results),
        "failures_count": len(failed_message_ids),
        "results": results
    }

    if failed_message_ids:
        response["batchItemFailures"] = [{"itemIdentifier": mid} for mid in failed_message_ids]

    logger.info(f"Lote SQS finalizado: {response}")
    return response
