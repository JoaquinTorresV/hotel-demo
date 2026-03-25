"""
Motor de clasificación de documentos financieros — Hotel
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
import re, uuid, datetime, os, smtplib, tempfile, json, pathlib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pydantic import BaseModel
from typing import Optional

# Persistencia JSON config
CONFIG_FILE = pathlib.Path("config.json")

def cargar_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception as ex:
            print(f"  [CONFIG] Error leyendo config.json: {ex}")
    return {}

def guardar_config(cfg: dict):
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [CONFIG] Guardado en {CONFIG_FILE.resolve()}")
    except Exception as ex:
        print(f"  [CONFIG] Error guardando config.json: {ex}")

app = FastAPI(title="Motor Aprobación Documental — Hotel")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

# ─── Config global (editable desde el frontend sin tocar código) ─────────────
CONFIG = {
    # Cuenta remitente (Gmail que MANDA los correos)
    "email_remitente":  "",   # ej: sistema@renaissancesantiago.cl
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
    "gemini_api_key": "",   # API key gratuita: aistudio.google.com
}

# Cargar config guardada al arrancar (persiste entre reinicios)
CONFIG.update(cargar_config())

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
    gemini_api_key:   Optional[str] = None

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
        ruts_prov = [r for r in ruts if r != "96.534.720-8"]
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
        msg["From"]    = f"Sistema Hotel <{remitente}>"
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
  <p style="color:#adc8e8;margin:4px 0 0;font-size:13px">{datetime.date.today().strftime('%d/%m/%Y')} · Hotel</p>
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
        "sistema": "Motor Aprobación Documental — Hotel"
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
    guardar_config(CONFIG)  # persiste en config.json
    print(f"\n  [CONFIG] Actualizado y guardado: {list(update.keys())}")
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
    # Aplanar estructura para que el frontend reciba campos directos
    docs_planos = []
    for doc in DOCUMENTOS.values():
        datos = doc.get("datos", {})
        clasificacion = doc.get("clasificacion", {})
        docs_planos.append({
            "doc_id":        doc["id"],
            "archivo":       doc.get("archivo", ""),
            "timestamp":     doc["timestamp"],
            "estado":        doc.get("estado", ""),
            "zona":          doc.get("estado", ""),
            # Campos de datos (antes estaban anidados en .datos)
            "proveedor":     datos.get("proveedor"),
            "rut":           datos.get("rut"),
            "folio":         datos.get("folio"),
            "total_clp":     datos.get("total", 0),
            "fecha_emision":       datos.get("fecha_emision"),
            "fecha_vencimiento":   datos.get("fecha_vencimiento"),
            # Clasificacion
            "motivos":   clasificacion.get("motivos", []),
            "accion":    clasificacion.get("accion", ""),
            "zona_label": clasificacion.get("zona", doc.get("estado", "")),
            "email_enviado": True,
            # Historial
            "historial":  doc.get("historial", []),
        })
    return {"total": len(docs_planos), "documentos": docs_planos}

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



# ════════════════════════════════════════════════════════════════════════════
#  FLUJO 2 — FACTURAS QUE EL HOTEL EMITE (aprobación interna 3 etapas)
#  Completamente separado del Flujo 1 (facturas que el hotel RECIBE)
# ════════════════════════════════════════════════════════════════════════════

# Base de datos en memoria para facturas emitidas
FACTURAS_EMITIDAS = {}

AREAS = [
    {"id": "rrhh",      "nombre": "Recursos Humanos",  "orden": 1},
    {"id": "marketing", "nombre": "Marketing",          "orden": 2},
    {"id": "gerencia",  "nombre": "Gerencia General",   "orden": 3},
]

class FacturaEmitidaInput(BaseModel):
    cliente:        str
    rut_cliente:    str
    concepto:       str
    monto_neto:     int
    descripcion:    Optional[str] = ""
    email_rrhh:     Optional[str] = ""
    email_marketing: Optional[str] = ""
    email_gerencia_aprobador: Optional[str] = ""

def email_aprobacion_interna(factura_id: str, factura: dict, area: dict) -> str:
    base = CONFIG["base_url"]
    iva = round(factura["monto_neto"] * 0.19)
    total = factura["monto_neto"] + iva
    return f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#333">
<div style="background:#1a3a5c;padding:16px 20px;border-radius:8px 8px 0 0">
  <h2 style="color:white;margin:0;font-size:16px">Solicitud de aprobacion — {area["nombre"]}</h2>
  <p style="color:#adc8e8;margin:4px 0 0;font-size:13px">Renaissance Santiago Hotel · Factura a emitir</p>
</div>
<div style="border:1px solid #ddd;border-top:none;padding:20px;border-radius:0 0 8px 8px">
  <p style="font-size:13px;color:#555;margin:0 0 16px">Se requiere tu aprobacion antes de emitir esta factura al cliente:</p>
  <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:20px">
    <tr style="background:#f5f5f5"><td style="padding:8px 12px;color:#666;width:40%">Cliente</td><td style="padding:8px 12px;font-weight:bold">{factura["cliente"]}</td></tr>
    <tr><td style="padding:8px 12px;color:#666">RUT cliente</td><td style="padding:8px 12px">{factura["rut_cliente"]}</td></tr>
    <tr style="background:#f5f5f5"><td style="padding:8px 12px;color:#666">Concepto</td><td style="padding:8px 12px">{factura["concepto"]}</td></tr>
    <tr><td style="padding:8px 12px;color:#666">Monto neto</td><td style="padding:8px 12px">$ {factura["monto_neto"]:,.0f} CLP</td></tr>
    <tr style="background:#f5f5f5"><td style="padding:8px 12px;color:#666">IVA (19%)</td><td style="padding:8px 12px">$ {iva:,.0f} CLP</td></tr>
    <tr><td style="padding:8px 12px;color:#666">Total a cobrar</td><td style="padding:8px 12px;font-weight:bold;color:#1a3a5c;font-size:15px">$ {total:,.0f} CLP</td></tr>
  </table>
  <p style="font-size:13px;color:#555;margin-bottom:16px">Etapa <strong>{area["orden"]} de {len(AREAS)}</strong> — {area["nombre"]}</p>
  <div>
    <a href="{base}/emision/aprobar/{factura_id}/{area["id"]}" style="display:inline-block;background:#2d7a3a;color:white;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:bold;font-size:14px;margin-right:8px">Aprobar</a>
    <a href="{base}/emision/rechazar/{factura_id}/{area["id"]}" style="display:inline-block;background:#a02020;color:white;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:bold;font-size:14px">Rechazar</a>
  </div>
  <p style="font-size:11px;color:#999;margin-top:16px">Sin respuesta en 24h se enviara recordatorio automatico.</p>
</div></body></html>"""

