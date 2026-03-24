"""
Motor de clasificación de documentos financieros — Hotel Pacifico Sur
FastAPI backend para la demo.

Endpoints:
  POST /procesar       → recibe PDF, devuelve clasificación completa
  GET  /documentos     → lista todos los docs procesados
  GET  /aprobar/{id}   → aprueba un doc de zona amarilla (botón del email)
  GET  /rechazar/{id}  → rechaza un doc de zona amarilla
  GET  /health         → healthcheck
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
import pdfplumber
import re, uuid, datetime, json, os, smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

app = FastAPI(title="Motor Aprobación Documental — Hotel Pacifico Sur")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

# ─── Config email (cambia por tu cuenta real) ────────────────────────────────
EMAIL_CONFIG = {
    "smtp_host":   "smtp.gmail.com",
    "smtp_port":   587,
    "usuario":     "TU_EMAIL@gmail.com",       # ← cambia esto
    "password":    "TU_APP_PASSWORD",           # ← contraseña de aplicación Gmail
    "desde":       "Sistema Hotel Pacifico Sur <TU_EMAIL@gmail.com>",
    "aprobador":   "EMAIL_APROBADOR@gmail.com", # ← email del responsable
    "gerencia":    "EMAIL_GERENCIA@gmail.com",  # ← email de gerencia
    "base_url":    "http://localhost:8000",
}

# ─── Base de datos simulada en memoria ──────────────────────────────────────
DOCUMENTOS = {}

# ─── Lista blanca de proveedores (RUTs verificados) ─────────────────────────
LISTA_BLANCA = {
    "12.456.789-5": {"nombre": "Distribuidora López e Hijos Ltda.", "media_historica": 650_000},
    "76.321.654-K": {"nombre": "Sistemas Técnicos SA",              "media_historica": 1_060_000},
    "9.876.543-2":  {"nombre": "Lavandería Industrial Norte Ltda.", "media_historica": 280_000},
    "15.432.100-8": {"nombre": "Suministros Gastronómicos SPA",     "media_historica": 420_000},
}

# ─── Umbrales de clasificación ───────────────────────────────────────────────
UMBRAL_VERDE_MAX    = 1_000_000   # hasta $1.000.000 CLP aprobación automática
UMBRAL_ROJO_MIN     = 10_000_000  # desde $10.000.000 CLP bloqueo automático
TOLERANCIA_HISTORICO = 0.15       # ±15% sobre media del proveedor

# ════════════════════════════════════════════════════════════════════════════
#  EXTRACCIÓN DE DATOS DEL PDF
# ════════════════════════════════════════════════════════════════════════════

def extraer_datos(ruta_pdf: str) -> dict:
    """Lee el PDF y extrae los campos clave."""
    datos = {
        "proveedor": None, "rut": None, "folio": None,
        "fecha_emision": None, "fecha_vencimiento": None,
        "neto": 0, "iva": 0, "total": 0, "concepto": None,
    }
    try:
        with pdfplumber.open(ruta_pdf) as pdf:
            texto = "\n".join(p.extract_text() or "" for p in pdf.pages)

        # RUT (formato chileno: XX.XXX.XXX-X o X.XXX.XXX-X)
        ruts = re.findall(r"\b\d{1,2}\.\d{3}\.\d{3}-[\dKk]\b", texto)
        # Ignorar el RUT del hotel mismo
        ruts_prov = [r for r in ruts if r != "76.543.210-8"]
        if ruts_prov:
            datos["rut"] = ruts_prov[0]

        # Folio
        folio_match = re.search(r"N[°o]?\s*(\d{4,})", texto)
        if folio_match:
            datos["folio"] = folio_match.group(1)

        # Fechas
        fechas = re.findall(r"\d{2}/\d{2}/\d{4}", texto)
        if len(fechas) >= 1: datos["fecha_emision"]    = fechas[0]
        if len(fechas) >= 2: datos["fecha_vencimiento"] = fechas[1]

        # Montos — busca patrones "$  X.XXX.XXX"
        montos = re.findall(r"\$\s*([\d\.]+)", texto)
        montos_num = []
        for m in montos:
            try:
                montos_num.append(int(m.replace(".", "")))
            except:
                pass

        if montos_num:
            montos_num.sort()
            # El total es el mayor, neto el anterior
            datos["total"] = montos_num[-1]
            if len(montos_num) >= 3:
                datos["neto"] = montos_num[-3]
                datos["iva"]  = montos_num[-2]

        # Proveedor — línea después de "PROVEEDOR"
        prov_match = re.search(r"PROVEEDOR\s*\n(.+)", texto)
        if prov_match:
            datos["proveedor"] = prov_match.group(1).strip()
        else:
            # fallback: buscar en lista blanca por RUT
            if datos["rut"] and datos["rut"] in LISTA_BLANCA:
                datos["proveedor"] = LISTA_BLANCA[datos["rut"]]["nombre"]

        # Concepto — primer ítem de la tabla
        concepto_match = re.search(r"Descripción\s*\n(.+)", texto)
        if concepto_match:
            datos["concepto"] = concepto_match.group(1).strip()[:80]

    except Exception as ex:
        print(f"  [WARN] Error extrayendo datos: {ex}")

    return datos

# ════════════════════════════════════════════════════════════════════════════
#  MOTOR DE REGLAS — CLASIFICACIÓN EN ZONAS
# ════════════════════════════════════════════════════════════════════════════

def clasificar(datos: dict) -> dict:
    """Aplica todas las reglas de negocio y devuelve zona + motivos."""
    motivos = []
    zona = "verde"  # optimista por defecto

    rut   = datos.get("rut")
    total = datos.get("total", 0)

    # ── Regla 1: Proveedor en lista blanca ───────────────────────────────────
    if not rut or rut not in LISTA_BLANCA:
        motivos.append("Proveedor no registrado en lista blanca")
        zona = "roja"
    else:
        motivos.append(f"Proveedor verificado ({LISTA_BLANCA[rut]['nombre']})")

    # ── Regla 2: Importe sobre umbral rojo ──────────────────────────────────
    if total >= UMBRAL_ROJO_MIN:
        motivos.append(f"Importe ${total:,.0f} supera umbral rojo (${UMBRAL_ROJO_MIN:,.0f})")
        zona = "roja"

    # ── Regla 3: Sin orden de compra (simulado: proveedores nuevos) ──────────
    if rut and rut not in LISTA_BLANCA:
        motivos.append("Sin orden de compra vinculada")
        zona = "roja"

    # ── Regla 4: Variación sobre histórico ───────────────────────────────────
    if rut and rut in LISTA_BLANCA and zona != "roja":
        media = LISTA_BLANCA[rut]["media_historica"]
        variacion = (total - media) / media if media > 0 else 0
        if abs(variacion) > TOLERANCIA_HISTORICO:
            pct = variacion * 100
            motivos.append(f"Importe {pct:+.0f}% sobre histórico del proveedor (media: ${media:,.0f})")
            if zona == "verde":
                zona = "amarilla"
        else:
            motivos.append(f"Importe dentro del histórico (±{abs(variacion)*100:.0f}%)")

    # ── Regla 5: Umbral automático verde ────────────────────────────────────
    if zona == "verde" and total <= UMBRAL_VERDE_MAX:
        motivos.append(f"Importe ${total:,.0f} dentro del umbral automático")

    # ── Acción según zona ────────────────────────────────────────────────────
    acciones = {
        "verde":    "Aprobación automática. Contabilizado y pago programado al vencimiento.",
        "amarilla": "Notificación enviada al responsable. Decisión requerida en 24h.",
        "roja":     "Documento BLOQUEADO. Expediente completo enviado a gerencia.",
    }

    return {
        "zona":    zona,
        "motivos": motivos,
        "accion":  acciones[zona],
        "reglas_aplicadas": len(motivos),
    }

# ════════════════════════════════════════════════════════════════════════════
#  NOTIFICACIONES EMAIL
# ════════════════════════════════════════════════════════════════════════════

def enviar_email(destinatario: str, asunto: str, html: str):
    """Envía email HTML. En modo demo imprime en consola si no hay SMTP."""
    cfg = EMAIL_CONFIG
    if "TU_EMAIL" in cfg["usuario"]:
        print(f"\n  [EMAIL SIMULADO] → {destinatario}")
        print(f"  Asunto: {asunto}")
        print(f"  (Configura EMAIL_CONFIG en motor.py para envíos reales)\n")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = asunto
        msg["From"]    = cfg["desde"]
        msg["To"]      = destinatario
        msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"]) as s:
            s.starttls()
            s.login(cfg["usuario"], cfg["password"])
            s.sendmail(cfg["usuario"], destinatario, msg.as_string())
        print(f"  [EMAIL] Enviado a {destinatario}")
        return True
    except Exception as ex:
        print(f"  [EMAIL ERROR] {ex}")
        return False

def email_zona_amarilla(doc_id: str, doc: dict) -> str:
    datos = doc["datos"]
    clasificacion = doc["clasificacion"]
    base = EMAIL_CONFIG["base_url"]
    motivos_html = "".join(f"<li>{m}</li>" for m in clasificacion["motivos"])
    return f"""
