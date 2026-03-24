const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export interface DocResult {
  doc_id: string
  zona: 'verde' | 'amarilla' | 'roja'
  proveedor: string | null
  rut: string | null
  total_clp: number
  folio: string | null
  fecha_emision: string | null
  motivos: string[]
  accion: string
  timestamp: string
  email_enviado: boolean
}

export interface DocListItem extends DocResult {
  archivo: string
  estado: string
}

export async function procesarPDF(file: File): Promise<DocResult> {
  const form = new FormData()
  form.append('archivo', file)
  const res = await fetch(`${API}/procesar`, { method: 'POST', body: form })
  if (!res.ok) throw new Error(`Error ${res.status}`)
  return res.json()
}

export async function listarDocumentos(): Promise<{ total: number; documentos: DocListItem[] }> {
  const res = await fetch(`${API}/documentos`)
  if (!res.ok) throw new Error(`Error ${res.status}`)
  return res.json()
}

export async function healthCheck(): Promise<boolean> {
  try {
    const res = await fetch(`${API}/health`, { signal: AbortSignal.timeout(2000) })
    return res.ok
  } catch { return false }
}

export interface ConfigData {
  email_remitente: string
  email_password: string
  email_aprobador: string
  email_gerencia: string
  whatsapp_activo: boolean
  whatsapp_numero: string
  umbral_verde: number
  umbral_rojo: number
  tolerancia: number
  dias_duplicados: number
  sla_24h: boolean
  sla_48h: boolean
  sla_72h: boolean
  sla_96h: boolean
  email_password_set?: boolean
}

export async function getConfiguracion(): Promise<ConfigData> {
  const res = await fetch(`${API}/configuracion`)
  if (!res.ok) throw new Error(`Error ${res.status}`)
  return res.json()
}

export async function saveConfiguracion(data: Partial<ConfigData>): Promise<{ ok: boolean; email_configurado: boolean }> {
  const res = await fetch(`${API}/configuracion`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(`Error ${res.status}`)
  return res.json()
}