def siguiente_area_pendiente(factura: dict):
    """Devuelve la siguiente área que falta aprobar, o None si todas aprobaron."""
    aprobaciones = factura.get("aprobaciones", {})
    monto_neto = factura.get("monto_neto", 0)
    for area in AREAS:
        # Gerencia solo requerida si monto > 5.000.000
        if area["id"] == "gerencia" and monto_neto <= 5_000_000:
            continue
        if aprobaciones.get(area["id"]) != "aprobado":
            return area
    return None

def notificar_siguiente_area(factura_id: str, factura: dict):
    """Envía email a la siguiente área pendiente de aprobación."""
    area = siguiente_area_pendiente(factura)
    if not area:
        return  # Todas aprobaron
    email_dest = {
        "rrhh":      factura.get("email_rrhh") or CONFIG.get("email_aprobador", ""),
        "marketing": factura.get("email_marketing") or CONFIG.get("email_aprobador", ""),
        "gerencia":  factura.get("email_gerencia_aprobador") or CONFIG.get("email_gerencia", ""),
    }.get(area["id"], "")
    if email_dest:
        html = email_aprobacion_interna(factura_id, factura, area)
        enviar_email(email_dest, f"[{area['nombre']}] Aprobacion requerida — {factura['concepto']}", html)

@app.post("/emision/crear")
def crear_factura_emitida(body: FacturaEmitidaInput):
    """Crea una nueva factura a emitir e inicia el flujo de aprobacion interna."""
    factura_id = "EM-" + str(uuid.uuid4())[:6].upper()
    timestamp  = datetime.datetime.now().isoformat()

    factura = {
        "id":           factura_id,
        "cliente":      body.cliente,
        "rut_cliente":  body.rut_cliente,
        "concepto":     body.concepto,
        "monto_neto":   body.monto_neto,
        "descripcion":  body.descripcion,
        "iva":          round(body.monto_neto * 0.19),
        "total":        body.monto_neto + round(body.monto_neto * 0.19),
        "email_rrhh":           body.email_rrhh,
        "email_marketing":      body.email_marketing,
        "email_gerencia_aprobador": body.email_gerencia_aprobador,
        "estado":       "pendiente",
        "aprobaciones": {},
        "historial":    [{"accion": "Factura creada e ingresada al flujo", "ts": timestamp}],
        "timestamp":    timestamp,
        # Gerencia solo requerida si monto_neto > 5.000.000
        "requiere_gerencia": body.monto_neto > 5_000_000,
        "areas_requeridas": ["rrhh", "marketing"] + (["gerencia"] if body.monto_neto > 5_000_000 else []),
    }
    FACTURAS_EMITIDAS[factura_id] = factura

    # Notificar primera área (RRHH siempre primero)
    notificar_siguiente_area(factura_id, factura)

    print(f"\n  [EMISION] Nueva factura {factura_id} para {body.cliente} — $ {body.monto_neto:,.0f} CLP")
    print(f"  [EMISION] Areas requeridas: {factura['areas_requeridas']}")
    return {"factura_id": factura_id, "estado": "pendiente", "siguiente_area": (siguiente_area_pendiente(factura) or {}).get("nombre"), "areas_requeridas": factura["areas_requeridas"]}

