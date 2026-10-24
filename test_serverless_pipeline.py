"""
test_serverless_pipeline.py
Suite de pruebas automatizadas para validar el flujo completo de:
1. Lambda Catalog-Service (API Gateway + EventBridge)
2. SQS Queue + Lambda Consumer
3. Orders-Service (Caché local Event-Carried State Transfer y Fallback resiliente)
"""

import json
import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# Importar handlers y servicios
import importlib.util
from pathlib import Path
import sys
import os

# Cargar handlers explícitamente para evitar colisión de nombre de módulo 'handler'
catalog_spec = importlib.util.spec_from_file_location("catalog_handler", Path("lambda-catalog/handler.py").resolve())
catalog_handler = importlib.util.module_from_spec(catalog_spec)
catalog_spec.loader.exec_module(catalog_handler)

consumer_spec = importlib.util.spec_from_file_location("consumer_handler", Path("lambda-consumer/handler.py").resolve())
consumer_handler = importlib.util.module_from_spec(consumer_spec)
consumer_spec.loader.exec_module(consumer_handler)

sys.path.insert(0, os.path.abspath("orders-service"))
from main import app as orders_app, SPACES_CACHE, ORDERS

class TestServerlessEventDrivenArchitecture(unittest.TestCase):

    def setUp(self):
        self.orders_client = TestClient(orders_app)

    def test_01_catalog_lambda_get_spaces(self):
        """Verifica que la Lambda de catálogo retorne la lista de espacios via API Gateway."""
        event = {
            "httpMethod": "GET",
            "path": "/spaces",
            "headers": {},
            "body": None
        }
        response = catalog_handler.lambda_handler(event, None)
        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertIsInstance(body, list)
        self.assertGreaterEqual(len(body), 4)
        print(" [PASS] LAB 6: catalog-fn GET /spaces responde 200 OK con catálogo completo")

    def test_02_catalog_lambda_update_availability_and_emit_event(self):
        """Verifica que al actualizar disponibilidad en catalog-fn se genera el evento SpaceChanged."""
        event = {
            "httpMethod": "PUT",
            "path": "/spaces/1/availability",
            "pathParameters": {"id": "1"},
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"available": False, "reason": "Mantenimiento preventivo"})
        }

        # Mock de cliente EventBridge para aislar pruebas sin AWS
        mock_eb = MagicMock()
        mock_eb.put_events.return_value = {"FailedEntryCount": 0, "Entries": [{"EventId": "evt-12345"}]}

        with patch.object(catalog_handler, "get_eventbridge_client", return_value=mock_eb):
            response = catalog_handler.lambda_handler(event, None)

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(body["space"]["available"], False)
        self.assertEqual(body["event_published"]["status"], "published")
        mock_eb.put_events.assert_called_once()
        print(" [PASS] LAB 6: catalog-fn actualiza espacio y emite evento SpaceChanged a EventBridge")

    def test_03_consumer_lambda_processes_sqs_message(self):
        """Verifica que la Lambda consumer-fn consuma mensajes de SQS y notifique a orders-service."""
        sqs_event = {
            "Records": [
                {
                    "messageId": "msg-sqs-9988",
                    "receiptHandle": "AQEBwJnKyr...",
                    "body": json.dumps({
                        "version": "0",
                        "id": "eb-evt-555",
                        "detail-type": "SpaceChanged",
                        "source": "coworking.catalog",
                        "time": "2026-10-24T18:00:00Z",
                        "detail": {
                            "space_id": 2,
                            "name": "Oficina Privada Junior",
                            "available": True,
                            "price_per_hour": 38.0,
                            "hourly_rate": 38.0,
                            "reason": "Tarifa actualizada dinámicamente"
                        }
                    })
                }
            ]
        }

        # Simular respuesta exitosa del webhook de orders-service
        with patch.object(consumer_handler, "forward_event_to_orders_service", return_value={"status": "delivered", "response_code": 200}):
            result = consumer_handler.lambda_handler(sqs_event, None)

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(result["processed_count"], 1)
        self.assertEqual(result["results"][0]["delivery"]["status"], "delivered")
        print(" [PASS] LAB 7: consumer-fn procesa lote de SQS y entrega evento a orders-service")

    def test_04_orders_service_event_webhook_updates_cache(self):
        """Verifica que orders-service reciba el evento y actualice su caché local sin peticiones síncronas."""
        payload = {
            "event_type": "SpaceChanged",
            "space_id": 3,
            "name": "Sala de Juntas Ejecutiva",
            "available": True,
            "price_per_hour": 75.0,
            "hourly_rate": 75.0,
            "timestamp": "2026-10-24T18:30:00Z"
        }
        res = self.orders_client.post("/events/space-changed", json=payload)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(SPACES_CACHE[3]["price_per_hour"], 75.0)

        # Consultar endpoint de inspección de caché
        cache_res = self.orders_client.get("/catalog-cache")
        self.assertEqual(cache_res.status_code, 200)
        data = cache_res.json()
        self.assertIn("spaces", data)
        print(" [PASS] LAB 7 (EDA Integration): orders-service sincroniza caché local mediante webhook")

    def test_05_orders_service_resilience_fallback_when_catalog_down(self):
        """
        Demuestra la solución al Chaos Engineering Lab 4:
        Cuando el catálogo síncrono está CAÍDO, orders-service utiliza la caché de eventos
        y crea la orden exitosamente (HTTP 201 Created) con status 'CONFIRMED'.
        """
        # Configurar espacio 1 en caché como disponible con precio 15.0
        SPACES_CACHE[1] = {
            "id": 1,
            "name": "Escritorio Individual Flex",
            "available": True,
            "price_per_hour": 15.0,
            "hourly_rate": 15.0
        }

        # Intentar crear orden con catálogo síncrono caído (URL inexistente o apagado)
        with patch("httpx.AsyncClient.get", side_effect=Exception("Connection refused")):
            res = self.orders_client.post(
                "/orders?space_id=1&user_email=eda-student@example.com&hours=3&enable_eda_fallback=true"
            )

        self.assertEqual(res.status_code, 201)
        order = res.json()
        self.assertEqual(order["fulfillment_source"], "EVENT_CACHE_FALLBACK")
        self.assertEqual(order["total_price"], 45.0)
        self.assertEqual(order["status"], "CONFIRMED")
        print(" [PASS] LAB 7 (Resiliencia EDA): orders-service completa orden en modo Fallback con catálogo caído")

if __name__ == "__main__":
    unittest.main()
