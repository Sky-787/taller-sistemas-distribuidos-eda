"""
build_taller5_document.py
Genera un documento Word profesional 'Taller 5 - Reporte Tecnico.docx'
con formato académico, tablas comparativas, bloques de código estilizados,
cuadros de llamadas técnicas y resumen de pruebas del Taller 5 (LAB 11).
"""

import os
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls


def set_cell_background(cell, color_hex):
    """Aplica color de fondo a una celda de tabla."""
    shading_xml = f'<w:shd {nsdecls("w")} w:fill="{color_hex}"/>'
    cell._tc.get_or_add_tcPr().append(parse_xml(shading_xml))


def add_code_block(doc, code_text):
    """Crea un bloque de código estilizado con fondo gris y tipografía monoespaciada."""
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = tbl.cell(0, 0)
    set_cell_background(cell, "F8FAFC")
    cell.width = Inches(6.5)

    tcPr = cell._tc.get_or_add_tcPr()
    tcBorders = parse_xml(f'''
        <w:tcBorders {nsdecls("w")}>
            <w:top w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/>
            <w:left w:val="single" w:sz="14" w:space="0" w:color="2563EB"/>
            <w:bottom w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/>
            <w:right w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/>
        </w:tcBorders>
    ''')
    tcPr.append(tcBorders)

    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = 1.15
    run = p.add_run(code_text.strip())
    run.font.name = "Consolas"
    run.font.size = Pt(8.5)
    run.font.color.rgb = RGBColor(30, 41, 59)
    doc.add_paragraph()


def add_callout(doc, text, title="NOTA TÉCNICA", color_hex="EFF6FF", border_hex="2563EB"):
    """Aplica un cuadro de llamada informativo destacado."""
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = tbl.cell(0, 0)
    set_cell_background(cell, color_hex)
    cell.width = Inches(6.5)

    tcPr = cell._tc.get_or_add_tcPr()
    tcBorders = parse_xml(f'''
        <w:tcBorders {nsdecls("w")}>
            <w:top w:val="single" w:sz="4" w:space="0" w:color="{border_hex}"/>
            <w:left w:val="single" w:sz="24" w:space="0" w:color="{border_hex}"/>
            <w:bottom w:val="single" w:sz="4" w:space="0" w:color="{border_hex}"/>
            <w:right w:val="single" w:sz="4" w:space="0" w:color="{border_hex}"/>
        </w:tcBorders>
    ''')
    tcPr.append(tcBorders)

    p = cell.paragraphs[0]
    r_title = p.add_run(f"📌 {title}: ")
    r_title.bold = True
    r_title.font.name = "Calibri"
    r_title.font.size = Pt(9.5)
    r_title.font.color.rgb = RGBColor(30, 58, 138)

    r_text = p.add_run(text)
    r_text.font.name = "Calibri"
    r_text.font.size = Pt(9.5)
    r_text.font.color.rgb = RGBColor(30, 41, 59)
    doc.add_paragraph()