@app.get("/emision/listar")
def listar_facturas_emitidas():
    """Lista todas las facturas emitidas con su estado de aprobacion."""
    resultado = []
    for f in FACTURAS_EMITIDAS.values():
        area_actual = siguiente_area_pendiente(f)
        resultado.append({
            **f,
            "area_pendiente": area_actual["nombre"] if area_actual else None,
            "progreso": len(f["aprobaciones"]),
            "total_etapas": len(f["areas_requeridas"]),
        })
    return {"total": len(resultado), "facturas": resultado}

@app.get("/emision/aprobar/{factura_id}/{area_id}", response_class=HTMLResponse)
def aprobar_emision(factura_id: str, area_id: str):
    """Un área aprueba su etapa — avanza al siguiente aprobador."""
    if factura_id not in FACTURAS_EMITIDAS:
        raise HTTPException(404, "Factura no encontrada")
    factura = FACTURAS_EMITIDAS[factura_id]
    if factura["estado"] == "rechazada":
        return "<html><body style='font-family:Arial;text-align:center;padding:60px'><h2 style='color:#a02020'>Esta factura ya fue rechazada</h2></body></html>"

    area_nombre = next((a["nombre"] for a in AREAS if a["id"] == area_id), area_id)
    ts = datetime.datetime.now().isoformat()
    factura["aprobaciones"][area_id] = "aprobado"
    factura["historial"].append({"accion": f"Aprobado por {area_nombre}", "ts": ts})

    siguiente = siguiente_area_pendiente(factura)
    if siguiente:
        factura["estado"] = "en_proceso"
        notificar_siguiente_area(factura_id, factura)
        msg = f"Aprobado por {area_nombre}. Solicitud enviada a {siguiente['nombre']}."
        color = "#b8860b"
    else:
        factura["estado"] = "aprobada"
        factura["historial"].append({"accion": "Todas las areas aprobaron — lista para emitir", "ts": ts})
        msg = "Todas las areas aprobaron. La factura esta lista para emitirse al cliente."
        color = "#2d7a3a"
        # Notificar a quien creo la factura
        resumen_html = f"""<html><body style='font-family:Arial;max-width:600px;margin:0 auto;padding:20px'>
        <div style='background:#2d7a3a;padding:16px;border-radius:8px 8px 0 0'><h2 style='color:white;margin:0'>Factura aprobada — lista para emitir</h2></div>
        <div style='border:1px solid #ddd;padding:20px;border-radius:0 0 8px 8px'>
        <p>La factura para <strong>{factura["cliente"]}</strong> por <strong>$ {factura["total"]:,.0f} CLP</strong> ha sido aprobada por todas las areas.</p>
        <p style='color:#555;font-size:13px'>Concepto: {factura["concepto"]}</p>
        </div></body></html>"""
        enviar_email(CONFIG.get("email_aprobador",""), f"Factura aprobada — {factura['cliente']}", resumen_html)

    return f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:500px;margin:60px auto;text-align:center">
    <div style="background:#e8f5e9;border:1px solid #a5d6a7;border-radius:12px;padding:40px">
      <div style="font-size:48px">✓</div>
      <h2 style="color:{color}">Aprobado — {area_nombre}</h2>
      <p style="color:#555;font-size:14px">{msg}</p>
      <p style="font-size:11px;color:#999">{factura_id} · {datetime.datetime.now().strftime("%d/%m/%Y %H:%M")}</p>
    </div></body></html>"""

@app.get("/emision/rechazar/{factura_id}/{area_id}", response_class=HTMLResponse)
def rechazar_emision(factura_id: str, area_id: str):
    """Un área rechaza la factura — se detiene el flujo."""
    if factura_id not in FACTURAS_EMITIDAS:
        raise HTTPException(404, "Factura no encontrada")
    factura = FACTURAS_EMITIDAS[factura_id]
    area_nombre = next((a["nombre"] for a in AREAS if a["id"] == area_id), area_id)
    ts = datetime.datetime.now().isoformat()
    factura["aprobaciones"][area_id] = "rechazado"
    factura["estado"] = "rechazada"
    factura["historial"].append({"accion": f"Rechazado por {area_nombre} — flujo detenido", "ts": ts})

    enviar_email(CONFIG.get("email_aprobador",""),
        f"Factura rechazada por {area_nombre} — {factura['cliente']}",
        f"<html><body style='font-family:Arial;padding:20px'><h3 style='color:#a02020'>Factura rechazada</h3><p>La factura para <strong>{factura['cliente']}</strong> fue rechazada por <strong>{area_nombre}</strong>.</p></body></html>")

    return f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:500px;margin:60px auto;text-align:center">
    <div style="background:#fff0f0;border:1px solid #ef9a9a;border-radius:12px;padding:40px">
      <div style="font-size:48px">✗</div>
      <h2 style="color:#a02020">Rechazado — {area_nombre}</h2>
      <p style="color:#555;font-size:14px">El flujo fue detenido. Se notificó al equipo de finanzas.</p>
      <p style="font-size:11px;color:#999">{factura_id} · {datetime.datetime.now().strftime("%d/%m/%Y %H:%M")}</p>
    </div></body></html>"""


