# Renaissance Santiago Hotel — Sistema de Aprobación Documental

Demo de automatización financiera. Clasifica facturas PDF en zonas Verde/Amarilla/Roja con IA.

## Stack
- **Frontend**: Next.js 15 + TypeScript + Tailwind — desplegado en **Vercel**
- **Backend**: Python + FastAPI + pdfplumber — desplegado en **Railway**

## Deploy en producción

### 1. Backend en Railway (gratis)
1. Ve a [railway.app](https://railway.app) → New Project → Deploy from GitHub
2. Selecciona este repositorio
3. Railway detecta `railway.toml` automáticamente
4. En Variables de entorno agrega:
   - `GEMINI_API_KEY` → tu API key de Gemini

### 2. Frontend en Vercel
1. Ve a [vercel.com](https://vercel.com) → New Project → importa este repo
2. En Variables de entorno agrega:
   - `NEXT_PUBLIC_API_URL` → la URL que te dio Railway (ej: `https://hotel-demo-production.up.railway.app`)
3. Deploy

## Desarrollo local

### Backend
```bash
cd backend
pip install -r requirements.txt
python motor.py
# → http://localhost:8000
```

### Frontend
```bash
npm install
npm run dev
# → http://localhost:3000
```

## Páginas
- `/` — Dashboard con upload de PDF y pipeline animado en tiempo real
- `/documentos` — Tabla de documentos procesados con filtros
- `/emision` — Flujo 2: facturas que el hotel emite con aprobación dinámica
- `/chat` — Chat IA con los documentos del hotel
- `/configuracion` — Panel sin código: emails, Gemini, umbrales, proveedores

## Zonas de clasificación
| Zona | Criterio | Acción |
|------|----------|--------|
| 🟢 Verde | Proveedor verificado + monto normal | Pago automático |
| 🟡 Amarilla | Anomalía menor | Email al aprobador con 1 clic |
| 🔴 Roja | Proveedor desconocido o monto crítico | Bloqueo + expediente a gerencia |

## Facturas de prueba
En `backend/facturas/` hay 3 PDFs listos para la demo:
- `factura_verde.pdf` — Distribuidora López · $893.500 CLP → Verde
- `factura_amarilla.pdf` — Sistemas Técnicos SA · $2.058.700 CLP → Amarilla  
- `factura_roja.pdf` — Constructora Metropolitana · $29.155.000 CLP → Roja
