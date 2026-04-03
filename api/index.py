"""
Backend FastAPI — Renaissance Santiago Hotel
Stateless: no RAM storage, no files.
El frontend guarda todo en localStorage.
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import pdfplumber, re, uuid, datetime, smtplib, tempfile, os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="Renaissance Santiago — Motor de Aprobación")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

# ── Lista blanca de proveedores ───────────────────────────────────────────────
LISTA_BLANCA = {
    "12.456.789-5": {"nombre": "Distribuidora López e Hijos Ltda.", "media": 800_000},
    "76.321.654-K": {"nombre": "Sistemas Técnicos SA",              "media": 1_060_000},
    "9.876.543-2":  {"nombre": "Lavandería Industrial Norte Ltda.", "media": 280_000},
    "15.432.100-8": {"nombre": "Suministros Gastronómicos SPA",     "media": 420_000},
}

UMBRAL_VERDE    = 1_000_000
UMBRAL_ROJO     = 10_000_000
TOLERANCIA      = 0.15
RUT_HOTEL       = "96.534.720-8"

# ════════════════════════════════════════════════════════════════════════════
#  OCR — leer el PDF
# ════════════════════════════════════════════════════════════════════════════
def extraer_datos(ruta: str) -> dict:
    datos = {"proveedor": None, "rut": None, "folio": None,
             "fecha_emision": None, "fecha_vencimiento": None,
             "neto": 0, "iva": 0, "total": 0}
    try:
        with pdfplumber.open(ruta) as pdf:
            texto = "\n".join(p.extract_text() or "" for p in pdf.pages)

        ruts = re.findall(r"\b\d{1,2}\.\d{3}\.\d{3}-[\dKk]\b", texto)
        ruts_prov = [r for r in ruts if r != RUT_HOTEL]
        if ruts_prov:
            datos["rut"] = ruts_prov[0]

        folio = re.search(r"N[°o]?\s*(\d{4,})", texto)
        if folio:
            datos["folio"] = folio.group(1)

        fechas = re.findall(r"\d{2}/\d{2}/\d{4}", texto)
        if len(fechas) >= 1: datos["fecha_emision"]     = fechas[0]
        if len(fechas) >= 2: datos["fecha_vencimiento"] = fechas[1]

        montos = re.findall(r"\$\s*([\d\.]+)", texto)
        nums = sorted([int(m.replace(".", "")) for m in montos
                       if m.replace(".", "").isdigit()])
        if nums:
            datos["total"] = nums[-1]
            if len(nums) >= 3:
                datos["neto"] = nums[-3]
                datos["iva"]  = nums[-2]

        prov = re.search(r"PROVEEDOR[^:\n]*\n(.+)", texto)
        if prov:
            datos["proveedor"] = prov.group(1).strip()
        elif datos["rut"] and datos["rut"] in LISTA_BLANCA:
            datos["proveedor"] = LISTA_BLANCA[datos["rut"]]["nombre"]

    except Exception as ex:
        print(f"[OCR] Error: {ex}")
    return datos

# ════════════════════════════════════════════════════════════════════════════
#  MOTOR DE REGLAS — clasificar en zona
# ════════════════════════════════════════════════════════════════════════════
def clasificar(datos: dict) -> dict:
    motivos, zona = [], "verde"
    rut   = datos.get("rut")
    total = datos.get("total", 0)

    if not rut or rut not in LISTA_BLANCA:
        motivos.append("Proveedor no registrado en lista blanca")
        zona = "roja"
    else:
        motivos.append(f"Proveedor verificado ({LISTA_BLANCA[rut]['nombre']})")

    if total >= UMBRAL_ROJO:
        motivos.append(f"Importe supera umbral crítico (${UMBRAL_ROJO:,.0f} CLP)")
        zona = "roja"

    if rut and rut in LISTA_BLANCA and zona != "roja":
        media = LISTA_BLANCA[rut]["media"]
        var   = (total - media) / media if media > 0 else 0
        if abs(var) > TOLERANCIA:
            motivos.append(f"Importe {var*100:+.0f}% sobre histórico del proveedor (media ${media:,.0f})")
            zona = "amarilla"
        else:
            motivos.append(f"Importe dentro del histórico (±{abs(var)*100:.0f}%)")

    if zona == "verde" and total <= UMBRAL_VERDE:
        motivos.append(f"Importe dentro del umbral automático (${UMBRAL_VERDE:,.0f})")

    acciones = {
        "verde":    "Aprobación automática. Pago programado al vencimiento.",
        "amarilla": "Notificación enviada al responsable. Decisión en 24h.",
        "roja":     "Documento BLOQUEADO. Expediente enviado a gerencia.",
    }
    return {"zona": zona, "motivos": motivos, "accion": acciones[zona]}

# ════════════════════════════════════════════════════════════════════════════
#  EMAIL — stateless, recibe config por request
# ════════════════════════════════════════════════════════════════════════════
def enviar_email(destinatario: str, asunto: str, html: str,
                 remitente: str, password: str) -> bool:
    if not destinatario or not remitente or not password:
        print(f"  [EMAIL] Sin config — omitido")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = asunto
        msg["From"]    = f"Renaissance Santiago <{remitente}>"
        msg["To"]      = destinatario
        msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.starttls()
            s.login(remitente, password)
            s.sendmail(remitente, destinatario, msg.as_string())
        print(f"  [EMAIL] ✓ Enviado a {destinatario}")
        return True
    except Exception as ex:
        print(f"  [EMAIL] Error: {ex}")
        return False

# ── Templates email ───────────────────────────────────────────────────────────
def html_amarilla(doc_id: str, datos: dict, motivos: list, base_url: str) -> str:
    m_html = "".join(f"<li>{m}</li>" for m in motivos)
    return f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px">
<div style="background:#b8860b;padding:16px 20px;border-radius:8px 8px 0 0">
  <h2 style="color:white;margin:0">Alerta: Factura requiere aprobación</h2>
</div>
<div style="border:1px solid #ddd;border-top:none;padding:20px;border-radius:0 0 8px 8px">
  <div style="background:#fff8e1;border-left:4px solid #b8860b;padding:12px;margin-bottom:16px">
    <ul style="margin:0;padding-left:20px;color:#5a4000">{m_html}</ul>
  </div>
  <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:20px">
    <tr style="background:#f5f5f5"><td style="padding:8px;color:#666;width:40%">Proveedor</td><td style="padding:8px;font-weight:bold">{datos.get("proveedor","—")}</td></tr>
    <tr><td style="padding:8px;color:#666">RUT</td><td style="padding:8px">{datos.get("rut","—")}</td></tr>
    <tr style="background:#f5f5f5"><td style="padding:8px;color:#666">Folio</td><td style="padding:8px">{datos.get("folio","—")}</td></tr>
    <tr><td style="padding:8px;color:#666">Total con IVA</td><td style="padding:8px;font-weight:bold;color:#b8860b">$ {datos.get("total",0):,.0f} CLP</td></tr>
  </table>
  <div>
    <a href="{base_url}/api/aprobar/{doc_id}" style="display:inline-block;background:#2d7a3a;color:white;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:bold;margin-right:8px">✓ Aprobar</a>
    <a href="{base_url}/api/rechazar/{doc_id}" style="display:inline-block;background:#a02020;color:white;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:bold">✗ Rechazar</a>
  </div>
  <p style="font-size:11px;color:#999;margin-top:16px">Sin respuesta en 24h → recordatorio automático.</p>
</div></body></html>"""

