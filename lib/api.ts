// Todas las llamadas van a /api/* — Vercel las rutea al Python serverless
// El frontend (localStorage) guarda el historial y la config

function fetchTimeout(url: string, opts: RequestInit = {}, ms = 30000) {
  const ctrl = new AbortController()
  const id   = setTimeout(() => ctrl.abort(), ms)
  return fetch(url, { ...opts, signal: ctrl.signal }).finally(() => clearTimeout(id))
}

function getApiBase(): string {
  if (process.env.NEXT_PUBLIC_API_URL) return process.env.NEXT_PUBLIC_API_URL
  if (typeof window !== 'undefined' && window.location.hostname === 'localhost') {
    return 'http://localhost:8000'
  }
  return '/api'
}

const API_BASE = getApiBase()

// ── Config desde localStorage ─────────────────────────────────────────────
export interface Config {
  email_remitente:  string
  email_password:   string
  email_aprobador:  string
  email_gerencia:   string
  gemini_api_key:   string
  whatsapp_activo:  boolean
  umbral_verde:     number
  umbral_rojo:      number
  tolerancia:       number
}

export const DEFAULT_CONFIG: Config = {
  email_remitente: '', email_password: '',
  email_aprobador: '', email_gerencia: '',
  gemini_api_key: '', whatsapp_activo: false,
  umbral_verde: 1000000, umbral_rojo: 10000000, tolerancia: 15,
}

export function getConfig(): Config {
  if (typeof window === 'undefined') return DEFAULT_CONFIG
  try {
    return { ...DEFAULT_CONFIG, ...JSON.parse(localStorage.getItem('renaissance_config') || '{}') }
  } catch { return DEFAULT_CONFIG }
}

export function saveConfig(cfg: Config) {
  localStorage.setItem('renaissance_config', JSON.stringify(cfg))
}

// ── Historial de documentos en localStorage ───────────────────────────────
export interface DocResult {
  doc_id: string; zona: 'verde' | 'amarilla' | 'roja'
  proveedor: string | null; rut: string | null; total_clp: number
  folio: string | null; fecha_emision: string | null; fecha_vencimiento: string | null
  motivos: string[]; accion: string; timestamp: string
  archivo: string; estado: string; email_enviado: boolean
  ia_resumen?: string; ia_analisis?: string
}

export function getDocumentos(): DocResult[] {
  if (typeof window === 'undefined') return []
  try { return JSON.parse(localStorage.getItem('renaissance_docs') || '[]') }
  catch { return [] }
}

export function saveDocumento(doc: DocResult) {
  const docs = getDocumentos()
  const idx  = docs.findIndex(d => d.doc_id === doc.doc_id)
  if (idx >= 0) docs[idx] = doc
  else docs.unshift(doc)
  localStorage.setItem('renaissance_docs', JSON.stringify(docs))
}

export function clearDocumentos() {
  localStorage.removeItem('renaissance_docs')
}

// ── Facturas emitidas en localStorage ────────────────────────────────────
export interface FacturaEmitida {
  factura_id: string; cliente: string; rut_cliente: string
  concepto: string; monto_neto: number; iva: number; total: number
  aprobadores: any[]; aprobaciones: Record<string, string>
  estado: string; area_pendiente: string | null
  progreso: number; total_etapas: number; timestamp: string
}

function numOrZero(v: unknown): number {
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : 0
}

function normalizeFacturaEmitida(raw: any): FacturaEmitida {
  return {
    factura_id: String(raw?.factura_id ?? ''),
    cliente: String(raw?.cliente ?? ''),
    rut_cliente: String(raw?.rut_cliente ?? ''),
    concepto: String(raw?.concepto ?? ''),
    monto_neto: numOrZero(raw?.monto_neto),
    iva: numOrZero(raw?.iva),
    total: numOrZero(raw?.total),
    aprobadores: Array.isArray(raw?.aprobadores) ? raw.aprobadores : [],
    aprobaciones: raw?.aprobaciones && typeof raw.aprobaciones === 'object' ? raw.aprobaciones : {},
    estado: String(raw?.estado ?? 'pendiente'),
    area_pendiente: raw?.area_pendiente == null ? null : String(raw.area_pendiente),
    progreso: numOrZero(raw?.progreso),
    total_etapas: numOrZero(raw?.total_etapas),
    timestamp: String(raw?.timestamp ?? new Date().toISOString()),
  }
}

