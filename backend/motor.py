"""
Motor de clasificación de documentos financieros — Hotel Pacifico Sur
FastAPI backend para la demo.

Endpoints:
  POST /procesar            → recibe PDF, devuelve clasificación completa
  GET  /documentos          → lista todos los docs procesados
  GET  /configuracion       → devuelve config actual
  POST /configuracion       → guarda config desde el frontend
  GET  /aprobar/{id}        → aprueba un doc de zona amarilla
  GET  /rechazar/{id}       → rechaza un doc de zona amarilla
  GET  /solicitar_info/{id} → solicita info al proveedor
  GET  /health              → healthcheck
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import pdfplumber
import re, uuid, datetime, os, smtplib, tempfile
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="Motor Aprobación Documental — Hotel Pacifico Sur")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

# ─── Config global (editable desde el frontend sin tocar código) ─────────────
CONFIG = {
    # Cuenta remitente (Gmail que MANDA los correos)
    "email_remitente":  "",   # ej: sistema@hotelpacificosur.cl
    "email_password":   "",   # Contraseña de aplicación Gmail (16 caracteres)
    # Destinatarios
    "email_aprobador":  "",   # Recibe alertas Zona Amarilla
    "email_gerencia":   "",   # Recibe alertas Zona Roja + resumen diario
    # WhatsApp (opcional)
    "whatsapp_activo":  False,
    "whatsapp_numero":  "",
    # Umbrales
    "umbral_verde":     1_000_000,
    "umbral_rojo":      10_000_000,
    "tolerancia":       15,    # porcentaje ±
    "dias_duplicados":  90,
    # SLA
    "sla_24h": True, "sla_48h": True, "sla_72h": True, "sla_96h": True,
    # URL base para botones en emails
    "base_url": "http://localhost:8000",
}

# ─── Modelo Pydantic para recibir config desde el frontend ───────────────────
class ConfigUpdate(BaseModel):
    email_remitente:  Optional[str] = None
    email_password:   Optional[str] = None
    email_aprobador:  Optional[str] = None
    email_gerencia:   Optional[str] = None
    whatsapp_activo:  Optional[bool] = None
    whatsapp_numero:  Optional[str] = None
    umbral_verde:     Optional[int] = None
    umbral_rojo:      Optional[int] = None
    tolerancia:       Optional[float] = None
    dias_duplicados:  Optional[int] = None
    sla_24h: Optional[bool] = None
    sla_48h: Optional[bool] = None
    sla_72h: Optional[bool] = None
    sla_96h: Optional[bool] = None

# ─── Base de datos en memoria ────────────────────────────────────────────────
DOCUMENTOS = {}

# ─── Lista blanca de proveedores ─────────────────────────────────────────────
LISTA_BLANCA = {
    "12.456.789-5": {"nombre": "Distribuidora López e Hijos Ltda.", "media_historica": 650_000},
    "76.321.654-K": {"nombre": "Sistemas Técnicos SA",              "media_historica": 1_060_000},
    "9.876.543-2":  {"nombre": "Lavandería Industrial Norte Ltda.", "media_historica": 280_000},
    "15.432.100-8": {"nombre": "Suministros Gastronómicos SPA",     "media_historica": 420_000},
}

# ════════════════════════════════════════════════════════════════════════════
#  OCR — EXTRACCIÓN DE DATOS
# ════════════════════════════════════════════════════════════════════════════

def extraer_datos(ruta_pdf: str) -> dict:
    datos = {
        "proveedor": None, "rut": None, "folio": None,
        "fecha_emision": None, "fecha_vencimiento": None,
        "neto": 0, "iva": 0, "total": 0, "concepto": None,
    }
    try:
        with pdfplumber.open(ruta_pdf) as pdf:
            texto = "\n".join(p.extract_text() or "" for p in pdf.pages)

        ruts = re.findall(r"\b\d{1,2}\.\d{3}\.\d{3}-[\dKk]\b", texto)
        ruts_prov = [r for r in ruts if r != "76.543.210-8"]
        if ruts_prov:
            datos["rut"] = ruts_prov[0]

        folio_match = re.search(r"N[°o]?\s*(\d{4,})", texto)
        if folio_match:
            datos["folio"] = folio_match.group(1)

        fechas = re.findall(r"\d{2}/\d{2}/\d{4}", texto)
        if len(fechas) >= 1: datos["fecha_emision"]     = fechas[0]
        if len(fechas) >= 2: datos["fecha_vencimiento"] = fechas[1]

        montos = re.findall(r"\$\s*([\d\.]+)", texto)
        montos_num = []
        for m in montos:
            try: montos_num.append(int(m.replace(".", "")))
            except: pass

        if montos_num:
            montos_num.sort()
            datos["total"] = montos_num[-1]
            if len(montos_num) >= 3:
                datos["neto"] = montos_num[-3]
                datos["iva"]  = montos_num[-2]

        prov_match = re.search(r"PROVEEDOR\s*\n(.+)", texto)
        if prov_match:
            datos["proveedor"] = prov_match.group(1).strip()
        elif datos["rut"] and datos["rut"] in LISTA_BLANCA:
            datos["proveedor"] = LISTA_BLANCA[datos["rut"]]["nombre"]

    except Exception as ex:
        print(f"  [WARN] Error extrayendo datos: {ex}")
    return datos

# ════════════════════════════════════════════════════════════════════════════
#  MOTOR DE REGLAS
# ════════════════════════════════════════════════════════════════════════════

def clasificar(datos: dict) -> dict:
    motivos = []
    zona = "verde"
    rut   = datos.get("rut")
    total = datos.get("total", 0)

    umbral_verde = CONFIG["umbral_verde"]
    umbral_rojo  = CONFIG["umbral_rojo"]
    tolerancia   = CONFIG["tolerancia"] / 100

    if not rut or rut not in LISTA_BLANCA:
        motivos.append("Proveedor no registrado en lista blanca")
        zona = "roja"
    else:
        motivos.append(f"Proveedor verificado ({LISTA_BLANCA[rut]['nombre']})")

    if total >= umbral_rojo:
        motivos.append(f"Importe ${total:,.0f} supera umbral rojo (${umbral_rojo:,.0f})")
        zona = "roja"

    if rut and rut not in LISTA_BLANCA:
        motivos.append("Sin orden de compra vinculada")
        zona = "roja"

    if rut and rut in LISTA_BLANCA and zona != "roja":
        media     = LISTA_BLANCA[rut]["media_historica"]
        variacion = (total - media) / media if media > 0 else 0
        if abs(variacion) > tolerancia:
            motivos.append(f"Importe {variacion*100:+.0f}% sobre histórico (media: ${media:,.0f})")
            if zona == "verde": zona = "amarilla"
        else:
            motivos.append(f"Importe dentro del histórico (±{abs(variacion)*100:.0f}%)")

    if zona == "verde" and total <= umbral_verde:
        motivos.append(f"Importe dentro del umbral automático (${umbral_verde:,.0f})")

    acciones = {
        "verde":    "Aprobación automática. Contabilizado y pago programado al vencimiento.",
        "amarilla": "Notificación enviada al responsable. Decisión requerida en 24h.",
        "roja":     "Documento BLOQUEADO. Expediente completo enviado a gerencia.",
    }
    return {"zona": zona, "motivos": motivos, "accion": acciones[zona], "reglas_aplicadas": len(motivos)}

# ════════════════════════════════════════════════════════════════════════════
#  NOTIFICACIONES EMAIL
# ════════════════════════════════════════════════════════════════════════════

def email_configurado() -> bool:
    return bool(CONFIG.get("email_remitente") and CONFIG.get("email_password"))

def enviar_email(destinatario: str, asunto: str, html: str) -> bool:
    if not destinatario:
        print(f"  [EMAIL] Destinatario vacío, omitido.")
        return False
    if not email_configurado():
        print(f"\n  [EMAIL SIMULADO] → {destinatario}")
        print(f"  Asunto : {asunto}")
        print(f"  Config : ve a http://localhost:3000/configuracion y completa los datos de email\n")
        return False
    try:
        remitente = CONFIG["email_remitente"]
        msg = MIMEMultipart("alternative")
        msg["Subject"] = asunto
        msg["From"]    = f"Sistema Hotel Pacifico Sur <{remitente}>"
        msg["To"]      = destinatario
        msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.starttls()
            s.login(remitente, CONFIG["email_password"])
            s.sendmail(remitente, destinatario, msg.as_string())
        print(f"  [EMAIL] ✓ Enviado a {destinatario}")
        return True
    except Exception as ex:
        print(f"  [EMAIL ERROR] {ex}")
        return False

def email_zona_amarilla(doc_id: str, doc: dict) -> str:
    datos = doc["datos"]
    clasificacion = doc["clasificacion"]
    base = CONFIG["base_url"]
    motivos_html = "".join(f"<li>{m}</li>" for m in clasificacion["motivos"])
    return f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#333">
<div style="background:#b8860b;padding:16px 20px;border-radius:8px 8px 0 0">
  <h2 style="color:white;margin:0;font-size:16px">Alerta: Factura requiere tu aprobacion</h2>
</div>
<div style="border:1px solid #ddd;border-top:none;padding:20px;border-radius:0 0 8px 8px">
  <p style="margin:0 0 16px;color:#555">El motor detectó una anomalía y requiere tu decisión:</p>
  <div style="background:#fff8e1;border-left:4px solid #b8860b;padding:12px 16px;margin-bottom:16px;border-radius:0 6px 6px 0">
    <strong style="color:#b8860b">Anomalía detectada — Zona Amarilla</strong>
    <ul style="margin:8px 0 0;padding-left:20px;color:#5a4000;font-size:13px">{motivos_html}</ul>
  </div>
  <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:20px">
    <tr style="background:#f5f5f5"><td style="padding:8px 12px;color:#666;width:40%">Proveedor</td><td style="padding:8px 12px;font-weight:bold">{datos.get("proveedor","—")}</td></tr>
    <tr><td style="padding:8px 12px;color:#666">RUT</td><td style="padding:8px 12px">{datos.get("rut","—")}</td></tr>
    <tr style="background:#f5f5f5"><td style="padding:8px 12px;color:#666">Folio</td><td style="padding:8px 12px">{datos.get("folio","—")}</td></tr>
    <tr><td style="padding:8px 12px;color:#666">Total con IVA</td><td style="padding:8px 12px;font-weight:bold;color:#b8860b">$ {datos.get("total",0):,.0f} CLP</td></tr>
    <tr style="background:#f5f5f5"><td style="padding:8px 12px;color:#666">Vencimiento</td><td style="padding:8px 12px">{datos.get("fecha_vencimiento","—")}</td></tr>
  </table>
  <p style="font-size:13px;color:#555;margin-bottom:16px">Decide directamente desde este email — sin entrar a ninguna plataforma:</p>
  <div>
    <a href="{base}/aprobar/{doc_id}" style="display:inline-block;background:#2d7a3a;color:white;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:bold;font-size:14px;margin-right:8px">Aprobar y pagar</a>
    <a href="{base}/rechazar/{doc_id}" style="display:inline-block;background:#a02020;color:white;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:bold;font-size:14px;margin-right:8px">Rechazar</a>
    <a href="{base}/solicitar_info/{doc_id}" style="display:inline-block;background:#555;color:white;padding:12px 24px;border-radius:6px;text-decoration:none;font-size:14px">Solicitar informacion</a>
  </div>
  <p style="font-size:11px;color:#999;margin-top:20px">Sin respuesta en 24h → recordatorio automático. En 72h escala al superior.</p>
</div></body></html>"""