def html_roja(doc_id: str, datos: dict, motivos: list) -> str:
    m_html = "".join(f"<li>{m}</li>" for m in motivos)
    return f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px">
<div style="background:#a02020;padding:16px 20px;border-radius:8px 8px 0 0">
  <h2 style="color:white;margin:0">ALERTA CRÍTICA — Documento bloqueado</h2>
</div>
<div style="border:1px solid #ddd;border-top:none;padding:20px;border-radius:0 0 8px 8px">
  <div style="background:#fff0f0;border-left:4px solid #a02020;padding:12px;margin-bottom:16px">
    <ul style="margin:0;padding-left:20px;color:#6a0000">{m_html}</ul>
  </div>
  <table style="width:100%;border-collapse:collapse;font-size:13px">
    <tr style="background:#f5f5f5"><td style="padding:8px;color:#666;width:40%">Proveedor</td><td style="padding:8px;font-weight:bold">{datos.get("proveedor","Desconocido")}</td></tr>
    <tr><td style="padding:8px;color:#666">RUT</td><td style="padding:8px">{datos.get("rut","—")}</td></tr>
    <tr style="background:#f5f5f5"><td style="padding:8px;color:#666">Total</td><td style="padding:8px;font-weight:bold;color:#a02020;font-size:15px">$ {datos.get("total",0):,.0f} CLP</td></tr>
  </table>
  <p style="margin-top:16px;font-size:13px">El pago está <strong>bloqueado</strong>. ID: {doc_id}</p>
