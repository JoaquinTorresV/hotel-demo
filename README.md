# Hotel Pacifico Sur — Sistema de Aprobación Documental

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

### Frontend
```bash
cd hotel-demo
npm install
npm run dev
# → http://localhost:3000
```

## Páginas
- `/` — Dashboard con upload de PDF y pipeline animado en tiempo real
- `/documentos` — Tabla de todos los documentos procesados
- `/configuracion` — Panel sin código: emails, umbrales, WhatsApp, SLA, proveedores

## Zonas de clasificación
| Zona | Criterio | Acción |
|------|----------|--------|
| 🟢 Verde | Proveedor verificado + importe normal | Pago automático |
| 🟡 Amarilla | Anomalía menor (importe fuera de histórico) | Notificación al aprobador |
| 🔴 Roja | Proveedor desconocido o importe sobre umbral | Bloqueo + expediente a gerencia |