def build_document():
    doc = docx.Document()

    # Márgenes estándar
    for section in doc.sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.9)
        section.right_margin = Inches(0.9)

    # TÍTULO PRINCIPAL
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_main = p_title.add_run("Taller 5: Resiliencia en Microservicios con FastAPI\n")
    r_main.bold = True
    r_main.font.size = Pt(17)
    r_main.font.name = "Calibri"
    r_main.font.color.rgb = RGBColor(30, 41, 59)

    r_sub = p_title.add_run("LAB 11: Rate Limiting, Circuit Breaker y Retry with Backoff")
    r_sub.bold = True
    r_sub.font.size = Pt(13)
    r_sub.font.name = "Calibri"
    r_sub.font.color.rgb = RGBColor(37, 99, 235)

    doc.add_paragraph()

    # METADATOS DEL DOCUMENTO
    p_meta = doc.add_paragraph()
    p_meta.add_run("Proyecto: ").bold = True
    p_meta.add_run("Arquitectura de Microservicios para Coworking\n")
    p_meta.add_run("Microservicio: ").bold = True
    p_meta.add_run("orders-service (Archivo: orders-service/middleware.py)\n")
    p_meta.add_run("Tecnologías: ").bold = True
    p_meta.add_run("Python 3.13, FastAPI, HTTPX, AsyncIO, Starlette, Pytest / Unittest\n")
    p_meta.add_run("Estado de Implementación: ").bold = True
    r_status = p_meta.add_run("100% Completado y Verificado (17/17 tests PASS)")
    r_status.bold = True
    r_status.font.color.rgb = RGBColor(22, 101, 52)

    doc.add_paragraph()

    # 1. OBJETIVO DEL TALLER
    doc.add_heading("1. Objetivo del Taller", level=1)
    doc.add_paragraph(
        "Implementar tres mecanismos esenciales para garantizar la seguridad, estabilidad y alta disponibilidad de una API "
        "desarrollada con FastAPI en una arquitectura de microservicios:\n"
        "1. Rate Limiter: Limita la cantidad de solicitudes que puede realizar una dirección IP para prevenir ataques de denegación de servicio o saturación.\n"
        "2. Circuit Breaker: Evita continuar llamando a dependencias o servicios externos (catalog-service) cuando presentan fallas reiteradas.\n"
        "3. Retry with Backoff: Vuelve a intentar de forma asíncrona operaciones transitorias fallidas espaciando progresivamente el tiempo de espera."
    )

    # 2. RATE LIMITER
    doc.add_heading("2. Mecanismo 1: Rate Limiter (Limitación de Tasa)", level=1)
    doc.add_paragraph(
        "Su función es proteger los recursos computacionales de la API evitando que una misma dirección IP realice demasiadas solicitudes en poco tiempo. "
        "Se implementó la clase RateLimiter utilizando el algoritmo de Ventana Deslizante (Sliding Window) en memoria con defaultdict(list)."
    )

    add_callout(
        doc,
        "Límite máximo permitido: 100 solicitudes por dirección IP en una ventana de 60 segundos. Si se supera el límite, "
        "se devuelve el código HTTP 429 Too Many Requests con la cabecera estándar Retry-After: 60.",
        title="PARÁMETROS DEL RATE LIMITER",
        color_hex="F0FDF4",
        border_hex="16A34A"
    )

    doc.add_paragraph("Código implementado en orders-service/middleware.py:")
    add_code_block(doc, '''
class RateLimiter:
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)

    def is_allowed(self, client_id: str) -> bool:
        now = time.time()
        # Eliminar solicitudes que tengan más de 60 segundos
        self.requests[client_id] = [
            req_time for req_time in self.requests[client_id]
            if now - req_time < self.window_seconds
        ]
        # Si ya alcanzó las 100, bloquear la nueva solicitud
        if len(self.requests[client_id]) >= self.max_requests:
            return False
        # Si todavía no alcanza el límite, registrar y permitir
        self.requests[client_id].append(now)
        return True

rate_limiter = RateLimiter(max_requests=100, window_seconds=60)

async def rate_limit_middleware(request: Request, call_next):
    if request.url.path in ["/docs", "/openapi.json", "/redoc"]:
        return await call_next(request)

    client_ip = request.client.host if request.client else "127.0.0.1"

    if not rate_limiter.is_allowed(client_ip):
        return JSONResponse(
            status_code=429,
            content={"error": "Too many requests"},
            headers={"Retry-After": "60"}
        )

    response = await call_next(request)
    return response

# Registro en FastAPI (main.py):
app.middleware("http")(rate_limit_middleware)
''')

    # 3. CIRCUIT BREAKER
    doc.add_heading("3. Mecanismo 2: Circuit Breaker (Interruptor de Circuito)", level=1)
    doc.add_paragraph(
        "Su función es proteger los servicios externos y evitar el desperdicio de sockets y tiempos de espera cuando una dependencia "
        "remota está caída. Se diseñó la máquina de estados con tres fases:"
    )

    table_states = doc.add_table(rows=4, cols=3)
    table_states.alignment = WD_TABLE_ALIGNMENT.CENTER
    s_headers = ["Estado", "Comportamiento", "Condición de Transición"]
    for i, h in enumerate(s_headers):
        cell = table_states.cell(0, i)
        cell.paragraphs[0].add_run(h).bold = True
        set_cell_background(cell, "E2E8F0")

    s_data = [
        ("CLOSED (Cerrado)", "Operación normal: peticiones fluyen hacia el catálogo", "Estado inicial. Contador de errores en 0."),
        ("OPEN (Abierto)", "Servicio bloqueado: cortocircuito inmediato (HTTP 503)", "Se alcanza el umbral de 5 fallos consecutivos."),
        ("HALF_OPEN (Semiabierto)", "Prueba controlada: evalúa si el servicio se recuperó", "Transcurrieron 60 segundos desde el último fallo.")
    ]
    for r_idx, r_data in enumerate(s_data, start=1):
        for c_idx, val in enumerate(r_data):
            cell = table_states.cell(r_idx, c_idx)
            cell.paragraphs[0].add_run(val)

    doc.add_paragraph()
    doc.add_paragraph("Implementación del Circuit Breaker y la función conectora del catálogo:")
    add_code_block(doc, '''
class CircuitBreaker:
    STATE_CLOSED = "closed"
    STATE_OPEN = "open"
    STATE_HALF_OPEN = "half_open"

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = self.STATE_CLOSED

    def can_execute(self) -> bool:
        now = time.time()
        if self.state == self.STATE_CLOSED:
            return True
        if self.state == self.STATE_OPEN:
            if now - self.last_failure_time > self.recovery_timeout:
                self.state = self.STATE_HALF_OPEN
                return True
            return False
        if self.state == self.STATE_HALF_OPEN:
            return True
        return True

    def record_success(self):
        self.failure_count = 0
        self.state = self.STATE_CLOSED

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = self.STATE_OPEN

catalog_circuit = CircuitBreaker(failure_threshold=5, recovery_timeout=60)

async def call_catalog_with_breaker(url: str) -> dict:
    if not catalog_circuit.can_execute():
        raise HTTPException(status_code=503, detail="Service Unavailable: Circuit breaker is OPEN")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                catalog_circuit.record_success()
                return response.json()
            elif response.status_code == 404:
                raise HTTPException(status_code=404, detail="Resource not found")
            else:
                catalog_circuit.record_failure()
                raise HTTPException(status_code=503, detail="Catalog service error")
    except HTTPException:
        raise
    except Exception as exc:
        catalog_circuit.record_failure()
        raise HTTPException(status_code=503, detail=f"Service Unavailable: {str(exc)}")
''')

    # 4. RETRY WITH BACKOFF
    doc.add_heading("4. Mecanismo 3: Retry with Backoff (Reintento Progresivo)", level=1)
    doc.add_paragraph(
        "Su función es reintentar automáticamente una operación asíncrona ante fallas transitorias de red, espaciando progresivamente "
        "el tiempo de espera mediante una función exponencial: base_delay * (2 ** attempt)."
    )

    table_retry = doc.add_table(rows=4, cols=4)
    table_retry.alignment = WD_TABLE_ALIGNMENT.CENTER
    r_headers = ["Intento", "Fórmula", "Tiempo de Espera", "Acción Realizada"]
    for i, h in enumerate(r_headers):
        cell = table_retry.cell(0, i)
        cell.paragraphs[0].add_run(h).bold = True
        set_cell_background(cell, "E2E8F0")

    r_rows = [
        ("Primer intento (0)", "1.0 * (2 ** 0)", "1 segundo", "Falla la operación, suspende el event loop 1s"),
        ("Segundo intento (1)", "1.0 * (2 ** 1)", "2 segundos", "Vuelve a fallar, suspende el event loop 2s"),
        ("Tercer intento (2)", "—", "Sin otro intento", "Último intento. Si falla, relanza la excepción.")
    ]
    for r_idx, r_data in enumerate(r_rows, start=1):
        for c_idx, val in enumerate(r_data):
            cell = table_retry.cell(r_idx, c_idx)
            cell.paragraphs[0].add_run(val)

    doc.add_paragraph()
    doc.add_paragraph("Código de la función retry_with_backoff:")
    add_code_block(doc, '''
async def retry_with_backoff(
    func,
    max_retries: int = 3,
    base_delay: float = 1.0
):
    last_exception = None

    for attempt in range(max_retries):
        try:
            return await func()
        except Exception as e:
            last_exception = e
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"Retry {attempt + 1}/{max_retries} after {delay}s: {str(e)}")
                await asyncio.sleep(delay)

    raise last_exception
''')

    # 5. TABLA COMPARATIVA
    doc.add_heading("5. Comparativa de los Tres Mecanismos (Sección 7)", level=1)
    doc.add_paragraph("Resumen conceptual de las responsabilidades de cada patrón de resiliencia implementado:")

    table_comp = doc.add_table(rows=4, cols=3)
    table_comp.alignment = WD_TABLE_ALIGNMENT.CENTER
    c_headers = ["Mecanismo", "¿Qué protege?", "¿Para qué sirve?"]
    for i, h in enumerate(c_headers):
        cell = table_comp.cell(0, i)
        cell.paragraphs[0].add_run(h).bold = True
        set_cell_background(cell, "E2E8F0")

    c_rows = [
        ("Rate Limiter", "Tu API (servidor local)", "Evita el exceso de solicitudes, abusos y ataques DoS por IP."),
        ("Circuit Breaker", "Servicios externos (catalog-service)", "Evita llamadas repetitivas y saturación a servicios caídos."),
        ("Retry with Backoff", "Operaciones fallidas", "Intenta recuperar operaciones temporalmente fallidas de forma no bloqueante.")
    ]
    for r_idx, r_data in enumerate(c_rows, start=1):
        for c_idx, val in enumerate(r_data):
            cell = table_comp.cell(r_idx, c_idx)
            cell.paragraphs[0].add_run(val)

    doc.add_paragraph()

    # 6. OBSERVACIONES PARA PRODUCCIÓN
    doc.add_heading("6. Observaciones y Sugerencias de Producción (Sección 6)", level=1)
    doc.add_paragraph(
        "Antes de desplegar estos mecanismos en un clúster de producción con alta concurrencia, deben considerarse las siguientes mejoras arquitectónicas:\n\n"
        "1. Almacenamiento Distribuido (Redis): El Rate Limiter almacena timestamps en la memoria RAM del proceso. En despliegues multi-instancia detrás de balanceadores, las peticiones se dispersan y el contador se reinicia si el contenedor reinicia. Conviene usar Redis con estructuras Token Bucket.\n"
        "2. Identificación IP tras Proxies: El atributo request.client.host puede identificar al proxy inverso (AWS ALB, NGINX o Cloudflare). Debe leerse la cabecera X-Forwarded-For con validación de proxies de confianza.\n"
        "3. Sincronización en HALF_OPEN: En alta concurrencia, varias solicitudes en HALF_OPEN podrían lanzar pruebas simultáneas. Se sugiere proteger el intento con un semáforo o asyncio.Lock.\n"
        "4. Idempotencia en Reintentos: No todas las operaciones deben reintentarse automáticamente. Operaciones de escritura (cobros bancarios, órdenes) sin llaves de idempotencia podrían duplicar transacciones.\n"
        "5. Filtrado de Errores Transitorios: Debe restringirse el Retry a excepciones transitorias (timeouts, fallos de red, 503) y no capturar errores de cliente 4xx (400, 401, 404)."
    )

    # 7. PRUEBAS AUTOMATIZADAS
    doc.add_heading("7. Verificación y Resultados de Pruebas Automatizadas", level=1)
    doc.add_paragraph(
        "Se desarrolló una suite completa de pruebas automatizadas en test_taller5_resilience.py, abarcando pruebas unitarias de clases, "
        "tiempos de ventana deslizante, conmutación de estados del Circuit Breaker, reintentos exponenciales y pruebas de integración con FastAPI TestClient:"
    )

    add_code_block(doc, '''
----------------------------------------------------------------------
Ran 17 tests in 0.535s

OK
 [PASS] 1. RateLimiter inicializa correctamente con 100 req / 60s
 [PASS] 2. RateLimiter permite solicitudes dentro del umbral (5/5 permitidas)
 [PASS] 3. RateLimiter bloquea solicitud excedente (is_allowed -> False)
 [PASS] 4. Aislamiento independiente por dirección IP verificado
 [PASS] 5. Ventana deslizante limpia solicitudes expiradas y restaura cupo
 [PASS] 6. CircuitBreaker inicia en estado 'closed' con umbral 5 y timeout 60s
 [PASS] 7. CircuitBreaker transiciona a 'open' al 5to fallo y bloquea ejecución
 [PASS] 8. CircuitBreaker conmuta de 'open' a 'half_open' tras expirar recovery_timeout
 [PASS] 9. Éxito en 'half_open' cierra el circuito ('closed') y reinicia contador a 0
 [PASS] 10. call_catalog_with_breaker retorna HTTP 503 inmediato cuando el circuito está OPEN
 [PASS] 11. call_catalog_with_breaker procesa respuesta HTTP 200 y registra éxito
 [PASS] 12. call_catalog_with_breaker captura fallo de red, incrementa errores y lanza 503
 [PASS] 13. retry_with_backoff retorna inmediatamente si el primer intento tiene éxito
 [PASS] 14. retry_with_backoff reintenta con retardo progresivo y resuelve éxito en intento #2
 [PASS] 15. retry_with_backoff ejecuta 3 intentos y relanza la última excepción
 [PASS] 16. Middleware FastAPI bloquea con HTTP 429, error JSON y cabecera Retry-After: 60
 [PASS] 17. Endpoints de telemetría y resiliencia /resilience/* operando con éxito
''')

    output_path = "Taller 5 - Reporte Tecnico.docx"
    doc.save(output_path)
    print(f"Documento generado exitosamente: {output_path}")


if __name__ == "__main__":
    build_document()