</div></body></html>"""

def html_verde(datos: dict) -> str:
    return f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px">
<div style="background:#2d7a3a;padding:16px 20px;border-radius:8px 8px 0 0">
  <h2 style="color:white;margin:0">Resumen — Factura procesada automáticamente</h2>
</div>
<div style="border:1px solid #ddd;border-top:none;padding:20px;border-radius:0 0 8px 8px">
  <p style="color:#555">La siguiente factura fue aprobada y el pago programado automáticamente:</p>
  <table style="width:100%;border-collapse:collapse;font-size:13px">
    <tr style="background:#f5f5f5"><td style="padding:8px;color:#666">Proveedor</td><td style="padding:8px;font-weight:bold">{datos.get("proveedor","—")}</td></tr>
    <tr><td style="padding:8px;color:#666">Total</td><td style="padding:8px;font-weight:bold;color:#2d7a3a">$ {datos.get("total",0):,.0f} CLP</td></tr>
    <tr style="background:#f5f5f5"><td style="padding:8px;color:#666">Vencimiento</td><td style="padding:8px">{datos.get("fecha_vencimiento","—")}</td></tr>
  </table>
  <p style="margin-top:12px;color:#2d7a3a;font-size:13px">✓ Intervención humana: ninguna</p>
</div></body></html>"""

# ════════════════════════════════════════════════════════════════════════════
#  ENDPOINTS
# ════════════════════════════════════════════════════════════════════════════

@app.get("/api/health")
def health():
    return {"status": "ok", "sistema": "Renaissance Santiago — Motor de Aprobación"}

class ProcesarConfig(BaseModel):
    email_remitente:  Optional[str] = ""
    email_password:   Optional[str] = ""
    email_aprobador:  Optional[str] = ""
    email_gerencia:   Optional[str] = ""
    base_url:         Optional[str] = "https://hotel-demo-ivory.vercel.app"

@app.post("/api/procesar")
async def procesar_documento(
    archivo: UploadFile = File(...),
    email_remitente:  str = "",
    email_password:   str = "",
    email_aprobador:  str = "",
    email_gerencia:   str = "",
    base_url:         str = "https://hotel-demo-ivory.vercel.app",
):
    if not archivo.filename or not archivo.filename.endswith(".pdf"):
        raise HTTPException(400, "Solo se aceptan archivos PDF")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
        f.write(await archivo.read())
        tmp = f.name

    doc_id    = str(uuid.uuid4())[:8].upper()
    timestamp = datetime.datetime.now().isoformat()

    try:
        datos         = extraer_datos(tmp)
        clasificacion = clasificar(datos)
        zona          = clasificacion["zona"]

        print(f"\n[{doc_id}] {archivo.filename} | RUT:{datos['rut']} | ${datos['total']:,.0f} → ZONA {zona.upper()}")

        email_enviado = False
        if zona == "verde":
            email_enviado = enviar_email(
                email_aprobador,
                "Resumen: factura procesada automáticamente",
                html_verde(datos),
                email_remitente, email_password
            )
        elif zona == "amarilla":
            email_enviado = enviar_email(
                email_aprobador,
                f"⚠ Alerta: Factura requiere aprobación — {datos.get('proveedor','')}",
                html_amarilla(doc_id, datos, clasificacion["motivos"], base_url),
                email_remitente, email_password
            )
        elif zona == "roja":
            email_enviado = enviar_email(
                email_gerencia,
                f"🔴 CRÍTICO: Documento bloqueado — ${datos.get('total',0):,.0f} CLP",
                html_roja(doc_id, datos, clasificacion["motivos"]),
                email_remitente, email_password
            )

        return {
            "doc_id":        doc_id,
            "zona":          zona,
            "proveedor":     datos.get("proveedor"),
            "rut":           datos.get("rut"),
            "total_clp":     datos.get("total", 0),
            "folio":         datos.get("folio"),
            "fecha_emision": datos.get("fecha_emision"),
            "fecha_vencimiento": datos.get("fecha_vencimiento"),
            "motivos":       clasificacion["motivos"],
            "accion":        clasificacion["accion"],
            "timestamp":     timestamp,
            "archivo":       archivo.filename,
            "estado":        zona,
            "email_enviado": email_enviado,
        }
    finally:
        os.unlink(tmp)

