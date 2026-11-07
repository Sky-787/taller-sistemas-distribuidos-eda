import os
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from datetime import datetime, timedelta, timezone
import logging
import time

logger = logging.getLogger("analytics-service")

# URI de conexión a MongoDB (viene del docker-compose)
MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb://analytics:analytics123@mongo:27017/coworking_analytics?authSource=admin"
)
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "coworking_analytics")


class AnalyticsClient:
    """Cliente MongoDB con manejo de conexiones, retry y operaciones de analytics."""

    def __init__(self, uri=None, db_name=None, max_retries=3, retry_delay=2):
        self.uri = uri or MONGO_URI
        self.db_name = db_name or MONGO_DB_NAME
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._client = None
        self._db = None

    def connect(self):
        """Establece conexión a MongoDB con reintentos."""
        for attempt in range(1, self.max_retries + 1):
            try:
                self._client = MongoClient(
                    self.uri,
                    serverSelectionTimeoutMS=5000,
                    connectTimeoutMS=5000,
                    maxPoolSize=10,
                    minPoolSize=2,
                    retryWrites=True
                )
                # Verificar conexión
                self._client.admin.command("ping")
                self._db = self._client[self.db_name]
                logger.info(f"Conectado a MongoDB (intento {attempt})")
                self._create_indexes()
                return True
            except (ConnectionFailure, ServerSelectionTimeoutError) as e:
                logger.warning(
                    f"Intento {attempt}/{self.max_retries} fallido: {e}"
                )
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay * attempt)
                else:
                    logger.error("No se pudo conectar a MongoDB tras reintentos")
                    raise

    def _create_indexes(self):
        """Crea índices para optimizar consultas de analytics."""
        events = self._db["events"]
        events.create_index([("event_type", ASCENDING)])
        events.create_index([("timestamp", DESCENDING)])
        events.create_index([("space_id", ASCENDING), ("timestamp", DESCENDING)])
        events.create_index([("user_email", ASCENDING)])

        metrics = self._db["metrics"]
        metrics.create_index([("metric_name", ASCENDING), ("timestamp", DESCENDING)])
        logger.info("Índices de MongoDB creados/verificados")

    @property
    def db(self):
        if self._db is None:
            self.connect()
        return self._db

    # ─── Operaciones de Eventos ───────────────────────────────────

    def track_event(self, event_type: str, data: dict):
        """Registra un evento de analytics (orden creada, cancelada, etc.)."""
        event = {
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc),
            **data
        }
        result = self.db["events"].insert_one(event)
        logger.info(f"Evento '{event_type}' registrado: {result.inserted_id}")
        return str(result.inserted_id)

    def get_events(self, event_type: str = None, limit: int = 50):
        """Obtiene eventos recientes, opcionalmente filtrados por tipo."""
        query = {}
        if event_type:
            query["event_type"] = event_type
        cursor = self.db["events"].find(
            query, {"_id": 0}
        ).sort("timestamp", DESCENDING).limit(limit)
        return list(cursor)

    # ─── Queries de Analytics ─────────────────────────────────────

    def get_popular_spaces(self, days: int = 30, limit: int = 10):
        """Retorna los espacios más reservados en los últimos N días."""
        since = datetime.now(timezone.utc) - timedelta(days=days)
        pipeline = [
            {"$match": {
                "event_type": "order_created",
                "timestamp": {"$gte": since}
            }},
            {"$group": {
                "_id": "$space_id",
                "space_name": {"$first": "$space_name"},
                "total_bookings": {"$sum": 1},
                "total_hours": {"$sum": "$hours"},
                "total_revenue": {"$sum": "$total_price"}
            }},
            {"$sort": {"total_bookings": -1}},
            {"$limit": limit}
        ]
        return list(self.db["events"].aggregate(pipeline))

    def get_revenue_summary(self, days: int = 30):
        """Resumen de ingresos en los últimos N días."""
        since = datetime.now(timezone.utc) - timedelta(days=days)
        pipeline = [
            {"$match": {
                "event_type": "order_created",
                "timestamp": {"$gte": since}
            }},
            {"$group": {
                "_id": None,
                "total_orders": {"$sum": 1},
                "total_revenue": {"$sum": "$total_price"},
                "total_hours": {"$sum": "$hours"},
                "avg_order_value": {"$avg": "$total_price"}
            }}
        ]
        result = list(self.db["events"].aggregate(pipeline))
        if result:
            summary = result[0]
            summary.pop("_id", None)
            return summary
        return {
            "total_orders": 0,
            "total_revenue": 0.0,
            "total_hours": 0,
            "avg_order_value": 0.0
        }

    def get_usage_by_hour(self, days: int = 7):
        """Distribución de reservas por hora del día."""
        since = datetime.now(timezone.utc) - timedelta(days=days)
        pipeline = [
            {"$match": {
                "event_type": "order_created",
                "timestamp": {"$gte": since}
            }},
            {"$group": {
                "_id": {"$hour": "$timestamp"},
                "bookings": {"$sum": 1}
            }},
            {"$sort": {"_id": 1}}
        ]
        return list(self.db["events"].aggregate(pipeline))

    def get_top_users(self, days: int = 30, limit: int = 10):
        """Usuarios con más reservas."""
        since = datetime.now(timezone.utc) - timedelta(days=days)
        pipeline = [
            {"$match": {
                "event_type": "order_created",
                "timestamp": {"$gte": since}
            }},
            {"$group": {
                "_id": "$user_email",
                "total_bookings": {"$sum": 1},
                "total_spent": {"$sum": "$total_price"}
            }},
            {"$sort": {"total_bookings": -1}},
            {"$limit": limit}
        ]
        return list(self.db["events"].aggregate(pipeline))

    # ─── Métricas ─────────────────────────────────────────────────

    def record_metric(self, metric_name: str, value: float, tags: dict = None):
        """Registra una métrica puntual (latencia, contadores, etc.)."""
        doc = {
            "metric_name": metric_name,
            "value": value,
            "timestamp": datetime.now(timezone.utc),
            "tags": tags or {}
        }
        self.db["metrics"].insert_one(doc)

    def health_check(self):
        """Verifica la conexión a MongoDB."""
        try:
            self._client.admin.command("ping")
            return {"status": "connected", "database": self.db_name}
        except Exception as e:
            return {"status": "disconnected", "error": str(e)}


# Instancia global reutilizable
analytics_client = AnalyticsClient()