export function getFacturasEmitidas(): FacturaEmitida[] {
  if (typeof window === 'undefined') return []
  try {
    const raw = JSON.parse(localStorage.getItem('renaissance_emision') || '[]')
    return Array.isArray(raw) ? raw.map(normalizeFacturaEmitida) : []
  }
  catch { return [] }
}

export function saveFacturaEmitida(f: FacturaEmitida) {
  const lista = getFacturasEmitidas()
  const idx   = lista.findIndex(x => x.factura_id === f.factura_id)
  if (idx >= 0) lista[idx] = f
  else lista.unshift(f)
  localStorage.setItem('renaissance_emision', JSON.stringify(lista))
}

export function clearFacturasEmitidas() {
  localStorage.removeItem('renaissance_emision')
}

// ── API calls ─────────────────────────────────────────────────────────────
export async function procesarPDF(file: File): Promise<DocResult> {
  const cfg  = getConfig()
  const form = new FormData()
  form.append('archivo', file)
  form.append('email_remitente',  cfg.email_remitente)
  form.append('email_password',   cfg.email_password)
  form.append('email_aprobador',  cfg.email_aprobador)
  form.append('email_gerencia',   cfg.email_gerencia)
  form.append('base_url',         window.location.origin)
  const res = await fetchTimeout(`${API_BASE}/procesar`, { method: 'POST', body: form }, 60000)
  if (!res.ok) throw new Error(`Error ${res.status}`)
  return res.json()
}

export async function healthCheck(): Promise<boolean> {
  try {
    const res = await fetchTimeout(`${API_BASE}/health`, {}, 8000)
    return res.ok
  } catch { return false }
}

export async function iaAnalizar(doc: DocResult): Promise<string> {
  const res = await fetchTimeout(`${API_BASE}/ia/analizar`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      doc_data: doc,
      zona: doc.zona,
      motivos: doc.motivos,
    }),
  }, 30000)
  if (!res.ok) throw new Error(`Error ${res.status}`)
  const data = await res.json()
  return data.analisis || ''
}

export async function iaResumen(doc: DocResult): Promise<string> {
  const res = await fetchTimeout(`${API_BASE}/ia/resumen`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      doc_data: doc,
      zona: doc.zona,
    }),
  }, 30000)
  if (!res.ok) throw new Error(`Error ${res.status}`)
  const data = await res.json()
  return data.resumen || ''
}

export async function iaChat(pregunta: string): Promise<{ respuesta: string; disponible: boolean }> {
  const res = await fetchTimeout(`${API_BASE}/ia/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pregunta, documentos: getDocumentos() }),
  }, 30000)
  if (!res.ok) throw new Error(`Error ${res.status}`)
  return res.json()
}

export async function iaEstado(): Promise<{ disponible: boolean; proveedor: string; configurar_en?: string }> {
  const res = await fetchTimeout(`${API_BASE}/ia/estado`, {}, 8000)
  if (!res.ok) throw new Error(`Error ${res.status}`)
  return res.json()
}

export async function crearEmision(body: any): Promise<FacturaEmitida> {
  const cfg = getConfig()
  const res = await fetchTimeout(`${API_BASE}/emision/crear`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ...body,
      email_remitente: cfg.email_remitente,
      email_password:  cfg.email_password,
      base_url:        typeof window !== 'undefined' ? window.location.origin : '',
    }),
  }, 30000)
  if (!res.ok) throw new Error(`Error ${res.status}`)
  return res.json()
}

export async function getDepartamentos(): Promise<{ id: string; nombre: string }[]> {
  const res = await fetchTimeout(`${API_BASE}/emision/departamentos`)
  const data = await res.json()
  return data.departamentos || []
}