<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#333">
<div style="background:#b8860b;padding:16px 20px;border-radius:8px 8px 0 0">
  <h2 style="color:white;margin:0;font-size:16px">⚠ Alerta: Factura requiere tu aprobación</h2>
</div>
<div style="border:1px solid #ddd;border-top:none;padding:20px;border-radius:0 0 8px 8px">
  <p style="margin:0 0 16px;color:#555">El motor de aprobación detectó una anomalía y requiere tu decisión para continuar:</p>
  <div style="background:#fff8e1;border-left:4px solid #b8860b;padding:12px 16px;margin-bottom:16px;border-radius:0 6px 6px 0">
    <strong style="color:#b8860b">Anomalía detectada — Zona Amarilla</strong>
    <ul style="margin:8px 0 0;padding-left:20px;color:#5a4000;font-size:13px">{motivos_html}</ul>
  </div>
  <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:20px">
    <tr style="background:#f5f5f5"><td style="padding:8px 12px;color:#666;width:40%">Proveedor</td>
      <td style="padding:8px 12px;font-weight:bold">{datos.get("proveedor","—")}</td></tr>
    <tr><td style="padding:8px 12px;color:#666">RUT</td>
      <td style="padding:8px 12px">{datos.get("rut","—")}</td></tr>
    <tr style="background:#f5f5f5"><td style="padding:8px 12px;color:#666">Folio</td>
      <td style="padding:8px 12px">{datos.get("folio","—")}</td></tr>
    <tr><td style="padding:8px 12px;color:#666">Total con IVA</td>
      <td style="padding:8px 12px;font-weight:bold;color:#b8860b">$ {datos.get("total",0):,.0f} CLP</td></tr>
    <tr style="background:#f5f5f5"><td style="padding:8px 12px;color:#666">Vencimiento</td>
      <td style="padding:8px 12px">{datos.get("fecha_vencimiento","—")}</td></tr>
  </table>
  <p style="font-size:13px;color:#555;margin-bottom:16px">Decide directamente desde este email — <strong>sin entrar a ninguna plataforma:</strong></p>
  <div style="display:flex;gap:10px;flex-wrap:wrap">
    <a href="{base}/aprobar/{doc_id}" style="background:#2d7a3a;color:white;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:bold;font-size:14px">✓ Aprobar y pagar</a>
    <a href="{base}/rechazar/{doc_id}" style="background:#a02020;color:white;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:bold;font-size:14px">✗ Rechazar</a>
    <a href="{base}/solicitar_info/{doc_id}" style="background:#555;color:white;padding:12px 24px;border-radius:6px;text-decoration:none;font-size:14px">? Solicitar información</a>
  </div>
  <p style="font-size:11px;color:#999;margin-top:20px">Sin respuesta en 24h → recordatorio automático. En 72h escala al superior jerárquico.</p>