def email_zona_verde_resumen(docs_verdes: list) -> str:
    filas = "".join(
        f"""<tr style="{'background:#f9f9f9' if i%2 else ''}">
        <td style="padding:7px 12px">{d['datos'].get('proveedor','—')}</td>
        <td style="padding:7px 12px">N° {d['datos'].get('folio','—')}</td>
        <td style="padding:7px 12px;text-align:right;font-weight:bold">$ {d['datos'].get('total',0):,.0f}</td>
        <td style="padding:7px 12px;color:#2d7a3a;font-weight:bold">Aprobado</td></tr>"""
        for i, d in enumerate(docs_verdes)
    )
    total_dia = sum(d['datos'].get('total', 0) for d in docs_verdes)
    return f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#333">
<div style="background:#1a3a5c;padding:16px 20px;border-radius:8px 8px 0 0">
  <h2 style="color:white;margin:0;font-size:16px">Resumen diario — Documentos procesados automáticamente</h2>
  <p style="color:#adc8e8;margin:4px 0 0;font-size:13px">{datetime.date.today().strftime('%d/%m/%Y')} · Hotel Pacifico Sur</p>
</div>
<div style="border:1px solid #ddd;border-top:none;padding:20px;border-radius:0 0 8px 8px">
  <div style="display:flex;gap:16px;margin-bottom:20px">
    <div style="background:#e8f5e9;padding:12px 16px;border-radius:6px;flex:1;text-align:center">
      <div style="font-size:24px;font-weight:bold;color:#2d7a3a">{len(docs_verdes)}</div>
      <div style="font-size:12px;color:#555">Facturas aprobadas</div>
    </div>
    <div style="background:#e3f0fb;padding:12px 16px;border-radius:6px;flex:1;text-align:center">
      <div style="font-size:20px;font-weight:bold;color:#1a3a5c">$ {total_dia:,.0f}</div>
      <div style="font-size:12px;color:#555">Total procesado CLP</div>
    </div>
    <div style="background:#e8f5e9;padding:12px 16px;border-radius:6px;flex:1;text-align:center">
      <div style="font-size:24px;font-weight:bold;color:#2d7a3a">0</div>
      <div style="font-size:12px;color:#555">Intervenciones humanas</div>
    </div>
  </div>
  <table style="width:100%;border-collapse:collapse;font-size:13px">
    <tr style="background:#1a3a5c;color:white">
      <th style="padding:8px 12px;text-align:left">Proveedor</th>
      <th style="padding:8px 12px;text-align:left">Folio</th>
      <th style="padding:8px 12px;text-align:right">Total</th>
      <th style="padding:8px 12px">Estado</th>
    </tr>{filas}
  </table>
