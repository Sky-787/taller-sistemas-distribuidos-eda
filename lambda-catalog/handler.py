import json
import os
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

# Configuración de Logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Configuración de EventBridge
EVENT_BUS_NAME = os.getenv("EVENT_BUS_NAME", "default")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", os.getenv("AWS_REGION", "us-east-1"))
LOCALSTACK_HOSTNAME = os.getenv("LOCALSTACK_HOSTNAME")

def get_eventbridge_client():
    """Inicializa el cliente de EventBridge, compatible con AWS real y LocalStack."""
    endpoint_url = None
    if LOCALSTACK_HOSTNAME:
        endpoint_url = f"http://{LOCALSTACK_HOSTNAME}:4566"
    elif os.getenv("AWS_ENDPOINT_URL"):
        endpoint_url = os.getenv("AWS_ENDPOINT_URL")

    try:
        return boto3.client("events", region_name=AWS_REGION, endpoint_url=endpoint_url)
    except Exception as exc:
        logger.warning(f"No se pudo crear cliente EventBridge: {exc}")
        return None

# Catálogo en memoria simulado (persiste durante el ciclo de vida del contenedor de Lambda)
SPACES: Dict[int, Dict[str, Any]] = {
    1: {"id": 1, "name": "Escritorio Individual Flex", "capacity": 1, "hourly_rate": 15.0, "price_per_hour": 15.0, "available": True},
    2: {"id": 2, "name": "Oficina Privada Junior", "capacity": 3, "hourly_rate": 35.0, "price_per_hour": 35.0, "available": True},
    3: {"id": 3, "name": "Sala de Juntas Ejecutiva", "capacity": 8, "hourly_rate": 60.0, "price_per_hour": 60.0, "available": True},
    4: {"id": 4, "name": "Auditorio Principal", "capacity": 25, "hourly_rate": 150.0, "price_per_hour": 150.0, "available": True},
}

def build_response(status_code: int, body: Any) -> Dict[str, Any]:
    """Genera una respuesta compatible con AWS API Gateway Proxy Integration."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization"
        },
        "body": json.dumps(body)
    }

def publish_space_changed_event(space: Dict[str, Any], previous_state: bool, reason: str = "availability_update") -> Dict[str, Any]:
    """
    Publica un evento en AWS EventBridge cuando cambia la disponibilidad o datos del espacio.
    Patrón: Event-Driven Architecture (EDA)
    """
    event_detail = {
        "space_id": space["id"],
        "name": space["name"],
        "capacity": space["capacity"],
        "available": space["available"],
        "hourly_rate": space.get("hourly_rate", space.get("price_per_hour", 0.0)),
        "price_per_hour": space.get("price_per_hour", space.get("hourly_rate", 0.0)),
        "previous_available": previous_state,
        "reason": reason,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    client = get_eventbridge_client()
    if client:
        try:
            entry = {
                "Source": "coworking.catalog",
                "DetailType": "SpaceChanged",
                "Detail": json.dumps(event_detail),
                "EventBusName": EVENT_BUS_NAME
            }
            response = client.put_events(Entries=[entry])
            logger.info(f"Evento SpaceChanged publicado en EventBridge: {response}")
            return {"status": "published", "detail": event_detail, "eventbridge_response": response}
        except (BotoCoreError, ClientError, NoCredentialsError) as exc:
            logger.warning(f"Fallo al publicar en EventBridge (Modo Simulación Activo): {exc}")
            return {"status": "simulated_local", "detail": event_detail, "error": str(exc)}
    else:
        logger.info(f"Evento SpaceChanged simulado localmente: {event_detail}")
        return {"status": "simulated_offline", "detail": event_detail}

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handler principal de la Lambda de Catálogo.
    Soporta API Gateway REST API v1 y HTTP API v2.
    """
    logger.info(f"Evento recibido: {json.dumps(event)}")

    # Detectar método HTTP y ruta
    http_method = event.get("httpMethod") or event.get("requestContext", {}).get("http", {}).get("method", "GET")
    raw_path = event.get("path") or event.get("rawPath", "/spaces")
    path_parameters = event.get("pathParameters") or {}

    # Manejo de CORS Preflight
    if http_method == "OPTIONS":
        return build_response(200, {"message": "CORS OK"})

    # Rutas:
    # 1. Health check
    if raw_path.endswith("/health"):
        return build_response(200, {
            "status": "ok",
            "service": "lambda-catalog",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    # 2. GET /spaces
    if (raw_path == "/spaces" or raw_path.endswith("/spaces")) and http_method == "GET":
        return build_response(200, list(SPACES.values()))

    # 3. GET /spaces/{id}
    space_id_str = path_parameters.get("id") or path_parameters.get("space_id")
    if not space_id_str and "/spaces/" in raw_path:
        parts = raw_path.rstrip("/").split("/spaces/")
        if len(parts) > 1 and parts[1].split("/")[0].isdigit():
            space_id_str = parts[1].split("/")[0]

    if space_id_str and space_id_str.isdigit():
        space_id = int(space_id_str)
        space = SPACES.get(space_id)

        if not space:
            return build_response(404, {"detail": f"Espacio con ID {space_id} no encontrado"})

        # Si es GET /spaces/{id}
        if http_method == "GET" and not raw_path.endswith("/availability"):
            return build_response(200, space)

        # 4. PUT / POST /spaces/{id}/availability (o actualización de disponibilidad)
        if http_method in ["PUT", "POST", "PATCH"]:
            try:
                body = json.loads(event.get("body") or "{}") if isinstance(event.get("body"), str) else (event.get("body") or {})
            except json.JSONDecodeError:
                return build_response(400, {"detail": "Cuerpo JSON inválido"})

            new_available = body.get("available")
            if new_available is None:
                return build_response(400, {"detail": "Campo 'available' requerido (booleano)"})

            previous_state = space["available"]
            space["available"] = bool(new_available)

            if "hourly_rate" in body:
                space["hourly_rate"] = float(body["hourly_rate"])
                space["price_per_hour"] = float(body["hourly_rate"])

            # Disparar evento a EventBridge si cambió la disponibilidad
            event_result = publish_space_changed_event(
                space=space,
                previous_state=previous_state,
                reason=body.get("reason", "manual_api_update")
            )

            return build_response(200, {
                "message": "Espacio actualizado exitosamente",
                "space": space,
                "event_published": event_result
            })

    return build_response(404, {"detail": f"Ruta no encontrada: {http_method} {raw_path}"})
