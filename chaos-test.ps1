# ==============================================================================
# LAB 4: Chaos Engineering - Caída de Servicio Dependiente (PowerShell)
# ==============================================================================

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " PASO 1: Prueba de línea base (Estado Normal)" -ForegroundColor Cyan
Write-Host " Ambos servicios están en línea. Creando una orden..."
Write-Host "================================================================="
$resp1 = curl.exe -s -w "`nHTTP_STATUS:%{http_code}" -X POST "http://localhost:8002/orders?space_id=1&user_email=normal@example.com&hours=2"
Write-Host $resp1
Write-Host ""

Start-Sleep -Seconds 2

Write-Host "=================================================================" -ForegroundColor Yellow
Write-Host " PASO 2: Inyección de Caos (Apagando catalog-service)" -ForegroundColor Yellow
Write-Host " Simulando fallo catastrófico en el microservicio de catálogo..."
Write-Host "================================================================="
docker stop catalog-service

Write-Host ""
Write-Host "Intentando crear una orden mientras el catálogo está caído..."
$resp2 = curl.exe -s -w "`nHTTP_STATUS:%{http_code}" -X POST "http://localhost:8002/orders?space_id=1&user_email=chaos@example.com&hours=2"
Write-Host $resp2
Write-Host ""

Start-Sleep -Seconds 2

Write-Host "=================================================================" -ForegroundColor Green
Write-Host " PASO 3: Recuperación del servicio (Restaurando catalog-service)" -ForegroundColor Green
Write-Host " Levantando nuevamente catalog-service..."
Write-Host "================================================================="
docker start catalog-service

Write-Host "Esperando 3 segundos a que catalog-service inicialice..."
Start-Sleep -Seconds 3

Write-Host ""
Write-Host "Reintentando crear una orden tras la recuperación..."
$resp3 = curl.exe -s -w "`nHTTP_STATUS:%{http_code}" -X POST "http://localhost:8002/orders?space_id=1&user_email=recovered@example.com&hours=2"
Write-Host $resp3
Write-Host ""