# ════════════════════════════════════════════════════════════════════════════
#  MÓDULO DE IA — Gemini (demo gratis) → Claude (producción)
#  3 funcionalidades: análisis, resumen ejecutivo, chat con documentos
# ════════════════════════════════════════════════════════════════════════════

from google import genai

def get_gemini():
    """Inicializa Gemini con la API key guardada en CONFIG."""
    api_key = CONFIG.get("gemini_api_key", "")
    if not api_key:
        return None
    return genai.Client(api_key=api_key)

def ia_disponible() -> bool:
    return bool(CONFIG.get("gemini_api_key", ""))

def llamar_ia(prompt: str, fallback: str = "") -> str:
    """Llama a Gemini. Si falla o no está configurado, devuelve el fallback."""
    client = get_gemini()
    if not client:
        return fallback
    try:
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt
        )
        return response.text.strip()
    except Exception as ex:
        print(f"  [IA] Error Gemini: {ex}")
        return fallback

def prompt_analisis(datos: dict, clasificacion: dict) -> str:
    zona = clasificacion.get("zona", "")
    motivos = "\n".join(f"- {m}" for m in clasificacion.get("motivos", []))
    return f"""Eres el sistema de análisis financiero del Renaissance Santiago Hotel.
Analizaste una factura y estos son los datos extraídos:

Proveedor: {datos.get("proveedor", "Desconocido")}
RUT: {datos.get("rut", "—")}
Folio: {datos.get("folio", "—")}
Total: ${datos.get("total", 0):,.0f} CLP
Fecha emisión: {datos.get("fecha_emision", "—")}
Fecha vencimiento: {datos.get("fecha_vencimiento", "—")}

El motor de reglas clasificó esta factura en ZONA {zona.upper()} por los siguientes motivos:
{motivos}

Escribe UN párrafo en español (máximo 4 oraciones) explicando:
1. Qué significa esta clasificación en términos prácticos para el hotel
2. Por qué es importante prestar atención a esta factura
3. Qué acción concreta recomiendas (aprobar, revisar, o bloquear y verificar)

Usa lenguaje claro y directo, como si hablaras con el jefe de finanzas del hotel.
No uses asteriscos, bullets ni markdown. Solo texto corrido."""

