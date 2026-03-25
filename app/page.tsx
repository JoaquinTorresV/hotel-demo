'use client'
import { useState, useCallback, useRef, useEffect } from 'react'
import { Upload, FileText, CheckCircle, XCircle, AlertCircle, ChevronRight, Clock } from 'lucide-react'
import { procesarPDF, listarDocumentos, iaAnalizar, iaResumen, DocResult, DocListItem } from '@/lib/api'

const PASOS = [
  { id: 1, label: 'Recepción del documento',  sub: 'Archivo recibido y registrado' },
  { id: 2, label: 'OCR — Lectura del PDF',     sub: 'Extrayendo RUT, monto, folio, fechas' },
  { id: 3, label: 'Validación legal',          sub: 'Verificando formato SII chileno' },
  { id: 4, label: 'Matching de documentos',    sub: 'Cruzando con órdenes de compra' },
  { id: 5, label: 'Motor de reglas',           sub: 'Aplicando umbrales y lista blanca' },
  { id: 6, label: 'Clasificación en zona',     sub: 'Asignando Verde / Amarilla / Roja' },
  { id: 7, label: 'Acción automática',         sub: 'Pago, notificación o bloqueo' },
]

type PasoEstado = 'idle' | 'active' | 'done'

const ZONA_LABEL: Record<string, string>  = { verde: 'Verde', amarilla: 'Amarilla', roja: 'Roja' }
const ZONA_COLOR: Record<string, string>  = { verde: '#16a34a', amarilla: '#d97706', roja: '#dc2626' }

function ZonaBadge({ zona }: { zona: string }) {
  return (
    <span className={`badge-${zona}`} style={{ padding: '2px 10px', borderRadius: 20, fontSize: 11, fontWeight: 600 }}>
      {ZONA_LABEL[zona] ?? zona}
    </span>
  )
}

function formatCLP(n: number | undefined | null) {
  return n !== null && n !== undefined && typeof n === 'number' ? `$ ${n.toLocaleString('es-CL')} CLP` : '—'
}

function timeAgo(ts: string) {
  const diff = Math.floor((Date.now() - new Date(ts).getTime()) / 1000)
  if (diff < 60) return `hace ${diff}s`
  if (diff < 3600) return `hace ${Math.floor(diff / 60)}min`
  return `hace ${Math.floor(diff / 3600)}h`
}

