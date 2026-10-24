"""
build_full_document.py
Genera un documento Word 'Parte 2.docx' completo, con diseño profesional,
diagramas embebidos, bloques de código estilizados y explicación detallada
de todos los laboratorios de Serverless & Event-Driven Architecture.
"""

import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
import os

def set_cell_background(cell, color_hex):
    """Aplica color de fondo a una celda de tabla."""
    shading_xml = f'<w:shd {nsdecls("w")} w:fill="{color_hex}"/>'
    cell._tc.get_or_add_tcPr().append(parse_xml(shading_xml))

def add_code_block(doc, code_text, language=""):
    """Crea un bloque de código estilizado con fondo gris y tipografía monoespaciada."""
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = tbl.cell(0, 0)
    set_cell_background(cell, "F4F5F7")
    cell.width = Inches(6.5)

    # Bordes de la celda
    tcPr = cell._tc.get_or_add_tcPr()
    tcBorders = parse_xml(f'''
        <w:tcBorders {nsdecls("w")}>
            <w:top w:val="single" w:sz="4" w:space="0" w:color="D1D5DB"/>
            <w:left w:val="single" w:sz="12" w:space="0" w:color="3B82F6"/>
            <w:bottom w:val="single" w:sz="4" w:space="0" w:color="D1D5DB"/>
            <w:right w:val="single" w:sz="4" w:space="0" w:color="D1D5DB"/>
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
    doc.add_paragraph() # Espacio después

def add_callout(doc, text, title="NOTA IMPORTANTE", color_hex="EFF6FF", border_hex="2563EB"):
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

    # Configuración de márgenes
    sections = doc.sections
    for section in sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.9)
        section.right_margin = Inches(0.9)

    # 1. TÍTULO PRINCIPAL
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_main = p_title.add_run("Parte 2: Taller 2 - De Microservicios a Sistemas Distribuidos Inteligentes\n")
    r_main.bold = True
    r_main.font.size = Pt(17)
    r_main.font.name = "Calibri"
    r_main.font.color.rgb = RGBColor(30, 41, 59)

    r_sub = p_title.add_run("CLASE 3: Serverless - Migración Event-Driven (EDA)")
    r_sub.bold = True
    r_sub.font.size = Pt(13)
    r_sub.font.name = "Calibri"
    r_sub.font.color.rgb = RGBColor(37, 99, 235)

    doc.add_paragraph()

    # 2. OBJETIVO
    h_obj = doc.add_heading("1. Objetivo del Taller", level=1)
    p_obj = doc.add_paragraph(
        "Migrar el microservicio síncrono catalog-service hacia una arquitectura Serverless basada en AWS Lambda "
        "y Amazon API Gateway, publicando eventos en Amazon EventBridge ante cualquier cambio en la disponibilidad "
        "o tarifa de los espacios de coworking. A su vez, desacoplar orders-service permitiendo que consuma dichos "
        "eventos mediante Amazon SQS y una Lambda Consumidora, implementando el patrón Event-Carried State Transfer "
        "para garantizar resiliencia ante caídas y prevenir fallos en cascada (resolviendo las debilidades observadas "
        "en los Labs de Chaos Engineering del Taller 1)."
    )

    # 3. ARQUITECTURA
    doc.add_heading("2. Diagrama de Arquitectura", level=1)
    
    # Imagen del diagrama
    img_path = "extracted_images/word/media/image1.png"
    if os.path.exists(img_path):
        p_img = doc.add_paragraph()
        p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_picture(img_path, width=Inches(5.8))
        p_caption = doc.add_paragraph("Ilustración 1: Flujo de eventos asíncronos y desacoplamiento con API Gateway, Lambda, EventBridge y SQS.")
        p_caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_caption.runs[0].font.size = Pt(8.5)
        p_caption.runs[0].font.italic = True
    
    doc.add_paragraph(
        "Descripción del flujo arquitectónico:\n"
        "1. API Gateway (/spaces): Expone los endpoints REST públicos para consultar y gestionar espacios.\n"
        "2. Lambda catalog-fn: Procesa la lógica de negocio del catálogo de forma serverless.\n"
        "3. Amazon EventBridge (SpaceChanged): Recibe y clasifica eventos emitidos cuando un espacio cambia de disponibilidad o precio.\n"
        "4. SQS Queue (catalog-events): Cola amortiguadora (buffer) que retiene los eventos y cuenta con una Dead Letter Queue (DLQ) para reintentos.\n"
        "5. Lambda consumer-fn: Lee mensajes de SQS de forma asíncrona y sincroniza el estado con los servicios consumidores.\n"
        "6. orders-service: Mantiene una caché local actualizada por eventos, permitiendo operar incluso si el catálogo síncrono sufre una caída total."
    )

    # 4. LAB 6
    doc.add_heading("3. LAB 6: Lambda catalog-service", level=1)
    doc.add_paragraph(
        "Objetivo: Convertir el microservicio síncrono catalog-service en una función Serverless montada en AWS Lambda "
        "y Amazon API Gateway, publicando eventos en Amazon EventBridge ante cualquier cambio en la disponibilidad o tarifa."
    )

    doc.add_heading("Archivo: lambda-catalog/requirements.txt", level=2)
    with open("lambda-catalog/requirements.txt", "r", encoding="utf-8") as f:
        add_code_block(doc, f.read())

    doc.add_heading("Archivo: lambda-catalog/handler.py", level=2)
    with open("lambda-catalog/handler.py", "r", encoding="utf-8") as f:
        add_code_block(doc, f.read())

    add_callout(
        doc,
        "La función publish_space_changed_event envía un evento con Source='coworking.catalog' y "
        "DetailType='SpaceChanged' hacia el bus de EventBridge. Contiene el estado anterior y nuevo del espacio.",
        title="PATRÓN EVENT-DRIVEN"
    )

    # 5. LAB 7
    doc.add_heading("4. LAB 7: Consumer Lambda que recibe eventos", level=1)
    doc.add_paragraph(
        "Objetivo: Implementar una función Lambda activada por lotes (batches) de Amazon SQS para procesar eventos "
        "SpaceChanged y propagarlos hacia orders-service, cerrando el ciclo de desacoplamiento Event-Driven."
    )

    doc.add_heading("4.1. Archivo: lambda-consumer/requirements.txt", level=2)
    with open("lambda-consumer/requirements.txt", "r", encoding="utf-8") as f:
        add_code_block(doc, f.read())

    doc.add_heading("4.2. Archivo: lambda-consumer/handler.py", level=2)
    with open("lambda-consumer/handler.py", "r", encoding="utf-8") as f:
        add_code_block(doc, f.read())

    add_callout(
        doc,
        "Soporta la propiedad ReportBatchItemFailures de AWS Lambda para devolver únicamente los identificadores de "
        "mensajes que fallaron en el lote, evitando reprocesamientos innecesarios de mensajes exitosos.",
        title="BUENAS PRÁCTICAS SQS BATCHING"
    )

    # SUB-SECCIONES DE INTEGRACIÓN Y DESPLIEGUE DEL LAB 7
    doc.add_heading("4.3. Infraestructura como Código: template.yaml (AWS SAM)", level=2)
    doc.add_paragraph(
        "Para desplegar de manera unificada la API Gateway, las funciones Lambda (catalog-fn y consumer-fn), "
        "la regla de EventBridge, la cola SQS catalog-events y la Dead Letter Queue (DLQ), se utiliza AWS SAM:"
    )
    with open("template.yaml", "r", encoding="utf-8") as f:
        add_code_block(doc, f.read())

    doc.add_heading("4.4. Resiliencia en orders-service (Event-Carried State Transfer)", level=2)
    doc.add_paragraph(
        "En el Taller 1 (Lab 4 y 5), la caída del catálogo provocaba un error HTTP 503 inmediato en orders-service. "
        "En este laboratorio actualizamos orders-service incorporando un webhook receptor (/events/space-changed), "
        "una caché local sincronizada por eventos y un lector tolerante (Tolerant Reader)."
    )
    with open("orders-service/main.py", "r", encoding="utf-8") as f:
        add_code_block(doc, f.read())

    add_callout(
        doc,
        "Al intentar crear una orden (POST /orders), si el catálogo síncrono no responde, orders-service recurre a "
        "la caché local alimentada por eventos y completa la reserva exitosamente (HTTP 201 Created), eliminando el "
        "punto único de fallo síncrono.",
        title="SOLUCIÓN DEFINITIVA AL CHAOS LAB 4"
    )

    doc.add_heading("4.5. Guía de Despliegue (AWS SAM CLI y Opciones Cloud)", level=2)
    sam_deploy_cmds = """# 1. Instalar AWS SAM CLI
pip install aws-sam-cli

# 2. Compilar dependencias y empaquetar artefactos
sam build

# 3. Despliegue guiado a AWS (primera vez, genera samconfig.toml)
sam deploy --guided

# 4. Despliegues posteriores automatizados
sam deploy

# 5. Probar endpoints de API Gateway localmente
sam local start-api --port 8001"""
    add_code_block(doc, sam_deploy_cmds)

    # 6. PRUEBAS Y VALIDACIÓN
    doc.add_heading("4.6. Pruebas Automatizadas y Simulación Local", level=2)
    doc.add_paragraph(
        "Para validar el funcionamiento sin requerir una cuenta de AWS activa con tarjeta de crédito, se diseñaron "
        "dos mecanismos: una suite de pruebas automatizadas (test_serverless_pipeline.py) y un script interactivo "
        "de simulación en consola (simulate_event_flow.py)."
    )

    doc.add_heading("Ejecución de la suite de pruebas automatizadas:", level=2)
    test_run_cmds = """# Ejecutar los 5 tests de integración de la arquitectura Serverless
python test_serverless_pipeline.py

# Resultado esperado:
# [PASS] LAB 6: catalog-fn GET /spaces responde 200 OK con catálogo completo
# [PASS] LAB 6: catalog-fn actualiza espacio y emite evento SpaceChanged a EventBridge
# [PASS] LAB 7: consumer-fn procesa lote de SQS y entrega evento a orders-service
# [PASS] LAB 8: orders-service sincroniza caché local mediante webhook
# [PASS] Resiliencia EDA: orders-service completa orden en modo Fallback con catálogo caído
# ----------------------------------------------------------------------
# Ran 5 tests in 0.176s - OK"""
    add_code_block(doc, test_run_cmds)

    doc.add_heading("Demostración interactiva en consola:", level=2)
    sim_cmds = """# Ejecutar simulación paso a paso de todo el flujo
python scripts/simulate_event_flow.py"""
    add_code_block(doc, sim_cmds)

    doc.add_heading("Orquestación local con Docker Compose y LocalStack:", level=2)
    compose_cmds = """# Levantar LocalStack (EventBridge + SQS + Lambda) junto con orders-service
docker-compose -f docker-compose.serverless.yml up --build -d"""
    add_code_block(doc, compose_cmds)

    # 9. CONCLUSIÓN Y BENEFICIOS ARQUITECTÓNICOS
    doc.add_heading("8. Cuadro Comparativo de Arquitectura", level=1)
    
    table = doc.add_table(rows=5, cols=3)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    headers = ["Criterio", "Taller 1: Microservicios Síncronos", "Taller 2: Serverless Event-Driven"]
    for i, h in enumerate(headers):
        cell = table.cell(0, i)
        set_cell_background(cell, "1E293B")
        p = cell.paragraphs[0]
        r = p.add_run(h)
        r.bold = True
        r.font.name = "Calibri"
        r.font.size = Pt(9.5)
        r.font.color.rgb = RGBColor(255, 255, 255)

    data = [
        ("Comunicación", "Peticiones HTTP síncronas bloqueantes", "Eventos asíncronos en EventBridge + SQS"),
        ("Tolerancia a fallos", "Si el catálogo cae, orders-service colapsa (503)", "Desacoplamiento temporal; órdenes operan con caché"),
        ("Escalabilidad", "Manual o por contenedores fijos (Docker Compose)", "Automática e instantánea por petición (AWS Lambda)"),
        ("Costos", "Servidores/contenedores 24/7 encendidos", "Pay-per-use (Cero costo si no hay peticiones)")
    ]

    for row_idx, row_data in enumerate(data, start=1):
        bg = "F8FAFC" if row_idx % 2 == 1 else "FFFFFF"
        for col_idx, text in enumerate(row_data):
            cell = table.cell(row_idx, col_idx)
            set_cell_background(cell, bg)
            p = cell.paragraphs[0]
            r = p.add_run(text)
            r.font.name = "Calibri"
            r.font.size = Pt(9)
            if col_idx == 0:
                r.bold = True

    doc.save("Parte 2.docx")
    print("Documento Word 'Parte 2.docx' generado exitosamente!")

if __name__ == "__main__":
    build_document()