</div></body></html>"""

def email_zona_verde_resumen(docs_verdes: list) -> str:
    filas = "".join(
        f"""<tr style="{'background:#f9f9f9' if i%2 else ''}">
        <td style="padding:7px 12px">{d['datos'].get('proveedor','—')}</td>
        <td style="padding:7px 12px">N° {d['datos'].get('folio','—')}</td>
        <td style="padding:7px 12px;text-align:right;font-weight:bold">$ {d['datos'].get('total',0):,.0f}</td>
        <td style="padding:7px 12px;color:#2d7a3a;font-weight:bold">Aprobado ✓</td>
        </tr>"""
        for i, d in enumerate(docs_verdes)
    )
    total_dia = sum(d['datos'].get('total', 0) for d in docs_verdes)
    return f"""
<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#333">
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
      <div style="font-size:22px;font-weight:bold;color:#1a3a5c">$ {total_dia:,.0f}</div>
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
    </tr>
    {filas}
  </table>
  <p style="font-size:11px;color:#999;margin-top:16px;text-align:center">
    Sistema de Aprobación Documental · Hotel Pacifico Sur · Generado automáticamente
  </p>
</div></body></html>"""

def email_zona_roja(doc_id: str, doc: dict) -> str:
    datos = doc["datos"]
    clasificacion = doc["clasificacion"]
    motivos_html = "".join(f"<li>{m}</li>" for m in clasificacion["motivos"])
    return f"""