</div></body></html>"""

def email_zona_roja(doc_id: str, doc: dict) -> str:
    datos = doc["datos"]
    clasificacion = doc["clasificacion"]
    motivos_html = "".join(f"<li>{m}</li>" for m in clasificacion["motivos"])
    return f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#333">
<div style="background:#a02020;padding:16px 20px;border-radius:8px 8px 0 0">
  <h2 style="color:white;margin:0;font-size:16px">ALERTA CRITICA — Documento bloqueado automáticamente</h2>
</div>
<div style="border:1px solid #ddd;border-top:none;padding:20px;border-radius:0 0 8px 8px">
  <div style="background:#fff0f0;border-left:4px solid #a02020;padding:12px 16px;margin-bottom:16px">
    <strong style="color:#a02020">Motivos del bloqueo:</strong>
    <ul style="margin:8px 0 0;padding-left:20px;color:#6a0000;font-size:13px">{motivos_html}</ul>
  </div>
  <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:20px">
    <tr style="background:#f5f5f5"><td style="padding:8px 12px;color:#666;width:40%">Proveedor</td><td style="padding:8px 12px;font-weight:bold">{datos.get("proveedor","Desconocido")}</td></tr>
    <tr><td style="padding:8px 12px;color:#666">RUT</td><td style="padding:8px 12px">{datos.get("rut","—")}</td></tr>
    <tr style="background:#f5f5f5"><td style="padding:8px 12px;color:#666">Importe total</td><td style="padding:8px 12px;font-weight:bold;color:#a02020;font-size:15px">$ {datos.get("total",0):,.0f} CLP</td></tr>
    <tr><td style="padding:8px 12px;color:#666">Folio</td><td style="padding:8px 12px">{datos.get("folio","—")}</td></tr>
  </table>
  <p style="font-size:13px;color:#555">El pago está <strong>bloqueado</strong> hasta que gerencia revise y autorice manualmente.</p>
  <p style="font-size:11px;color:#999;margin-top:16px">ID: {doc_id} · {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
</div></body></html>"""

