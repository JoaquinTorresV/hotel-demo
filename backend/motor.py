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
import re, uuid, datetime, os, smtplib, tempfile, json, pathlib, time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pydantic import BaseModel
from typing import Optional

# Persistencia JSON config y variables de entorno
BASE_DIR = pathlib.Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"
ENV_FILE = BASE_DIR / ".env"
DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
DEFAULT_GEMINI_API_VERSION = os.getenv("GEMINI_API_VERSION", "v1").strip() or "v1"
GEMINI_MAX_RETRIES = max(1, int(os.getenv("GEMINI_MAX_RETRIES", "2")))
GEMINI_MODEL_FALLBACKS = [
    m.strip() for m in os.getenv(
        "GEMINI_MODEL_FALLBACKS",
        "gemini-2.5-flash,gemini-2.5-pro",
    ).split(",") if m.strip()
]

def load_env_file(path: pathlib.Path = ENV_FILE):
    if not path.exists():
        return
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except Exception as ex:
        print(f"  [ENV] Error leyendo {path.name}: {ex}")

load_env_file()

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

def get_gemini_api_key() -> str:
    env_key = os.getenv("GEMINI_API_KEY", "").strip()
    if env_key:
        return env_key
    return str(CONFIG.get("gemini_api_key", "")).strip()

def gemini_api_source() -> str:
    if os.getenv("GEMINI_API_KEY", "").strip():
        return "env"
    if str(CONFIG.get("gemini_api_key", "")).strip():
        return "config"
    return "none"

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
    "12.456.789-5": {"nombre": "Distribuidora López e Hijos Ltda.", "media_historica": 800_000},
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
    """Devuelve la config actual sin exponer secretos."""
    cfg_publica = {k: v for k, v in CONFIG.items() if k not in {"email_password", "gemini_api_key"}}
    cfg_publica["email_password_set"] = bool(CONFIG.get("email_password"))
    cfg_publica["gemini_api_key_set"] = bool(get_gemini_api_key())
    cfg_publica["gemini_api_key_source"] = gemini_api_source()
    return cfg_publica

@app.post("/configuracion")
def set_configuracion(body: ConfigUpdate):
    """Guarda config enviada desde el frontend."""
    update = body.model_dump(exclude_none=True)
    if os.getenv("GEMINI_API_KEY", "").strip():
        update.pop("gemini_api_key", None)
    CONFIG.update(update)
    guardar_config(CONFIG)  # persiste en config.json
    print(f"\n  [CONFIG] Actualizado y guardado: {list(update.keys())}")
    return {
        "ok": True,
        "email_configurado": email_configurado(),
        "campos_actualizados": list(update.keys()),
        "gemini_api_key_set": bool(get_gemini_api_key()),
        "gemini_api_key_source": gemini_api_source(),
    }

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
#  FLUJO 2 — FACTURAS QUE EL HOTEL EMITE (aprobación dinámica)
#  Aprobadores completamente configurables por factura — sin límites fijos
# ════════════════════════════════════════════════════════════════════════════

FACTURAS_EMITIDAS = {}

# Catálogo de departamentos disponibles para el hotel
DEPARTAMENTOS_HOTEL = [
    {"id": "gerencia_general",   "nombre": "Gerencia General"},
    {"id": "finanzas",           "nombre": "Finanzas y Contabilidad"},
    {"id": "rrhh",               "nombre": "Recursos Humanos"},
    {"id": "marketing",          "nombre": "Marketing y Ventas"},
    {"id": "operaciones",        "nombre": "Operaciones"},
    {"id": "fb_manager",         "nombre": "F&B Manager"},
    {"id": "revenue",            "nombre": "Revenue Management"},
    {"id": "eventos",            "nombre": "Eventos y Banquetes"},
    {"id": "compras",            "nombre": "Compras y Proveedores"},
    {"id": "legal",              "nombre": "Legal y Cumplimiento"},
    {"id": "ti",                 "nombre": "Tecnología (TI)"},
    {"id": "mantenimiento",      "nombre": "Mantenimiento"},
    {"id": "housekeeping",       "nombre": "Housekeeping"},
    {"id": "recepcion",          "nombre": "Recepción y Front Desk"},
    {"id": "director_hotel",     "nombre": "Director del Hotel"},
]

