# Hotel — Sistema de Aprobación Documental

Demo de automatización financiera para hoteles. Clasifica facturas PDF en zonas Verde/Amarilla/Roja y envía notificaciones automáticas por email.

## Stack
- **Frontend**: Next.js 15 + TypeScript + Tailwind CSS
- **Backend**: Python + FastAPI + pdfplumber

## Estructura
```
hotel-demo/        → Frontend Next.js
  app/             → Páginas (Dashboard, Documentos, Configuración)
  components/      → Sidebar
  lib/api.ts       → Cliente HTTP hacia el backend

demo_hotel/        → Backend Python
  motor.py         → API FastAPI + motor de clasificación
  generar_facturas.py → Genera 3 facturas PDF de prueba
  test_motor.py    → Test de clasificación
```

## Cómo correr

### Backend
```bash
cd demo_hotel
pip install fastapi uvicorn pdfplumber python-multipart reportlab
python motor.py
# → http://localhost:8000
```

Variables de entorno del backend:
```bash
GEMINI_API_KEY=tu_clave_de_google_ai
GEMINI_MODEL=gemini-2.0-flash
GEMINI_MAX_RETRIES=2
```
Puedes ponerla en `backend/.env` para desarrollo local o en las variables de entorno de Render para producción.

### Frontend
```bash
cd hotel-demo
npm install
npm run dev
# → http://localhost:3000
```

Variable de entorno del frontend:
```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```
En Vercel, configura `NEXT_PUBLIC_API_URL` apuntando al backend de Render.

## Páginas
- `/` — Dashboard con upload de PDF y pipeline animado en tiempo real
- `/documentos` — Tabla de todos los documentos procesados
- `/configuracion` — Panel sin código: emails, umbrales, WhatsApp, SLA, proveedores

## Gemini
- El backend lee `GEMINI_API_KEY` desde el entorno y, si no existe, usa el fallback local de `backend/config.json`.
- Si Gemini devuelve 503 o responde vacío, el backend reintenta y luego usa un fallback local para no dejar el resumen o el chat en blanco.
- La UI de configuración ya no expone la clave guardada; solo muestra si Gemini está activo y de dónde viene la configuración.

## Zonas de clasificación
| Zona | Criterio | Acción |
|------|----------|--------|
| 🟢 Verde | Proveedor verificado + importe normal | Pago automático |
| 🟡 Amarilla | Anomalía menor (importe fuera de histórico) | Notificación al aprobador |
| 🔴 Roja | Proveedor desconocido o importe sobre umbral | Bloqueo + expediente a gerencia |