<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#333">
<div style="background:#a02020;padding:16px 20px;border-radius:8px 8px 0 0">
  <h2 style="color:white;margin:0;font-size:16px">🔴 ALERTA CRÍTICA — Documento bloqueado automáticamente</h2>
</div>
<div style="border:1px solid #ddd;border-top:none;padding:20px;border-radius:0 0 8px 8px">
  <div style="background:#fff0f0;border-left:4px solid #a02020;padding:12px 16px;margin-bottom:16px">
    <strong style="color:#a02020">Motivos del bloqueo:</strong>
    <ul style="margin:8px 0 0;padding-left:20px;color:#6a0000;font-size:13px">{motivos_html}</ul>
  </div>
  <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:20px">
    <tr style="background:#f5f5f5"><td style="padding:8px 12px;color:#666;width:40%">Proveedor</td>
      <td style="padding:8px 12px;font-weight:bold">{datos.get("proveedor","Desconocido")}</td></tr>
    <tr><td style="padding:8px 12px;color:#666">RUT</td>
      <td style="padding:8px 12px">{datos.get("rut","—")}</td></tr>
    <tr style="background:#f5f5f5"><td style="padding:8px 12px;color:#666">Importe total</td>
      <td style="padding:8px 12px;font-weight:bold;color:#a02020;font-size:15px">$ {datos.get("total",0):,.0f} CLP</td></tr>
    <tr><td style="padding:8px 12px;color:#666">Folio</td>
      <td style="padding:8px 12px">{datos.get("folio","—")}</td></tr>
  </table>
  <p style="font-size:13px;color:#555">El pago está <strong>bloqueado</strong> hasta que gerencia revise y autorice manualmente en el panel de administración.</p>
  <p style="font-size:11px;color:#999;margin-top:16px">ID documento: {doc_id} · {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
</div></body></html>"""

# ════════════════════════════════════════════════════════════════════════════
#  ENDPOINTS API
# ════════════════════════════════════════════════════════════════════════════

@app.get("/health")
def health():
    return {"status": "ok", "sistema": "Motor Aprobación Documental — Hotel Pacifico Sur"}

@app.post("/procesar")
async def procesar_documento(archivo: UploadFile = File(...)):
    """Recibe un PDF, lo clasifica y dispara las notificaciones correspondientes."""
    if not archivo.filename.endswith(".pdf"):
        raise HTTPException(400, "Solo se aceptan archivos PDF")

    # Guardar temporalmente
    tmp = f"/tmp/{uuid.uuid4()}.pdf"
    with open(tmp, "wb") as f:
        f.write(await archivo.read())

    # Pipeline completo
    doc_id = str(uuid.uuid4())[:8].upper()
    timestamp = datetime.datetime.now().isoformat()

    print(f"\n{'='*55}")
    print(f"  [1/4] Recibido: {archivo.filename} | ID: {doc_id}")

    datos = extraer_datos(tmp)
    print(f"  [2/4] OCR completado | RUT: {datos['rut']} | Total: ${datos['total']:,.0f}")

    clasificacion = clasificar(datos)
    zona = clasificacion["zona"]
    print(f"  [3/4] Clasificado: ZONA {zona.upper()}")

    doc = {
        "id": doc_id, "archivo": archivo.filename,
        "timestamp": timestamp, "datos": datos,
        "clasificacion": clasificacion, "estado": zona,
        "historial": [{"accion": f"Clasificado como zona {zona}", "ts": timestamp}]
    }
    DOCUMENTOS[doc_id] = doc

    # Notificaciones según zona
    cfg = EMAIL_CONFIG
    if zona == "verde":
        print(f"  [4/4] Aprobación automática. Pago programado.")
        # El resumen verde se manda al final del día; para la demo lo mandamos ahora
        html = email_zona_verde_resumen([doc])
        enviar_email(cfg["aprobador"], "Resumen diario — 1 factura procesada automáticamente", html)
        enviar_email(cfg["gerencia"],  "Resumen diario — 1 factura procesada automáticamente", html)

    elif zona == "amarilla":
        print(f"  [4/4] Notificación enviada al aprobador.")
        html = email_zona_amarilla(doc_id, doc)
        enviar_email(cfg["aprobador"], f"⚠ Alerta: Factura requiere aprobación — {datos.get('proveedor','Proveedor')}", html)
        enviar_email(cfg["gerencia"],  f"⚠ Copia: Factura en revisión — {datos.get('proveedor','Proveedor')}", html)

    elif zona == "roja":
        print(f"  [4/4] BLOQUEADO. Expediente enviado a gerencia.")
        html = email_zona_roja(doc_id, doc)
        enviar_email(cfg["gerencia"],  f"🔴 ALERTA CRÍTICA: Documento bloqueado — ${datos.get('total',0):,.0f} CLP", html)
        enviar_email(cfg["aprobador"], f"🔴 Aviso: Documento bloqueado y escalado a gerencia", html)

    os.remove(tmp)
    print(f"{'='*55}\n")

    return {
        "doc_id":        doc_id,
        "zona":          zona,
        "proveedor":     datos.get("proveedor"),
        "rut":           datos.get("rut"),
        "total_clp":     datos.get("total"),
        "folio":         datos.get("folio"),
        "fecha_emision": datos.get("fecha_emision"),
        "motivos":       clasificacion["motivos"],
        "accion":        clasificacion["accion"],
        "timestamp":     timestamp,
        "email_enviado": True,
    }

@app.get("/documentos")
def listar_documentos():
    return {"total": len(DOCUMENTOS), "documentos": list(DOCUMENTOS.values())}

@app.get("/aprobar/{doc_id}", response_class=HTMLResponse)
def aprobar(doc_id: str):
    if doc_id not in DOCUMENTOS:
        raise HTTPException(404, "Documento no encontrado")
    doc = DOCUMENTOS[doc_id]
    doc["estado"] = "aprobado"
    doc["historial"].append({"accion": "Aprobado por responsable", "ts": datetime.datetime.now().isoformat()})
    total = doc["datos"].get("total", 0)
    prov  = doc["datos"].get("proveedor", "—")
    return f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:500px;margin:60px auto;text-align:center;color:#333">
    <div style="background:#e8f5e9;border:1px solid #a5d6a7;border-radius:12px;padding:40px">
      <div style="font-size:48px">✓</div>
      <h2 style="color:#2d7a3a;margin:12px 0">Aprobado correctamente</h2>
      <p style="font-size:15px"><strong>{prov}</strong></p>
      <p style="font-size:18px;font-weight:bold;color:#1a3a5c">$ {total:,.0f} CLP</p>
      <p style="color:#555;font-size:13px">Pago programado para la fecha de vencimiento.<br>Registro de auditoría actualizado.</p>
      <p style="font-size:11px;color:#999;margin-top:20px">ID: {doc_id} · {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
    </div></body></html>"""

@app.get("/rechazar/{doc_id}", response_class=HTMLResponse)
def rechazar(doc_id: str):
    if doc_id not in DOCUMENTOS:
        raise HTTPException(404, "Documento no encontrado")
    doc = DOCUMENTOS[doc_id]
    doc["estado"] = "rechazado"
    doc["historial"].append({"accion": "Rechazado por responsable", "ts": datetime.datetime.now().isoformat()})
    prov = doc["datos"].get("proveedor", "—")
    return f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:500px;margin:60px auto;text-align:center;color:#333">
    <div style="background:#fff0f0;border:1px solid #ef9a9a;border-radius:12px;padding:40px">
      <div style="font-size:48px">✗</div>
      <h2 style="color:#a02020;margin:12px 0">Factura rechazada</h2>
      <p style="font-size:15px"><strong>{prov}</strong></p>
      <p style="color:#555;font-size:13px">El proveedor será notificado automáticamente.<br>Motivo registrado en el log de auditoría.</p>
      <p style="font-size:11px;color:#999;margin-top:20px">ID: {doc_id} · {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
    </div></body></html>"""

@app.get("/solicitar_info/{doc_id}", response_class=HTMLResponse)
def solicitar_info(doc_id: str):
    if doc_id not in DOCUMENTOS:
        raise HTTPException(404, "Documento no encontrado")
    doc = DOCUMENTOS[doc_id]
    doc["estado"] = "info_solicitada"
    doc["historial"].append({"accion": "Información solicitada al proveedor", "ts": datetime.datetime.now().isoformat()})
    prov = doc["datos"].get("proveedor", "—")
    return f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:500px;margin:60px auto;text-align:center;color:#333">
    <div style="background:#fff8e1;border:1px solid #ffe082;border-radius:12px;padding:40px">
      <div style="font-size:48px">?</div>
      <h2 style="color:#b8860b;margin:12px 0">Información solicitada</h2>
      <p style="font-size:15px"><strong>{prov}</strong></p>
      <p style="color:#555;font-size:13px">Solicitud enviada al proveedor.<br>SLA extendido 48 horas. Recibirás respuesta en tu email.</p>
      <p style="font-size:11px;color:#999;margin-top:20px">ID: {doc_id} · {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
    </div></body></html>"""

if __name__ == "__main__":
    import uvicorn
    print("\n Motor de Aprobación Documental — Hotel Pacifico Sur")
    print(" ─────────────────────────────────────────────────")
    print(" API corriendo en: http://localhost:8000")
    print(" Docs interactivos: http://localhost:8000/docs")
    print(" ─────────────────────────────────────────────────")
    print(" IMPORTANTE: configura EMAIL_CONFIG con tu cuenta")
    print(" Gmail (contraseña de aplicación) para envíos reales.\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)