class AprobadorInput(BaseModel):
    area_id:  str
    nombre:   str
    email:    str
    orden:    int

class FacturaEmitidaInput(BaseModel):
    cliente:      str
    rut_cliente:  str
    concepto:     str
    monto_neto:   int
    descripcion:  Optional[str] = ""
    aprobadores:  list  # Lista de AprobadorInput

def email_aprobacion_interna(factura_id: str, factura: dict, aprobador: dict, total_etapas: int) -> str:
    base    = CONFIG["base_url"]
    iva     = factura["iva"]
    total   = factura["total"]
    area_id = aprobador["area_id"]
    orden   = aprobador["orden"]
    return f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#333">
<div style="background:#1a3a5c;padding:16px 20px;border-radius:8px 8px 0 0">
  <h2 style="color:white;margin:0;font-size:16px">Solicitud de aprobacion — {aprobador["nombre"]}</h2>
  <p style="color:#adc8e8;margin:4px 0 0;font-size:13px">Renaissance Santiago Hotel · Etapa {orden} de {total_etapas}</p>
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
    {f'<tr style="background:#f5f5f5"><td style="padding:8px 12px;color:#666">Descripcion</td><td style="padding:8px 12px">{factura["descripcion"]}</td></tr>' if factura.get("descripcion") else ""}
  </table>
  <p style="font-size:13px;color:#555;margin-bottom:16px"><strong>Etapa {orden} de {total_etapas}</strong> — Aprobacion de {aprobador["nombre"]}</p>
  <div>
    <a href="{base}/emision/aprobar/{factura_id}/{area_id}" style="display:inline-block;background:#2d7a3a;color:white;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:bold;font-size:14px;margin-right:8px">Aprobar</a>
    <a href="{base}/emision/rechazar/{factura_id}/{area_id}" style="display:inline-block;background:#a02020;color:white;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:bold;font-size:14px">Rechazar</a>
  </div>
  <p style="font-size:11px;color:#999;margin-top:16px">Sin respuesta en 24h se enviara recordatorio automatico.</p>
