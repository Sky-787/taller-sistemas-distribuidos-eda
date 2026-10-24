import os
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
import httpx
from fastapi import FastAPI, HTTPException, Query, Body
from pydantic import BaseModel

# Configuración de Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("orders-service")

app = FastAPI(
    title="Orders Service",
    description="Servicio de gestión de órdenes de reserva de coworking con resiliencia y soporte Event-Driven",
    version="2.0.0"
)

# URL del catalog-service configurable por variable de entorno
CATALOG_SERVICE_URL = os.getenv("CATALOG_SERVICE_URL", "http://catalog-service:8001")
if CATALOG_SERVICE_URL and not CATALOG_SERVICE_URL.startswith(("http://", "https://")):
    CATALOG_SERVICE_URL = f"https://{CATALOG_SERVICE_URL}"

# Caché local de espacios sincronizada mediante eventos (Event-Carried State Transfer)
SPACES_CACHE: Dict[int, Dict[str, Any]] = {
    1: {"id": 1, "name": "Escritorio Individual Flex", "price_per_hour": 15.0, "hourly_rate": 15.0, "available": True},
    2: {"id": 2, "name": "Oficina Privada Junior", "price_per_hour": 35.0, "hourly_rate": 35.0, "available": True},
    3: {"id": 3, "name": "Sala de Juntas Ejecutiva", "price_per_hour": 60.0, "hourly_rate": 60.0, "available": True},
    4: {"id": 4, "name": "Auditorio Principal", "price_per_hour": 150.0, "hourly_rate": 150.0, "available": True},
}

class Order(BaseModel):
    id: int
    space_id: int
    space_name: Optional[str] = None
    user_email: str
    hours: int
    price_per_hour: float
    total_price: float
    status: str = "CONFIRMED"
    fulfillment_source: str = "SYNCHRONOUS_CATALOG"  # "SYNCHRONOUS_CATALOG" o "EVENT_CACHE_FALLBACK"
    created_at: str

# Almacenamiento en memoria para órdenes
ORDERS: List[Order] = []

@app.get("/", tags=["Inicio"])
def root():
    return {
        "message": "Microservicio de Órdenes de Coworking (FastAPI)",
        "docs_url": "/docs",
        "endpoints": {
            "health": "/health",
            "orders": "/orders",
            "catalog_cache": "/catalog-cache",
            "event_webhook": "/events/space-changed"
        }
    }

@app.get("/health", tags=["Salud"])
def health_check():
    """Endpoint de verificación de salud del microservicio de órdenes."""
    return {"status": "ok", "service": "orders-service", "version": "2.0.0"}

@app.get("/orders", response_model=List[Order], tags=["Órdenes"])
def get_orders():
    """Retorna el listado completo de órdenes registradas."""
    return ORDERS

@app.get("/catalog-cache", tags=["Event-Driven Architecture"])
def get_catalog_cache():
    """
    Retorna el estado de la caché local sincronizada a través de eventos SpaceChanged
    provenientes de EventBridge -> SQS -> Lambda Consumer.
    """
    return {
        "description": "Caché local desacoplada alimentada por eventos",
        "cached_spaces_count": len(SPACES_CACHE),
        "spaces": list(SPACES_CACHE.values())
    }

@app.post("/events/space-changed", tags=["Event-Driven Architecture"])
def handle_space_changed_event(event: Dict[str, Any] = Body(...)):
    """
    Webhook receptor invocado por la Lambda Consumidora (consumer-fn) de AWS.
    Aplica el patrón Event-Carried State Transfer para actualizar la disponibilidad
    y tarifas en tiempo real sin acoplamiento síncrono.
    """
    space_id = event.get("space_id")
    if not space_id:
        raise HTTPException(status_code=400, detail="Missing required field: 'space_id'")

    price = event.get("price_per_hour") or event.get("hourly_rate") or 0.0
    SPACES_CACHE[space_id] = {
        "id": space_id,
        "name": event.get("name", f"Espacio #{space_id}"),
        "capacity": event.get("capacity"),
        "available": bool(event.get("available", True)),
        "price_per_hour": float(price),
        "hourly_rate": float(price),
        "last_synced_at": event.get("timestamp", datetime.now(timezone.utc).isoformat())
    }

    logger.info(f"Caché de órdenes actualizada por evento para espacio #{space_id}: {SPACES_CACHE[space_id]}")
    return {
        "status": "synchronized",
        "space_id": space_id,
        "cached_data": SPACES_CACHE[space_id]
    }