@app.get("/api/aprobar/{doc_id}")
async def aprobar_doc(doc_id: str):
    from fastapi.responses import HTMLResponse
    return HTMLResponse(f"""<!DOCTYPE html><html><body style="font-family:Arial;max-width:500px;margin:60px auto;text-align:center">
    <div style="background:#e8f5e9;border:1px solid #a5d6a7;border-radius:12px;padding:40px">
      <div style="font-size:48px">✓</div><h2 style="color:#2d7a3a">Aprobado correctamente</h2>
      <p style="color:#555">Pago programado al vencimiento. Auditoría actualizada.</p>
      <p style="font-size:11px;color:#999">ID: {doc_id} · {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
    </div></body></html>""")

@app.get("/api/rechazar/{doc_id}")
async def rechazar_doc(doc_id: str):
    from fastapi.responses import HTMLResponse
    return HTMLResponse(f"""<!DOCTYPE html><html><body style="font-family:Arial;max-width:500px;margin:60px auto;text-align:center">
    <div style="background:#fff0f0;border:1px solid #ef9a9a;border-radius:12px;padding:40px">
      <div style="font-size:48px">✗</div><h2 style="color:#a02020">Factura rechazada</h2>
      <p style="color:#555">Proveedor notificado. Motivo registrado.</p>
      <p style="font-size:11px;color:#999">ID: {doc_id} · {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
    </div></body></html>""")

# ── IA ────────────────────────────────────────────────────────────────────────
class IARequest(BaseModel):
    gemini_api_key: Optional[str] = ""
    doc_data:       Optional[dict] = None
    zona:           Optional[str] = ""
    motivos:        Optional[list] = []
    pregunta:       Optional[str] = ""
    documentos:     Optional[list] = []

def llamar_gemini(prompt: str, api_key: str) -> str:
    if not api_key:
        return ""
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        resp   = client.models.generate_content(
            model="gemini-1.5-flash", contents=prompt)
        return resp.text.strip()
    except Exception as ex:
        print(f"[IA] Error: {ex}")
        return ""

@app.post("/api/ia/analizar")
async def ia_analizar(body: IARequest):
    if not body.gemini_api_key:
        return {"analisis": "", "disponible": False}
    datos   = body.doc_data or {}
    motivos = "\n".join(f"- {m}" for m in (body.motivos or []))
    prompt  = f"""Eres el sistema financiero del Renaissance Santiago Hotel.
Analizaste una factura con estos datos:
Proveedor: {datos.get("proveedor","?")} | RUT: {datos.get("rut","?")}
Total: ${datos.get("total_clp",0):,.0f} CLP | Zona: {body.zona}
Motivos del motor de reglas:
{motivos}

Escribe UN párrafo (máximo 4 oraciones) en español para el jefe de finanzas:
qué significa esta zona, por qué importa y qué acción recomiendas.
Sin markdown, sin asteriscos, solo texto."""
    analisis = llamar_gemini(prompt, body.gemini_api_key)
    return {"analisis": analisis, "disponible": bool(analisis)}

