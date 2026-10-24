#!/bin/bash

# ==============================================================================
# LAB 4: Chaos Engineering - Caída de Servicio Dependiente (catalog-service)
# ==============================================================================

echo "================================================================="
echo " PASO 1: Prueba de línea base (Estado Normal)"
echo " Ambos servicios están en línea. Creando una orden..."
echo "================================================================="
RESPONSE_1=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST "http://localhost:8002/orders?space_id=1&user_email=normal@example.com&hours=2")
BODY_1=$(echo "$RESPONSE_1" | sed '$d')
STATUS_1=$(echo "$RESPONSE_1" | tail -n 1 | cut -d: -f2)

echo "Respuesta: $BODY_1"
echo "Código HTTP recibido: $STATUS_1"
echo ""

# Pausa para claridad
sleep 2

echo "================================================================="
echo " PASO 2: Inyección de Caos (Apagando catalog-service)"
echo " Simulando fallo catastrófico en el microservicio de catálogo..."
echo "================================================================="
docker stop catalog-service

echo ""
echo "Intentando crear una orden mientras el catálogo está caído..."
RESPONSE_2=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST "http://localhost:8002/orders?space_id=1&user_email=chaos@example.com&hours=2")
BODY_2=$(echo "$RESPONSE_2" | sed '$d')
STATUS_2=$(echo "$RESPONSE_2" | tail -n 1 | cut -d: -f2)

echo "Respuesta: $BODY_2"
echo "Código HTTP recibido: $STATUS_2 (Esperado: 503)"
echo ""

# Pausa para claridad
sleep 2

echo "================================================================="
echo " PASO 3: Recuperación del servicio (Restaurando catalog-service)"
echo " Levantando nuevamente catalog-service..."
echo "================================================================="
docker start catalog-service

echo "Esperando 3 segundos a que catalog-service inicialice..."
sleep 3

echo ""
echo "Reintentando crear una orden tras la recuperación..."
RESPONSE_3=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST "http://localhost:8002/orders?space_id=1&user_email=recovered@example.com&hours=2")
BODY_3=$(echo "$RESPONSE_3" | sed '$d')
STATUS_3=$(echo "$RESPONSE_3" | tail -n 1 | cut -d: -f2)

echo "Respuesta: $BODY_3"
echo "Código HTTP recibido: $STATUS_3 (Esperado: 201 o 200)"
echo ""

echo "================================================================="
echo " Resumen del experimento de Chaos Engineering:"
echo " 1. Normal:       HTTP $STATUS_1"
echo " 2. En Caos:      HTTP $STATUS_2"
echo " 3. Recuperado:   HTTP $STATUS_3"
echo "================================================================="