def prompt_resumen(datos: dict, clasificacion: dict) -> str:
    zona = clasificacion.get("zona", "")
    return f"""Eres el asistente financiero del Renaissance Santiago Hotel.
Resume en 2-3 oraciones esta factura para el equipo directivo:

Proveedor: {datos.get("proveedor", "Desconocido")}
Concepto detectado: {datos.get("concepto", "Servicios varios")}
Total: ${datos.get("total", 0):,.0f} CLP
Clasificación automática: Zona {zona}

El resumen debe ser ejecutivo: qué es, cuánto vale, y si requiere atención.
Sin markdown, sin bullets, solo texto natural en español."""

def prompt_chat(pregunta: str, documentos: list) -> str:
    docs_texto = ""
    for d in documentos[-20:]:  # Últimos 20 docs para no saturar el contexto
        datos = d.get("datos", {})
        zona = d.get("estado", "")
        docs_texto += f"- {datos.get('proveedor','?')} | ${datos.get('total',0):,.0f} CLP | Zona {zona} | {d.get('timestamp','')[:10]}\n"

    return f"""Eres el asistente financiero inteligente del Renaissance Santiago Hotel.
Tienes acceso al historial de facturas procesadas por el sistema:

FACTURAS REGISTRADAS:
{docs_texto if docs_texto else "No hay facturas registradas aún."}

El usuario del hotel te pregunta:
"{pregunta}"

Responde de forma clara y directa en español. Si la pregunta es sobre datos financieros,
da cifras concretas. Si no hay suficientes datos para responder, dilo honestamente.
Máximo 4 oraciones. Sin markdown."""


# ── Endpoints de IA ──────────────────────────────────────────────────────────

class ChatInput(BaseModel):
    pregunta: str

@app.get("/ia/estado")
def ia_estado():
    return {
        "disponible": ia_disponible(),
        "proveedor": "Gemini 3 Flash Preview (demo)" if ia_disponible() else "No configurado",
        "configurar_en": "/configuracion"
    }

@app.post("/ia/analizar/{doc_id}")
def ia_analizar_documento(doc_id: str):
    """Análisis inteligente de una factura ya procesada."""
    if doc_id not in DOCUMENTOS:
        raise HTTPException(404, "Documento no encontrado")
    doc = DOCUMENTOS[doc_id]
    datos = doc["datos"]
    clasificacion = doc["clasificacion"]

    if not ia_disponible():
        return {"analisis": "", "disponible": False, "mensaje": "Configura la API key de Gemini en /configuracion para activar el análisis con IA."}

    analisis = llamar_ia(prompt_analisis(datos, clasificacion))
    doc["ia_analisis"] = analisis  # Guardamos en memoria para no repetir llamada
    return {"analisis": analisis, "disponible": True}

@app.post("/ia/resumen/{doc_id}")
def ia_resumen_documento(doc_id: str):
    """Resumen ejecutivo de una factura."""
    if doc_id not in DOCUMENTOS:
        raise HTTPException(404, "Documento no encontrado")
    doc = DOCUMENTOS[doc_id]

    if not ia_disponible():
        return {"resumen": "", "disponible": False}

    resumen = llamar_ia(prompt_resumen(doc["datos"], doc["clasificacion"]))
    doc["ia_resumen"] = resumen
    return {"resumen": resumen, "disponible": True}

@app.post("/ia/chat")
def ia_chat(body: ChatInput):
    """Chat con los documentos del hotel en lenguaje natural."""
    if not ia_disponible():
        return {"respuesta": "La IA no está configurada. Agrega tu API key de Gemini en Configuración.", "disponible": False}

    if not body.pregunta.strip():
        raise HTTPException(400, "La pregunta no puede estar vacía")

    docs = list(DOCUMENTOS.values())
    respuesta = llamar_ia(prompt_chat(body.pregunta, docs))
    return {"respuesta": respuesta, "disponible": True, "docs_analizados": len(docs)}


if __name__ == "__main__":
    import uvicorn
    print("\n Motor de Aprobación Documental — Hotel")
    print(" ─────────────────────────────────────────────────")
    print(" API:  http://localhost:8000")
    print(" Docs: http://localhost:8000/docs")
    print(" ─────────────────────────────────────────────────")
    print(" Configura los emails en: http://localhost:3000/configuracion\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)