@app.post("/api/ia/resumen")
async def ia_resumen(body: IARequest):
    if not body.gemini_api_key:
        return {"resumen": "", "disponible": False}
    datos  = body.doc_data or {}
    prompt = f"""Resume en 2 oraciones para directivos del Renaissance Santiago Hotel:
Proveedor: {datos.get("proveedor","?")} | Total: ${datos.get("total_clp",0):,.0f} CLP | Zona: {body.zona}
Sin markdown. Solo texto natural en español."""
    resumen = llamar_gemini(prompt, body.gemini_api_key)
    return {"resumen": resumen, "disponible": bool(resumen)}

@app.post("/api/ia/chat")
async def ia_chat(body: IARequest):
    if not body.gemini_api_key:
        return {"respuesta": "Configura la API key de Gemini en Configuración.", "disponible": False}
    if not body.pregunta:
        raise HTTPException(400, "Pregunta vacía")
    docs_txt = ""
    for d in (body.documentos or [])[-20:]:
        docs_txt += f"- {d.get('proveedor','?')} | ${d.get('total_clp',0):,.0f} CLP | Zona {d.get('zona','')} | {str(d.get('timestamp',''))[:10]}\n"
    prompt = f"""Eres el asistente financiero del Renaissance Santiago Hotel.
Historial de facturas:
{docs_txt or 'Sin facturas registradas.'}
Pregunta: "{body.pregunta}"
Responde en máximo 4 oraciones en español, con datos concretos si los hay. Sin markdown."""
    respuesta = llamar_gemini(prompt, body.gemini_api_key)
    return {"respuesta": respuesta, "disponible": True}

# ── Flujo 2: emisión ─────────────────────────────────────────────────────────
DEPARTAMENTOS = [
    {"id": "gerencia_general",  "nombre": "Gerencia General"},
    {"id": "finanzas",          "nombre": "Finanzas y Contabilidad"},
    {"id": "rrhh",              "nombre": "Recursos Humanos"},
    {"id": "marketing",         "nombre": "Marketing y Ventas"},
    {"id": "operaciones",       "nombre": "Operaciones"},
    {"id": "fb_manager",        "nombre": "F&B Manager"},
    {"id": "revenue",           "nombre": "Revenue Management"},
    {"id": "eventos",           "nombre": "Eventos y Banquetes"},
    {"id": "compras",           "nombre": "Compras y Proveedores"},
    {"id": "legal",             "nombre": "Legal y Cumplimiento"},
    {"id": "ti",                "nombre": "Tecnología (TI)"},
    {"id": "mantenimiento",     "nombre": "Mantenimiento"},
    {"id": "housekeeping",      "nombre": "Housekeeping"},
    {"id": "recepcion",         "nombre": "Recepción y Front Desk"},
    {"id": "director_hotel",    "nombre": "Director del Hotel"},
]

@app.get("/api/emision/departamentos")
def listar_departamentos():
    return {"departamentos": DEPARTAMENTOS}

class AprobadorEmision(BaseModel):
    area_id: str
    nombre:  str
    email:   str
    orden:   int

class EmisionInput(BaseModel):
    cliente:        str
    rut_cliente:    str
    concepto:       str
    monto_neto:     int
    descripcion:    Optional[str] = ""
    aprobadores:    list
    email_remitente: Optional[str] = ""
    email_password:  Optional[str] = ""
    base_url:        Optional[str] = "https://hotel-demo-ivory.vercel.app"