</div></body></html>"""

def siguiente_aprobador_pendiente(factura: dict) -> Optional[dict]:
    """Devuelve el siguiente aprobador que aún no ha respondido, en orden."""
    aprobaciones = factura.get("aprobaciones", {})
    for aprobador in sorted(factura["aprobadores"], key=lambda x: x["orden"]):
        estado = aprobaciones.get(aprobador["area_id"])
        if estado != "aprobado":
            return aprobador
    return None

def notificar_siguiente_aprobador(factura_id: str, factura: dict):
    aprobador = siguiente_aprobador_pendiente(factura)
    if not aprobador or not aprobador.get("email"):
        return
    total_etapas = len(factura["aprobadores"])
    html = email_aprobacion_interna(factura_id, factura, aprobador, total_etapas)
    enviar_email(aprobador["email"], f"[{aprobador['nombre']}] Aprobacion requerida — {factura['concepto']}", html)

@app.get("/emision/departamentos")
def listar_departamentos():
    """Lista todos los departamentos disponibles para configurar el flujo."""
    return {"departamentos": DEPARTAMENTOS_HOTEL}

@app.post("/emision/crear")
def crear_factura_emitida(body: FacturaEmitidaInput):
    """Crea factura e inicia el flujo con los aprobadores que se definieron."""
    if not body.aprobadores:
        raise HTTPException(400, "Debes definir al menos un aprobador")

    factura_id = "EM-" + str(uuid.uuid4())[:6].upper()
    timestamp  = datetime.datetime.now().isoformat()
    iva        = round(body.monto_neto * 0.19)

    # Normalizar aprobadores y asignar orden secuencial
    aprobadores = sorted(
        [{"area_id": a["area_id"], "nombre": a["nombre"], "email": a["email"], "orden": a["orden"]}
         for a in body.aprobadores],
        key=lambda x: x["orden"]
    )

    factura = {
        "id":           factura_id,
        "cliente":      body.cliente,
        "rut_cliente":  body.rut_cliente,
        "concepto":     body.concepto,
        "descripcion":  body.descripcion or "",
        "monto_neto":   body.monto_neto,
        "iva":          iva,
        "total":        body.monto_neto + iva,
        "aprobadores":  aprobadores,
        "aprobaciones": {},
        "estado":       "pendiente",
        "historial":    [{"accion": f"Factura creada — {len(aprobadores)} aprobadores configurados", "ts": timestamp}],
        "timestamp":    timestamp,
    }
    FACTURAS_EMITIDAS[factura_id] = factura
    notificar_siguiente_aprobador(factura_id, factura)

    print(f"\n  [EMISION] {factura_id} para {body.cliente} — $ {body.monto_neto:,.0f} CLP")
    print(f"  [EMISION] Flujo: {' → '.join(a['nombre'] for a in aprobadores)}")

    siguiente = siguiente_aprobador_pendiente(factura)
    return {
        "factura_id":      factura_id,
        "estado":          "pendiente",
        "total_etapas":    len(aprobadores),
        "siguiente_area":  siguiente["nombre"] if siguiente else None,
        "flujo":           [a["nombre"] for a in aprobadores],
    }

@app.get("/emision/listar")
def listar_facturas_emitidas():
    resultado = []
    for f in FACTURAS_EMITIDAS.values():
        sig = siguiente_aprobador_pendiente(f)
        aprobadas = sum(1 for v in f["aprobaciones"].values() if v == "aprobado")
        resultado.append({
            **f,
            "area_pendiente":  sig["nombre"] if sig else None,
            "progreso":        aprobadas,
            "total_etapas":    len(f["aprobadores"]),
        })
    return {"total": len(resultado), "facturas": resultado}

@app.get("/emision/aprobar/{factura_id}/{area_id}", response_class=HTMLResponse)
def aprobar_emision(factura_id: str, area_id: str):
    if factura_id not in FACTURAS_EMITIDAS:
        raise HTTPException(404, "Factura no encontrada")
    factura = FACTURAS_EMITIDAS[factura_id]
    if factura["estado"] == "rechazada":
        return "<html><body style='font-family:Arial;text-align:center;padding:60px'><h2 style='color:#a02020'>Esta factura ya fue rechazada</h2></body></html>"

    area_nombre = next((a["nombre"] for a in factura["aprobadores"] if a["area_id"] == area_id), area_id)
    ts = datetime.datetime.now().isoformat()
    factura["aprobaciones"][area_id] = "aprobado"
    factura["historial"].append({"accion": f"Aprobado por {area_nombre}", "ts": ts})

    siguiente = siguiente_aprobador_pendiente(factura)
    if siguiente:
        factura["estado"] = "en_proceso"
        notificar_siguiente_aprobador(factura_id, factura)
        msg   = f"Aprobado. Solicitud enviada a {siguiente['nombre']}."
        color = "#b8860b"
    else:
        factura["estado"] = "aprobada"
        factura["historial"].append({"accion": "Todas las etapas aprobadas — lista para emitir", "ts": ts})
        msg   = "Todas las etapas completadas. La factura está lista para emitirse al cliente."
        color = "#2d7a3a"
        resumen = f"""<html><body style='font-family:Arial;max-width:600px;margin:0 auto;padding:20px'>
        <div style='background:#2d7a3a;padding:16px;border-radius:8px 8px 0 0'><h2 style='color:white;margin:0'>Factura aprobada — lista para emitir</h2></div>
        <div style='border:1px solid #ddd;padding:20px;border-radius:0 0 8px 8px'>
        <p>La factura para <strong>{factura["cliente"]}</strong> por <strong>$ {factura["total"]:,.0f} CLP</strong> fue aprobada por todas las áreas.</p>
        <p style='color:#555;font-size:13px'>Concepto: {factura["concepto"]}</p></div></body></html>"""
        enviar_email(CONFIG.get("email_aprobador", ""), f"✓ Factura aprobada — {factura['cliente']}", resumen)

    return f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:500px;margin:60px auto;text-align:center">
    <div style="background:#e8f5e9;border:1px solid #a5d6a7;border-radius:12px;padding:40px">
      <div style="font-size:48px">✓</div>
      <h2 style="color:{color}">{area_nombre} — Aprobado</h2>
      <p style="color:#555;font-size:14px">{msg}</p>
      <p style="font-size:11px;color:#999">{factura_id} · {datetime.datetime.now().strftime("%d/%m/%Y %H:%M")}</p>
    </div></body></html>"""