export default function Dashboard() {
  const [dragging, setDragging]     = useState(false)
  const [pasos, setPasos]           = useState<PasoEstado[]>(Array(7).fill('idle'))
  const [procesando, setProcesando] = useState(false)
  const [resultado, setResultado]   = useState<DocResult | null>(null)
  const [error, setError]           = useState<string | null>(null)
  const [docs, setDocs]             = useState<DocListItem[]>([])
  const [archivo, setArchivo]       = useState<string>('')
  const [iaAnalisis, setIaAnalisis]   = useState<string>('')
  const [iaRes, setIaRes]             = useState<string>('')
  const [iaLoading, setIaLoading]     = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    listarDocumentos().then(d => setDocs(d.documentos.slice().reverse())).catch(() => {})
  }, [])

  const animarPipeline = useCallback((onDone: () => void) => {
    const delays    = [0, 600, 1100, 1700, 2400, 3100, 3700]
    const durations = [500, 450, 550, 650, 650, 600, 500]
    setPasos(Array(7).fill('idle'))
    delays.forEach((delay, i) => {
      setTimeout(() => {
        setPasos(prev => prev.map((s, j) => j === i ? 'active' : s))
        setTimeout(() => {
          setPasos(prev => prev.map((s, j) => j === i ? 'done' : s))
          if (i === 6) onDone()
        }, durations[i])
      }, delay)
    })
  }, [])

  const procesarArchivo = useCallback(async (file: File) => {
    if (!file.name.endsWith('.pdf')) { setError('Solo se aceptan archivos PDF'); return }
    setError(null); setResultado(null); setArchivo(file.name); setProcesando(true)
    animarPipeline(async () => {
      try {
        const res = await procesarPDF(file)
        setResultado(res)
        setDocs(prev => [{ ...res, archivo: file.name, estado: res.zona } as DocListItem, ...prev])
        // Llamadas IA en paralelo (no bloqueante)
        setIaAnalisis(''); setIaRes(''); setIaLoading(true)
        Promise.all([
          iaAnalizar(res.doc_id).catch(() => ({ analisis: '', disponible: false })),
          iaResumen(res.doc_id).catch(() => ({ resumen: '', disponible: false })),
        ]).then(([analisis, resumen]) => {
          setIaAnalisis((analisis as any).analisis || '')
          setIaRes((resumen as any).resumen || '')
          setIaLoading(false)
        })
      } catch {
        setError('No se pudo conectar al motor. ¿Está corriendo en localhost:8000?')
      } finally {
        setProcesando(false)
      }
    })
  }, [animarPipeline])

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) procesarArchivo(file)
  }, [procesarArchivo])

  const isRunning = procesando || pasos.some(p => p === 'active')

  return (
    <div style={{ padding: '32px 36px', maxWidth: 1100 }}>
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ margin: 0, fontSize: 22, fontWeight: 600 }}>Dashboard</h1>
        <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--gray-400)' }}>
          Sube una factura y observa el pipeline de aprobación en tiempo real
        </p>
      </div>

      <KPIBar docs={docs} />

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginTop: 24 }}>

        {/* Columna izquierda */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ background: 'white', borderRadius: 16, padding: 24, border: '1px solid var(--gray-200)' }}>
            <p style={{ margin: '0 0 14px', fontSize: 13, fontWeight: 600, color: 'var(--gray-600)' }}>Subir factura PDF</p>
            <div
              className={`upload-zone ${dragging ? 'drag-over' : ''}`}
              style={{ padding: 32, textAlign: 'center' }}
              onDragOver={e => { e.preventDefault(); setDragging(true) }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              onClick={() => !isRunning && inputRef.current?.click()}
            >
              <input ref={inputRef} type="file" accept=".pdf" style={{ display: 'none' }} onChange={e => { const f = e.target.files?.[0]; if (f) procesarArchivo(f) }} />
              <div style={{ width: 44, height: 44, borderRadius: 12, background: '#eff6ff', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 12px' }}>
                <Upload size={20} color="var(--accent)" />
              </div>
              {isRunning ? (
                <p style={{ margin: 0, fontSize: 13, color: 'var(--accent)', fontWeight: 500 }}>Procesando {archivo}…</p>
              ) : (
                <>
                  <p style={{ margin: 0, fontSize: 13, fontWeight: 500 }}>Arrastra tu factura aquí</p>
                  <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--gray-400)' }}>o haz clic para seleccionar · Solo PDF</p>
                </>
              )}
            </div>
            {error && (
              <div style={{ marginTop: 12, padding: '10px 14px', background: 'var(--rojo-bg)', border: '1px solid var(--rojo-bd)', borderRadius: 8, fontSize: 12, color: 'var(--rojo)' }}>
                {error}
              </div>
            )}
          </div>

          {/* Pipeline */}
          <div style={{ background: 'white', borderRadius: 16, padding: 24, border: '1px solid var(--gray-200)' }}>
            <p style={{ margin: '0 0 16px', fontSize: 13, fontWeight: 600, color: 'var(--gray-600)' }}>Pipeline de procesamiento</p>
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {PASOS.map((paso, i) => {
                const est = pasos[i]
                return (
                  <div key={paso.id} className={`step-${est}`} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 0', borderBottom: i < 6 ? '1px solid var(--gray-100)' : 'none', transition: 'opacity 0.25s' }}>
                    <div className={`step-icon-${est}`} style={{ width: 28, height: 28, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, transition: 'all 0.25s' }}>
                      {est === 'done'   ? <CheckCircle size={14} color="var(--verde)" /> :
                       est === 'active' ? <span className="spinner" /> :
                       <span style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: 10, fontWeight: 600 }}>{paso.id}</span>}
                    </div>
                    <div style={{ flex: 1 }}>
                      <p style={{ margin: 0, fontSize: 12, fontWeight: 500 }}>{paso.label}</p>
                      {est !== 'idle' && <p style={{ margin: 0, fontSize: 11, color: 'var(--gray-400)' }}>{paso.sub}</p>}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>

        {/* Columna derecha: Resultado */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ background: 'white', borderRadius: 16, padding: 24, border: '1px solid var(--gray-200)', minHeight: 200 }}>
            <p style={{ margin: '0 0 16px', fontSize: 13, fontWeight: 600, color: 'var(--gray-600)' }}>Resultado de clasificación</p>

            {!resultado && !isRunning && (
              <div style={{ textAlign: 'center', padding: '40px 20px', color: 'var(--gray-400)' }}>
                <FileText size={32} style={{ opacity: 0.3, margin: '0 auto 12px', display: 'block' }} />
                <p style={{ margin: 0, fontSize: 13 }}>Sube una factura para ver el resultado</p>
              </div>
            )}

            {isRunning && !resultado && (
              <div style={{ textAlign: 'center', padding: '40px 20px' }}>
                <span className="spinner" style={{ width: 28, height: 28, display: 'block', margin: '0 auto 14px', borderWidth: 3 }} />
                <p style={{ margin: 0, fontSize: 13, color: 'var(--gray-400)' }}>Analizando documento…</p>
              </div>
            )}

            {resultado && (
              <div className={`result-${resultado.zona} fade-up`} style={{ borderRadius: 12, padding: 18 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    {resultado.zona === 'verde'    && <CheckCircle size={18} color="var(--verde)" />}
                    {resultado.zona === 'amarilla' && <AlertCircle size={18} color="var(--amarillo)" />}
                    {resultado.zona === 'roja'     && <XCircle size={18} color="var(--rojo)" />}
                    <span style={{ fontSize: 14, fontWeight: 600, color: ZONA_COLOR[resultado.zona] }}>
                      Zona {ZONA_LABEL[resultado.zona]}
                    </span>
                  </div>
                  <ZonaBadge zona={resultado.zona} />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 14 }}>
                  {([
                    ['Proveedor', resultado.proveedor ?? '—'],
                    ['RUT',       resultado.rut ?? '—'],
                    ['Folio',     resultado.folio ? `N° ${resultado.folio}` : '—'],
                    ['Total',     formatCLP(resultado.total_clp)],
                    ['Emisión',   resultado.fecha_emision ?? '—'],
                    ['ID doc',    resultado.doc_id],
                  ] as [string, string][]).map(([k, v]) => (
                    <div key={k} style={{ background: 'rgba(255,255,255,0.6)', borderRadius: 8, padding: '8px 10px' }}>
                      <p style={{ margin: 0, fontSize: 10, color: 'var(--gray-400)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{k}</p>
                      <p style={{ margin: '2px 0 0', fontSize: 12, fontWeight: 500, fontFamily: ['RUT','Total','ID doc'].includes(k) ? 'IBM Plex Mono, monospace' : 'inherit', wordBreak: 'break-all' }}>{v}</p>
                    </div>
                  ))}
                </div>

                <div style={{ marginBottom: 12 }}>
                  <p style={{ margin: '0 0 6px', fontSize: 11, fontWeight: 600, color: 'var(--gray-600)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Reglas aplicadas</p>
                  {resultado.motivos && resultado.motivos.length > 0 ? resultado.motivos.map((m, i) => (
                    <div key={`motivo-${i}`} style={{ display: 'flex', alignItems: 'flex-start', gap: 6, marginBottom: 4 }}>
                      <ChevronRight size={12} style={{ flexShrink: 0, marginTop: 2, color: ZONA_COLOR[resultado.zona] }} />
                      <span style={{ fontSize: 12 }}>{m}</span>
                    </div>
                  )) : <p style={{ fontSize: 12, color: 'var(--gray-400)' }}>Sin detalle de reglas</p>}
                </div>

                <div style={{ background: 'rgba(255,255,255,0.7)', borderRadius: 8, padding: '10px 12px', marginBottom: 10 }}>
                  <p style={{ margin: 0, fontSize: 12, fontWeight: 500, color: ZONA_COLOR[resultado.zona] }}>{resultado.accion}</p>
                </div>

                {resultado.email_enviado && (
                  <p style={{ margin: 0, fontSize: 11, color: 'var(--gray-400)', display: 'flex', alignItems: 'center', gap: 4 }}>
                    <CheckCircle size={11} /> Notificación por email enviada automáticamente
                  </p>
                )}

                {/* ── Bloque IA ── */}
                {(iaLoading || iaRes || iaAnalisis) && (
                  <div style={{ marginTop: 12, borderTop: '1px solid rgba(0,0,0,0.06)', paddingTop: 12 }}>
                    <p style={{ margin: '0 0 8px', fontSize: 10, fontWeight: 600, color: ZONA_COLOR[resultado.zona], textTransform: 'uppercase', letterSpacing: '0.06em', display: 'flex', alignItems: 'center', gap: 5 }}>
                      <span style={{ fontSize: 13 }}>✦</span> Análisis con IA
                    </p>
                    {iaLoading && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--gray-400)' }}>
                        <span className="spinner" style={{ width: 12, height: 12, flexShrink: 0 }} />
                        Analizando con Gemini…
                      </div>
                    )}
                    {iaRes && !iaLoading && (
                      <div style={{ background: 'rgba(255,255,255,0.55)', borderRadius: 8, padding: '8px 10px', marginBottom: 8 }}>
                        <p style={{ margin: '0 0 3px', fontSize: 10, fontWeight: 600, color: 'var(--gray-600)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Resumen ejecutivo</p>
                        <p style={{ margin: 0, fontSize: 12, lineHeight: 1.6, color: 'var(--gray-900)' }}>{iaRes}</p>
                      </div>
                    )}
                    {iaAnalisis && !iaLoading && (
                      <div style={{ background: 'rgba(255,255,255,0.55)', borderRadius: 8, padding: '8px 10px' }}>
                        <p style={{ margin: '0 0 3px', fontSize: 10, fontWeight: 600, color: 'var(--gray-600)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Análisis detallado</p>
                        <p style={{ margin: 0, fontSize: 12, lineHeight: 1.6, color: 'var(--gray-900)' }}>{iaAnalisis}</p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>

          {docs.length > 0 && (
            <div style={{ background: 'white', borderRadius: 16, padding: 24, border: '1px solid var(--gray-200)' }}>
              <p style={{ margin: '0 0 14px', fontSize: 13, fontWeight: 600, color: 'var(--gray-600)' }}>Últimos documentos</p>
              {docs.slice(0, 5).map((doc, i) => (
                <div key={doc.doc_id || i} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 0', borderBottom: i < Math.min(docs.length, 5) - 1 ? '1px solid var(--gray-100)' : 'none' }}>
                  <ZonaBadge zona={doc.zona} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p style={{ margin: 0, fontSize: 12, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{doc.proveedor ?? doc.archivo}</p>
                    <p style={{ margin: 0, fontSize: 11, color: 'var(--gray-400)', fontFamily: 'IBM Plex Mono, monospace' }}>{formatCLP(doc.total_clp)}</p>
                  </div>
                  <span style={{ fontSize: 11, color: 'var(--gray-400)', display: 'flex', alignItems: 'center', gap: 3, whiteSpace: 'nowrap' }}>
                    <Clock size={10} />{timeAgo(doc.timestamp)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

      </div>
    </div>
  )
}

function KPIBar({ docs }: { docs: DocListItem[] }) {
  const verdes    = docs.filter(d => d.zona === 'verde').length
  const amarillas = docs.filter(d => d.zona === 'amarilla').length
  const rojas     = docs.filter(d => d.zona === 'roja').length
  const total     = docs.length
  const pct       = total ? Math.round((verdes / total) * 100) : 0
  const kpis = [
    { label: 'Automatizados', value: `${pct}%`, sub: `${verdes} de ${total} docs`,     color: 'var(--verde)' },
    { label: 'Zona Verde',    value: verdes,     sub: 'Pago automático',               color: 'var(--verde)' },
    { label: 'Zona Amarilla', value: amarillas,  sub: 'Esperando aprobación',          color: 'var(--amarillo)' },
    { label: 'Zona Roja',     value: rojas,      sub: 'Bloqueados',                   color: 'var(--rojo)' },
  ]
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14 }}>
      {kpis.map(k => (
        <div key={k.label} style={{ background: 'white', border: '1px solid var(--gray-200)', borderRadius: 12, padding: '16px 18px' }}>
          <p style={{ margin: 0, fontSize: 11, fontWeight: 600, color: 'var(--gray-400)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{k.label}</p>
          <p style={{ margin: '6px 0 2px', fontSize: 24, fontWeight: 600, color: k.color, fontFamily: 'IBM Plex Mono, monospace' }}>{k.value}</p>
          <p style={{ margin: 0, fontSize: 11, color: 'var(--gray-400)' }}>{k.sub}</p>
        </div>
      ))}
    </div>
  )
}