# ════════════════════════════════════════════════════════════════════════════
#  ENDPOINTS
# ════════════════════════════════════════════════════════════════════════════

@app.get("/health")
def health():
    return {
        "status": "ok",
        "email_configurado": email_configurado(),
        "sistema": "Motor Aprobación Documental — Hotel Pacifico Sur"
    }

@app.get("/configuracion")
def get_configuracion():
    """Devuelve la config actual (sin exponer la contraseña)."""
    cfg_publica = {k: v for k, v in CONFIG.items() if k != "email_password"}
    cfg_publica["email_password_set"] = bool(CONFIG.get("email_password"))
    return cfg_publica

@app.post("/configuracion")
def set_configuracion(body: ConfigUpdate):
    """Guarda config enviada desde el frontend."""
    update = body.model_dump(exclude_none=True)
    CONFIG.update(update)
    print(f"\n  [CONFIG] Configuración actualizada: {list(update.keys())}")
    if CONFIG.get("email_remitente") and CONFIG.get("email_password"):
        print(f"  [CONFIG] Email remitente configurado: {CONFIG['email_remitente']}")
    return {"ok": True, "email_configurado": email_configurado(), "campos_actualizados": list(update.keys())}

@app.post("/procesar")
async def procesar_documento(archivo: UploadFile = File(...)):
    if not archivo.filename.endswith(".pdf"):
        raise HTTPException(400, "Solo se aceptan archivos PDF")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(await archivo.read())
        tmp = tmp_file.name

    doc_id    = str(uuid.uuid4())[:8].upper()
    timestamp = datetime.datetime.now().isoformat()

    print(f"\n{'='*55}")
    print(f"  [1/4] Recibido: {archivo.filename} | ID: {doc_id}")

    datos         = extraer_datos(tmp)
    print(f"  [2/4] OCR completado | RUT: {datos['rut']} | Total: ${datos['total']:,.0f}")

    clasificacion = clasificar(datos)
    zona          = clasificacion["zona"]
    print(f"  [3/4] Clasificado: ZONA {zona.upper()}")

    doc = {
        "id": doc_id, "archivo": archivo.filename,
        "timestamp": timestamp, "datos": datos,
        "clasificacion": clasificacion, "estado": zona,
        "historial": [{"accion": f"Clasificado como zona {zona}", "ts": timestamp}]
    }
    DOCUMENTOS[doc_id] = doc

    aprobador = CONFIG.get("email_aprobador", "")
    gerencia  = CONFIG.get("email_gerencia", "")

    if zona == "verde":
        print(f"  [4/4] Aprobación automática. Enviando resumen.")
        html = email_zona_verde_resumen([doc])
        enviar_email(aprobador, "Resumen: 1 factura procesada automáticamente", html)
        enviar_email(gerencia,  "Resumen: 1 factura procesada automáticamente", html)

    elif zona == "amarilla":
        print(f"  [4/4] Notificación enviada al aprobador.")
        html = email_zona_amarilla(doc_id, doc)
        enviar_email(aprobador, f"Alerta: Factura requiere aprobación — {datos.get('proveedor','Proveedor')}", html)
        enviar_email(gerencia,  f"Copia: Factura en revisión — {datos.get('proveedor','')}", html)

    elif zona == "roja":
        print(f"  [4/4] BLOQUEADO. Expediente enviado a gerencia.")
        html = email_zona_roja(doc_id, doc)
        enviar_email(gerencia,  f"ALERTA CRITICA: Documento bloqueado — ${datos.get('total',0):,.0f} CLP", html)
        enviar_email(aprobador, f"Aviso: Documento bloqueado y escalado a gerencia", html)

    os.remove(tmp)
    print(f"{'='*55}\n")

    return {
        "doc_id": doc_id, "zona": zona,
        "proveedor": datos.get("proveedor"), "rut": datos.get("rut"),
        "total_clp": datos.get("total"), "folio": datos.get("folio"),
        "fecha_emision": datos.get("fecha_emision"),
        "motivos": clasificacion["motivos"], "accion": clasificacion["accion"],
        "timestamp": timestamp,
        "email_enviado": email_configurado() and bool(aprobador or gerencia),
    }