@app.get("/emision/rechazar/{factura_id}/{area_id}", response_class=HTMLResponse)
def rechazar_emision(factura_id: str, area_id: str):
    if factura_id not in FACTURAS_EMITIDAS:
        raise HTTPException(404, "Factura no encontrada")
    factura = FACTURAS_EMITIDAS[factura_id]
    area_nombre = next((a["nombre"] for a in factura["aprobadores"] if a["area_id"] == area_id), area_id)
    ts = datetime.datetime.now().isoformat()
    factura["aprobaciones"][area_id] = "rechazado"
    factura["estado"] = "rechazada"
    factura["historial"].append({"accion": f"Rechazado por {area_nombre} — flujo detenido", "ts": ts})

    aviso = f"""<html><body style='font-family:Arial;padding:20px'><h3 style='color:#a02020'>Factura rechazada</h3>
    <p>La factura para <strong>{factura['cliente']}</strong> fue rechazada por <strong>{area_nombre}</strong>.</p></body></html>"""
    enviar_email(CONFIG.get("email_aprobador", ""), f"✗ Factura rechazada — {factura['cliente']}", aviso)

    return f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:500px;margin:60px auto;text-align:center">
    <div style="background:#fff0f0;border:1px solid #ef9a9a;border-radius:12px;padding:40px">
      <div style="font-size:48px">✗</div>
      <h2 style="color:#a02020">{area_nombre} — Rechazado</h2>
      <p style="color:#555;font-size:14px">El flujo fue detenido. El equipo de finanzas fue notificado.</p>
      <p style="font-size:11px;color:#999">{factura_id} · {datetime.datetime.now().strftime("%d/%m/%Y %H:%M")}</p>
    </div></body></html>"""

# ════════════════════════════════════════════════════════════════════════════
#  MÓDULO DE IA — Gemini (demo gratis) → Claude (producción)
#  3 funcionalidades: análisis, resumen ejecutivo, chat con documentos
# ════════════════════════════════════════════════════════════════════════════

from google import genai
from google.genai import types

def get_gemini():
    """Inicializa Gemini con la API key del entorno o la config local."""
    api_key = get_gemini_api_key()
    if not api_key:
        return None
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(api_version=DEFAULT_GEMINI_API_VERSION),
    )

def ia_disponible() -> bool:
    return bool(get_gemini_api_key())

def formatear_clp(valor: int | float) -> str:
    return f"$ {valor:,.0f} CLP"

def fallback_analisis(datos: dict, clasificacion: dict) -> str:
    zona = str(clasificacion.get("zona", "")).lower()
    proveedor = datos.get("proveedor") or "este proveedor"
    total = formatear_clp(datos.get("total", 0))
    if zona == "verde":
        return f"La factura de {proveedor} por {total} cae en zona verde, así que el monto parece estar dentro del patrón esperado. Conviene aprobarla y seguir el flujo normal, porque no muestra señales fuertes de riesgo."
    if zona == "amarilla":
        return f"La factura de {proveedor} por {total} quedó en zona amarilla porque se sale del comportamiento esperado y merece revisión. Lo prudente es validar el detalle antes de aprobarla, para confirmar que el cargo esté justificado y no haya duplicidad o sobrecosto."
    return f"La factura de {proveedor} por {total} quedó en zona roja, lo que indica un riesgo alto para el hotel. La recomendación es bloquear y verificar antes de avanzar, porque el monto o la señal de control requiere revisión manual."

def fallback_resumen(datos: dict, clasificacion: dict) -> str:
    zona = str(clasificacion.get("zona", "")).lower()
    proveedor = datos.get("proveedor") or "proveedor no identificado"
    concepto = datos.get("concepto") or "servicios varios"
    total = formatear_clp(datos.get("total", 0))
    zona_texto = {"verde": "zona verde", "amarilla": "zona amarilla", "roja": "zona roja"}.get(zona, "una zona no determinada")
    return f"Factura de {proveedor} por {total}, asociada a {concepto}. Quedó clasificada en {zona_texto} y conviene revisarla según el flujo normal del hotel."

def _doc_datos_chat(doc: dict) -> dict:
    """Normaliza documentos en formato anidado (backend) o plano (frontend)."""
    nested = doc.get("datos") if isinstance(doc.get("datos"), dict) else {}
    proveedor = nested.get("proveedor") or doc.get("proveedor") or "desconocido"
    total_raw = nested.get("total", doc.get("total_clp", doc.get("total", 0)))
    try:
        total = float(total_raw or 0)
    except Exception:
        total = 0
    return {"proveedor": proveedor, "total": total}

def _doc_zona_chat(doc: dict) -> str:
    """Mapea estados heterogéneos a: verde, amarilla o roja."""
    estado_raw = " ".join([
        str(doc.get("estado", "")),
        str(doc.get("zona", "")),
        str(doc.get("zona_label", "")),
        str(doc.get("accion", "")),
    ]).lower()
    if any(tag in estado_raw for tag in ["roja", "bloque", "rechaz"]):
        return "roja"
    if "amarilla" in estado_raw:
        return "amarilla"
    if any(tag in estado_raw for tag in ["verde", "aprob"]):
        return "verde"
    return ""

def fallback_chat(pregunta: str, documentos: list) -> str:
    if not documentos:
        return "No hay facturas registradas todavía, así que no puedo sacar conclusiones del historial."

    docs_norm = [{"datos": _doc_datos_chat(d), "zona": _doc_zona_chat(d)} for d in documentos]
    total = sum(d["datos"].get("total", 0) for d in docs_norm)
    verdes = sum(1 for d in docs_norm if d.get("zona") == "verde")
    amarillas = sum(1 for d in docs_norm if d.get("zona") == "amarilla")
    rojas = sum(1 for d in docs_norm if d.get("zona") == "roja")
    mayor = max(docs_norm, key=lambda d: d["datos"].get("total", 0))
    mayor_datos = mayor["datos"]

    texto = pregunta.lower()
    if any(p in texto for p in ["gastado", "gasto", "total", "monto"]):
        return f"Con los documentos registrados llevas {formatear_clp(total)} procesados. Hay {verdes} en verde, {amarillas} en amarilla y {rojas} en roja."
    if any(p in texto for p in ["proveedor", "más alto", "mas alto", "mayor"]):
        return f"El proveedor con el monto más alto es {mayor_datos.get('proveedor', 'desconocido')} por {formatear_clp(mayor_datos.get('total', 0))}."
    if any(p in texto for p in ["bloque", "pendient", "roja", "rojo"]):
        return f"Tienes {rojas} facturas en zona roja y {amarillas} en amarilla. Esas son las que conviene revisar primero porque tienen mayor riesgo o requieren aprobación."
    if any(p in texto for p in ["autom", "aprob", "verde"]):
        return f"Hay {verdes} facturas en zona verde que pudieron seguir el flujo automático."

    return f"Hay {len(documentos)} facturas registradas. El monto acumulado es {formatear_clp(total)} y la distribución actual es {verdes} verdes, {amarillas} amarillas y {rojas} rojas."

def llamar_ia(prompt: str, fallback: str = "") -> str:
    """Llama a Gemini. Si falla o no está configurado, devuelve el fallback."""
    client = get_gemini()
    if not client:
        return fallback
    last_error = None
    env_model = os.getenv("GEMINI_MODEL", "").strip()
    model_candidates = [m for m in [env_model, DEFAULT_GEMINI_MODEL, *GEMINI_MODEL_FALLBACKS] if m]
    # Eliminar duplicados preservando orden
    model_candidates = list(dict.fromkeys(model_candidates))

    for model_name in model_candidates:
        for attempt in range(1, GEMINI_MAX_RETRIES + 1):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                text = (response.text or "").strip()
                if text:
                    return text
                last_error = f"Respuesta vacía de Gemini con modelo {model_name}"
            except Exception as ex:
                last_error = ex
                print(f"  [IA] Error Gemini modelo={model_name} (intento {attempt}/{GEMINI_MAX_RETRIES}): {ex}")
                if attempt < GEMINI_MAX_RETRIES:
                    time.sleep(0.5 * attempt)

    if last_error:
        print(f"  [IA] Usando fallback local tras error Gemini: {last_error}")
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
        datos = _doc_datos_chat(d)
        zona = _doc_zona_chat(d)
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
    documentos: Optional[list] = []  # El frontend manda su historial (stateless)

class IAInlineInput(BaseModel):
    doc_data: Optional[dict] = None
    zona: Optional[str] = ""
    motivos: Optional[list] = None

def _datos_desde_inline(doc_data: dict | None) -> dict:
    payload = doc_data or {}
    return {
        "proveedor": payload.get("proveedor"),
        "rut": payload.get("rut"),
        "folio": payload.get("folio"),
        "fecha_emision": payload.get("fecha_emision"),
        "fecha_vencimiento": payload.get("fecha_vencimiento"),
        "concepto": payload.get("concepto"),
        "total": payload.get("total_clp", payload.get("total", 0)) or 0,
    }

@app.get("/ia/estado")
def ia_estado():
    fuente = gemini_api_source()
    return {
        "disponible": ia_disponible(),
        "proveedor": "Gemini 3 Flash Preview (entorno)" if fuente == "env" else ("Gemini 3 Flash Preview (config local)" if fuente == "config" else "No configurado"),
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
        return {"analisis": fallback_analisis(datos, clasificacion), "disponible": False, "mensaje": "Gemini no está configurado. Se devolvió un análisis local de respaldo."}

    analisis = llamar_ia(prompt_analisis(datos, clasificacion), fallback_analisis(datos, clasificacion))
    doc["ia_analisis"] = analisis  # Guardamos en memoria para no repetir llamada
    return {"analisis": analisis, "disponible": True}

@app.post("/ia/resumen/{doc_id}")
def ia_resumen_documento(doc_id: str):
    """Resumen ejecutivo de una factura."""
    if doc_id not in DOCUMENTOS:
        raise HTTPException(404, "Documento no encontrado")
    doc = DOCUMENTOS[doc_id]

    if not ia_disponible():
        return {"resumen": fallback_resumen(doc["datos"], doc["clasificacion"]), "disponible": False}

    resumen = llamar_ia(prompt_resumen(doc["datos"], doc["clasificacion"]), fallback_resumen(doc["datos"], doc["clasificacion"]))
    doc["ia_resumen"] = resumen
    return {"resumen": resumen, "disponible": True}

@app.post("/ia/analizar")
def ia_analizar_inline(body: IAInlineInput):
    """Análisis IA usando payload directo (compatibilidad frontend)."""
    datos = _datos_desde_inline(body.doc_data)
    clasificacion = {
        "zona": (body.zona or "").lower(),
        "motivos": body.motivos or [],
    }
    fallback = fallback_analisis(datos, clasificacion)
    if not ia_disponible():
        return {"analisis": fallback, "disponible": False, "mensaje": "Gemini no está configurado o no está disponible. Se devolvió un análisis local de respaldo."}
    analisis = llamar_ia(prompt_analisis(datos, clasificacion), fallback)
    return {"analisis": analisis, "disponible": True}

@app.post("/ia/resumen")
def ia_resumen_inline(body: IAInlineInput):
    """Resumen IA usando payload directo (compatibilidad frontend)."""
    datos = _datos_desde_inline(body.doc_data)
    clasificacion = {
        "zona": (body.zona or "").lower(),
        "motivos": body.motivos or [],
    }
    fallback = fallback_resumen(datos, clasificacion)
    if not ia_disponible():
        return {"resumen": fallback, "disponible": False}
    resumen = llamar_ia(prompt_resumen(datos, clasificacion), fallback)
    return {"resumen": resumen, "disponible": True}

@app.post("/ia/chat")
def ia_chat(body: ChatInput):
    """Chat con los documentos del hotel en lenguaje natural."""
    if not body.pregunta.strip():
        raise HTTPException(400, "La pregunta no puede estar vacía")

    # Prioridad: docs del frontend (Vercel stateless) > DOCUMENTOS en RAM (local)
    docs_frontend = body.documentos or []
    docs = docs_frontend if docs_frontend else list(DOCUMENTOS.values())
    if not ia_disponible():
        return {"respuesta": fallback_chat(body.pregunta, docs), "disponible": False, "docs_analizados": len(docs)}

    respuesta = llamar_ia(prompt_chat(body.pregunta, docs), fallback_chat(body.pregunta, docs))
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
