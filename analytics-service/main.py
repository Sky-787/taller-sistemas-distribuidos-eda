import os
import logging
from fastapi import FastAPI, HTTPException, Query, Body
from typing import Dict, Any, Optional
from mongodb_client import analytics_client

# Configuración de Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("analytics-service")

app = FastAPI(
    title="Analytics Service",
    description="Servicio de analytics de uso para coworking — MongoDB Atlas",
    version="1.0.0"
)


@app.on_event("startup")
def startup_event():
    """Conectar a MongoDB al iniciar el servicio."""
    try:
        analytics_client.connect()
        logger.info("Analytics Service conectado a MongoDB")
    except Exception as e:
        logger.error(f"No se pudo conectar a MongoDB al inicio: {e}")


@app.get("/", tags=["Inicio"])
def root():
    return {
        "message": "Microservicio de Analytics de Coworking (MongoDB)",
        "docs_url": "/docs",
        "endpoints": {
            "health": "/health",
            "track_event": "/events (POST)",
            "get_events": "/events (GET)",
            "popular_spaces": "/analytics/popular-spaces",
            "revenue": "/analytics/revenue",
            "usage_by_hour": "/analytics/usage-by-hour",
            "top_users": "/analytics/top-users"
        }
    }


@app.get("/health", tags=["Salud"])
def health_check():
    """Verificación de salud del servicio y conexión a MongoDB."""
    mongo_status = analytics_client.health_check()
    return {
        "status": "ok" if mongo_status["status"] == "connected" else "degraded",
        "service": "analytics-service",
        "version": "1.0.0",
        "mongodb": mongo_status
    }


# ─── Eventos ──────────────────────────────────────────────────────

@app.post("/events", tags=["Eventos"])
def track_event(event: Dict[str, Any] = Body(...)):
    """
    Registra un evento de analytics.
    Campos esperados: event_type, space_id, space_name, user_email, hours, total_price, etc.
    """
    event_type = event.get("event_type")
    if not event_type:
        raise HTTPException(status_code=400, detail="Campo 'event_type' es requerido")

    event_id = analytics_client.track_event(event_type, event)
    return {"status": "tracked", "event_id": event_id}


@app.get("/events", tags=["Eventos"])
def get_events(
    event_type: Optional[str] = Query(None, description="Filtrar por tipo de evento"),
    limit: int = Query(50, ge=1, le=500, description="Cantidad máxima de eventos")
):
    """Retorna eventos recientes registrados."""
    events = analytics_client.get_events(event_type=event_type, limit=limit)
    # Convertir datetime a string para serialización JSON
    for evt in events:
        if "timestamp" in evt:
            evt["timestamp"] = evt["timestamp"].isoformat()
    return {"count": len(events), "events": events}


# ─── Queries de Analytics ─────────────────────────────────────────

@app.get("/analytics/popular-spaces", tags=["Analytics"])
def popular_spaces(
    days: int = Query(30, ge=1, le=365, description="Período en días"),
    limit: int = Query(10, ge=1, le=50)
):
    """Retorna los espacios más reservados en los últimos N días."""
    result = analytics_client.get_popular_spaces(days=days, limit=limit)
    return {"period_days": days, "spaces": result}


@app.get("/analytics/revenue", tags=["Analytics"])
def revenue_summary(
    days: int = Query(30, ge=1, le=365, description="Período en días")
):
    """Resumen de ingresos: total órdenes, revenue, horas, promedio."""
    result = analytics_client.get_revenue_summary(days=days)
    return {"period_days": days, "summary": result}


@app.get("/analytics/usage-by-hour", tags=["Analytics"])
def usage_by_hour(
    days: int = Query(7, ge=1, le=90, description="Período en días")
):
    """Distribución de reservas por hora del día."""
    result = analytics_client.get_usage_by_hour(days=days)
    return {"period_days": days, "distribution": result}


@app.get("/analytics/top-users", tags=["Analytics"])
def top_users(
    days: int = Query(30, ge=1, le=365, description="Período en días"),
    limit: int = Query(10, ge=1, le=50)
):
    """Usuarios con más reservas."""
    result = analytics_client.get_top_users(days=days, limit=limit)
    return {"period_days": days, "users": result}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8003, reload=True)