@app.get("/documentos")
def listar_documentos():
    return {"total": len(DOCUMENTOS), "documentos": list(DOCUMENTOS.values())}

@app.get("/aprobar/{doc_id}", response_class=HTMLResponse)
def aprobar(doc_id: str):
    if doc_id not in DOCUMENTOS: raise HTTPException(404, "Documento no encontrado")
    doc = DOCUMENTOS[doc_id]
    doc["estado"] = "aprobado"
    doc["historial"].append({"accion": "Aprobado por responsable", "ts": datetime.datetime.now().isoformat()})
    total = doc["datos"].get("total", 0)
    prov  = doc["datos"].get("proveedor", "—")
    return f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:500px;margin:60px auto;text-align:center">
    <div style="background:#e8f5e9;border:1px solid #a5d6a7;border-radius:12px;padding:40px">
      <div style="font-size:48px">✓</div>
      <h2 style="color:#2d7a3a">Aprobado correctamente</h2>
      <p><strong>{prov}</strong></p>
      <p style="font-size:18px;font-weight:bold;color:#1a3a5c">$ {total:,.0f} CLP</p>
      <p style="color:#555;font-size:13px">Pago programado para la fecha de vencimiento.<br>Registro de auditoría actualizado.</p>
      <p style="font-size:11px;color:#999">ID: {doc_id} · {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
    </div></body></html>"""

@app.get("/rechazar/{doc_id}", response_class=HTMLResponse)
def rechazar(doc_id: str):
    if doc_id not in DOCUMENTOS: raise HTTPException(404, "Documento no encontrado")
    doc = DOCUMENTOS[doc_id]
    doc["estado"] = "rechazado"
    doc["historial"].append({"accion": "Rechazado por responsable", "ts": datetime.datetime.now().isoformat()})
    prov = doc["datos"].get("proveedor", "—")
    return f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:500px;margin:60px auto;text-align:center">
    <div style="background:#fff0f0;border:1px solid #ef9a9a;border-radius:12px;padding:40px">
      <div style="font-size:48px">✗</div>
      <h2 style="color:#a02020">Factura rechazada</h2>
      <p><strong>{prov}</strong></p>
      <p style="color:#555;font-size:13px">El proveedor será notificado. Motivo registrado en auditoría.</p>
      <p style="font-size:11px;color:#999">ID: {doc_id} · {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
    </div></body></html>"""

@app.get("/solicitar_info/{doc_id}", response_class=HTMLResponse)
def solicitar_info(doc_id: str):
    if doc_id not in DOCUMENTOS: raise HTTPException(404, "Documento no encontrado")
    doc = DOCUMENTOS[doc_id]
    doc["estado"] = "info_solicitada"
    doc["historial"].append({"accion": "Información solicitada al proveedor", "ts": datetime.datetime.now().isoformat()})
    prov = doc["datos"].get("proveedor", "—")
    return f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:500px;margin:60px auto;text-align:center">
    <div style="background:#fff8e1;border:1px solid #ffe082;border-radius:12px;padding:40px">
      <div style="font-size:48px">?</div>
      <h2 style="color:#b8860b">Información solicitada</h2>
      <p><strong>{prov}</strong></p>
      <p style="color:#555;font-size:13px">Solicitud enviada. SLA extendido 48 horas.</p>
      <p style="font-size:11px;color:#999">ID: {doc_id} · {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
    </div></body></html>"""

if __name__ == "__main__":
    import uvicorn
    print("\n Motor de Aprobación Documental — Hotel Pacifico Sur")
    print(" ─────────────────────────────────────────────────")
    print(" API:  http://localhost:8000")
    print(" Docs: http://localhost:8000/docs")
    print(" ─────────────────────────────────────────────────")
    print(" Configura los emails en: http://localhost:3000/configuracion\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)