@app.post("/orders", response_model=Order, status_code=201, tags=["Órdenes"])
async def create_order(
    space_id: int = Query(..., description="ID del espacio a reservar"),
    user_email: str = Query(..., description="Email del usuario que reserva"),
    hours: int = Query(..., gt=0, description="Cantidad de horas de reserva"),
    enable_eda_fallback: bool = Query(True, description="Usar caché Event-Driven si el catálogo síncrono falla")
):
    """
    Crea una nueva orden de reserva.
    1. Intenta consultar el catálogo síncrono por HTTP.
    2. Si el catálogo síncrono falla (Chaos Lab 4) y enable_eda_fallback=True,
       utiliza la caché local sincronizada por EventBridge/SQS evitando la indisponibilidad total.
    3. Soporta tolerant reader (price_per_hour / hourly_rate) para evitar fallos por cambio de contrato (Chaos Lab 5).
    """
    catalog_url = f"{CATALOG_SERVICE_URL}/spaces/{space_id}"
    space_data = None
    fulfillment_source = "SYNCHRONOUS_CATALOG"

    # 1. Intentar consulta síncrona
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(catalog_url)
            if response.status_code == 200:
                space_data = response.json()
            elif response.status_code == 404:
                raise HTTPException(status_code=404, detail=f"Space with id {space_id} not found in catalog")
            else:
                logger.warning(f"Error inesperado del catálogo síncrono: {response.status_code}")
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise exc
        logger.warning(f"Catálogo síncrono no responde en {catalog_url}: {exc}")
        if not enable_eda_fallback:
            # Comportamiento estricto de Chaos Lab 4 (sin EDA)
            raise HTTPException(status_code=503, detail="Catalog service unavailable") from exc

    # 2. Resiliencia Event-Driven: Si el catálogo síncrono falló, usar caché local
    if space_data is None:
        if space_id in SPACES_CACHE:
            logger.info(f"Activando Fallback Resiliente EDA: Usando caché local para espacio #{space_id}")
            space_data = SPACES_CACHE[space_id]
            fulfillment_source = "EVENT_CACHE_FALLBACK"
        else:
            raise HTTPException(
                status_code=503,
                detail="Catalog service unavailable and no cached event state found for this space"
            )

    # Validar disponibilidad
    if not space_data.get("available", True):
        raise HTTPException(
            status_code=400,
            detail=f"El espacio '{space_data.get('name')}' no se encuentra disponible actualmente."
        )

    # Tolerant Reader (Soporta tanto 'price_per_hour' como 'hourly_rate')
    price_val = space_data.get("price_per_hour")
    if price_val is None:
        price_val = space_data.get("hourly_rate")

    if price_val is None:
        raise HTTPException(
            status_code=500,
            detail="Contract error: neither 'price_per_hour' nor 'hourly_rate' found in space data"
        )

    price_per_hour = float(price_val)
    total_price = round(price_per_hour * hours, 2)
    space_name = space_data.get("name", f"Espacio #{space_id}")

    order = Order(
        id=len(ORDERS) + 1,
        space_id=space_id,
        space_name=space_name,
        user_email=user_email,
        hours=hours,
        price_per_hour=price_per_hour,
        total_price=total_price,
        status="CONFIRMED",
        fulfillment_source=fulfillment_source,
        created_at=datetime.now(timezone.utc).isoformat()
    )

    ORDERS.append(order)
    logger.info(f"Orden #{order.id} creada exitosamente (Fuente: {fulfillment_source})")
    return order

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)