@app.post("/api/emision/crear")
async def crear_emision(body: EmisionInput):
    if not body.aprobadores:
        raise HTTPException(400, "Define al menos un aprobador")
    factura_id = "EM-" + str(uuid.uuid4())[:6].upper()
    iva   = round(body.monto_neto * 0.19)
    total = body.monto_neto + iva
    aprobadores = sorted(body.aprobadores, key=lambda x: x.get("orden", 0))

    # Notificar al primer aprobador
    primer = aprobadores[0] if aprobadores else None
    email_enviado = False
    if primer and primer.get("email"):
        n_total = len(aprobadores)
        html = f"""<!DOCTYPE html><html><body style="font-family:Arial;max-width:600px;margin:0 auto;padding:20px">
<div style="background:#1a3a5c;padding:16px 20px;border-radius:8px 8px 0 0">
  <h2 style="color:white;margin:0">Aprobación requerida — {primer['nombre']}</h2>
  <p style="color:#adc8e8;margin:4px 0 0">Etapa 1 de {n_total} · Renaissance Santiago Hotel</p>
</div>
<div style="border:1px solid #ddd;border-top:none;padding:20px;border-radius:0 0 8px 8px">
  <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px">
    <tr style="background:#f5f5f5"><td style="padding:8px;color:#666">Cliente</td><td style="padding:8px;font-weight:bold">{body.cliente}</td></tr>
    <tr><td style="padding:8px;color:#666">Concepto</td><td style="padding:8px">{body.concepto}</td></tr>
    <tr style="background:#f5f5f5"><td style="padding:8px;color:#666">Monto neto</td><td style="padding:8px">$ {body.monto_neto:,.0f} CLP</td></tr>
    <tr><td style="padding:8px;color:#666">Total con IVA</td><td style="padding:8px;font-weight:bold;color:#1a3a5c;font-size:15px">$ {total:,.0f} CLP</td></tr>
  </table>
  <div>
    <a href="{body.base_url}/api/emision/aprobar/{factura_id}/{primer['area_id']}" style="display:inline-block;background:#2d7a3a;color:white;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:bold;margin-right:8px">Aprobar</a>
    <a href="{body.base_url}/api/emision/rechazar/{factura_id}/{primer['area_id']}" style="display:inline-block;background:#a02020;color:white;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:bold">Rechazar</a>
  </div>
</div></body></html>"""
        email_enviado = enviar_email(
            primer["email"],
            f"[{primer['nombre']}] Aprobación requerida — {body.concepto}",
            html, body.email_remitente, body.email_password
        )

    return {
        "factura_id":   factura_id,
        "estado":       "pendiente",
        "cliente":      body.cliente,
        "rut_cliente":  body.rut_cliente,
        "concepto":     body.concepto,
        "monto_neto":   body.monto_neto,
        "iva":          iva,
        "total":        total,
        "aprobadores":  aprobadores,
        "aprobaciones": {},
        "area_pendiente": primer["nombre"] if primer else None,
        "progreso":     0,
        "total_etapas": len(aprobadores),
        "timestamp":    datetime.datetime.now().isoformat(),
        "email_enviado": email_enviado,
    }

@app.get("/api/emision/aprobar/{factura_id}/{area_id}")
async def aprobar_emision(factura_id: str, area_id: str):
    from fastapi.responses import HTMLResponse
    return HTMLResponse(f"""<!DOCTYPE html><html><body style="font-family:Arial;max-width:500px;margin:60px auto;text-align:center">
    <div style="background:#e8f5e9;border:1px solid #a5d6a7;border-radius:12px;padding:40px">
      <div style="font-size:48px">✓</div><h2 style="color:#2d7a3a">Etapa aprobada</h2>
      <p style="color:#555">La solicitud avanzó a la siguiente etapa del flujo.</p>
      <p style="font-size:11px;color:#999">{factura_id} · {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
    </div></body></html>""")

@app.get("/api/emision/rechazar/{factura_id}/{area_id}")
async def rechazar_emision(factura_id: str, area_id: str):
    from fastapi.responses import HTMLResponse
    return HTMLResponse(f"""<!DOCTYPE html><html><body style="font-family:Arial;max-width:500px;margin:60px auto;text-align:center">
    <div style="background:#fff0f0;border:1px solid #ef9a9a;border-radius:12px;padding:40px">
      <div style="font-size:48px">✗</div><h2 style="color:#a02020">Flujo detenido</h2>
      <p style="color:#555">La factura fue rechazada. El equipo de finanzas fue notificado.</p>
      <p style="font-size:11px;color:#999">{factura_id} · {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
    </div></body></html>""")
