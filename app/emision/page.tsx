'use client'
import { useState, useEffect } from 'react'
import { Send, CheckCircle, XCircle, Clock, AlertCircle, Plus, ChevronRight, Trash2, GripVertical, X } from 'lucide-react'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface Departamento { id: string; nombre: string }
interface Aprobador { area_id: string; nombre: string; email: string; orden: number }
interface FacturaEmitida {
  id: string; cliente: string; rut_cliente: string; concepto: string
  monto_neto: number; iva: number; total: number; descripcion: string
  estado: 'pendiente' | 'en_proceso' | 'aprobada' | 'rechazada'
  aprobaciones: Record<string, string>; aprobadores: Aprobador[]
  area_pendiente: string | null; progreso: number; total_etapas: number
  timestamp: string; historial: { accion: string; ts: string }[]
}

const ESTADO_CFG: Record<string, { label: string; color: string; bg: string }> = {
  pendiente:  { label: 'Pendiente',  color: 'var(--gray-600)',  bg: '#f1f5f9' },
  en_proceso: { label: 'En proceso', color: 'var(--amarillo)',  bg: 'var(--amarillo-bg)' },
  aprobada:   { label: 'Aprobada',   color: 'var(--verde)',     bg: 'var(--verde-bg)' },
  rechazada:  { label: 'Rechazada',  color: 'var(--rojo)',      bg: 'var(--rojo-bg)' },
}

function fmtCLP(n: number) { return `$ ${n.toLocaleString('es-CL')} CLP` }
function fmtDate(ts: string) {
  return new Date(ts).toLocaleString('es-CL', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

const inp: React.CSSProperties = {
  width: '100%', padding: '9px 12px', borderRadius: 8,
  border: '1px solid var(--gray-200)', fontSize: 13,
  fontFamily: 'Sora, sans-serif', outline: 'none',
  background: 'white', color: 'var(--gray-900)',
}

export default function Emision() {
  const [facturas, setFacturas]     = useState<FacturaEmitida[]>([])
  const [deptos, setDeptos]         = useState<Departamento[]>([])
  const [loading, setLoading]       = useState(true)
  const [showForm, setShowForm]     = useState(false)
  const [enviando, setEnviando]     = useState(false)
  const [detalle, setDetalle]       = useState<FacturaEmitida | null>(null)

  // Campos del formulario
  const [cliente, setCliente]       = useState('')
  const [rut, setRut]               = useState('')
  const [concepto, setConcepto]     = useState('')
  const [monto, setMonto]           = useState('')
  const [desc, setDesc]             = useState('')

  // Aprobadores dinámicos
  const [aprobadores, setAprobadores] = useState<Aprobador[]>([])

  const cargar = () => {
    setLoading(true)
    Promise.all([
      fetch(`${API}/emision/listar`).then(r => r.json()).catch(() => ({ facturas: [] })),
      fetch(`${API}/emision/departamentos`).then(r => r.json()).catch(() => ({ departamentos: [] })),
    ]).then(([f, d]) => {
      setFacturas(f.facturas || [])
      setDeptos(d.departamentos || [])
      setLoading(false)
    })
  }
  useEffect(() => { cargar() }, [])

  // Agregar aprobador
  const agregarAprobador = () => {
    setAprobadores(prev => [...prev, {
      area_id: '', nombre: '', email: '', orden: prev.length + 1
    }])
  }

  // Quitar aprobador
  const quitarAprobador = (idx: number) => {
    setAprobadores(prev => prev.filter((_, i) => i !== idx).map((a, i) => ({ ...a, orden: i + 1 })))
  }

  // Actualizar campo de aprobador
  const updateAprobador = (idx: number, field: keyof Aprobador, value: string) => {
    setAprobadores(prev => prev.map((a, i) => {
      if (i !== idx) return a
      const updated = { ...a, [field]: value }
      // Si cambia el depto, auto-fill el nombre
      if (field === 'area_id') {
        const depto = deptos.find(d => d.id === value)
        if (depto) updated.nombre = depto.nombre
      }
      return updated
    }))
  }

  const montoNum  = parseInt(monto.replace(/\D/g, '') || '0')
  const ivaCalc   = Math.round(montoNum * 0.19)
  const totalCalc = montoNum + ivaCalc
  const formValido = cliente && rut && concepto && monto && aprobadores.length > 0 &&
    aprobadores.every(a => a.area_id && a.email)

  const resetForm = () => {
    setCliente(''); setRut(''); setConcepto(''); setMonto(''); setDesc('')
    setAprobadores([]); setShowForm(false)
  }

  const crear = async () => {
    if (!formValido) return
    setEnviando(true)
    try {
      const res = await fetch(`${API}/emision/crear`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cliente, rut_cliente: rut, concepto, monto_neto: montoNum,
          descripcion: desc, aprobadores,
        }),
      })
      if (res.ok) { resetForm(); cargar() }
    } finally { setEnviando(false) }
  }

  return (
    <div style={{ padding: '32px 36px', maxWidth: 1100 }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <div style={{ display: 'inline-flex', alignItems: 'center', background: '#dbeafe', padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 600, color: 'var(--accent)', marginBottom: 6 }}>
            Flujo 2 — Facturas que el hotel emite
          </div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 600 }}>Emisión y aprobación interna</h1>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--gray-400)' }}>
            Facturas que Renaissance cobra a sus clientes · Define el flujo de aprobación para cada caso
          </p>
        </div>
        <button onClick={() => setShowForm(true)}
          style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 18px', background: 'var(--accent)', color: 'white', border: 'none', borderRadius: 10, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'Sora, sans-serif' }}>
          <Plus size={15} /> Nueva factura
        </button>
      </div>

      {/* Aviso */}
      <div style={{ background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 10, padding: '10px 16px', marginBottom: 20, fontSize: 12, color: '#1d4ed8', display: 'flex', gap: 8 }}>
        <AlertCircle size={14} style={{ flexShrink: 0, marginTop: 1 }} />
        <span>Aquí gestionas las facturas que <strong>Renaissance le cobra a sus clientes</strong>. Cada factura define su propio flujo de aprobación — tú eliges cuántas etapas y qué área aprueba en cada una.</span>
      </div>

      {/* Tabla */}
      <div style={{ background: 'white', border: '1px solid var(--gray-200)', borderRadius: 16, overflow: 'hidden' }}>
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--gray-400)', fontSize: 13 }}>Cargando…</div>
        ) : facturas.length === 0 ? (
          <div style={{ padding: 60, textAlign: 'center' }}>
            <Send size={32} style={{ color: 'var(--gray-200)', margin: '0 auto 12px', display: 'block' }} />
            <p style={{ margin: 0, fontSize: 13, color: 'var(--gray-400)' }}>No hay facturas en proceso.</p>
            <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--gray-400)' }}>Crea la primera con "Nueva factura".</p>
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--gray-100)', background: 'var(--gray-50)' }}>
                {['Estado','Cliente','Concepto','Total','Flujo de aprobación','Área pendiente','Creada'].map(h => (
                  <th key={h} style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: 'var(--gray-400)', textTransform: 'uppercase', letterSpacing: '0.05em', whiteSpace: 'nowrap' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {facturas.map((f, i) => {
                const est = ESTADO_CFG[f.estado] || ESTADO_CFG.pendiente
                return (
                  <tr key={f.id} onClick={() => setDetalle(f)}
                    style={{ borderBottom: '1px solid var(--gray-100)', background: i % 2 === 0 ? 'white' : 'var(--gray-50)', cursor: 'pointer' }}
                    onMouseEnter={e => (e.currentTarget.style.background = '#f0f7ff')}
                    onMouseLeave={e => (e.currentTarget.style.background = i % 2 === 0 ? 'white' : 'var(--gray-50)')}>
                    <td style={{ padding: '12px 16px' }}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, background: est.bg, color: est.color, padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 600 }}>
                        {est.label}
                      </span>
                    </td>
                    <td style={{ padding: '12px 16px', fontWeight: 500 }}>{f.cliente}</td>
                    <td style={{ padding: '12px 16px', color: 'var(--gray-600)', maxWidth: 180 }}>
                      <span style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.concepto}</span>
                    </td>
                    <td style={{ padding: '12px 16px', fontFamily: 'IBM Plex Mono, monospace', fontWeight: 600, color: 'var(--accent)', whiteSpace: 'nowrap' }}>
                      {fmtCLP(f.total)}
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <div style={{ flex: 1, height: 5, background: 'var(--gray-100)', borderRadius: 3, minWidth: 60, overflow: 'hidden' }}>
                          <div style={{ height: '100%', width: `${f.total_etapas > 0 ? (f.progreso / f.total_etapas) * 100 : 0}%`, background: f.estado === 'aprobada' ? 'var(--verde)' : f.estado === 'rechazada' ? 'var(--rojo)' : 'var(--accent)', borderRadius: 3 }} />
                        </div>
                        <span style={{ fontSize: 11, color: 'var(--gray-400)', whiteSpace: 'nowrap' }}>{f.progreso}/{f.total_etapas}</span>
                      </div>
                    </td>
                    <td style={{ padding: '12px 16px', fontSize: 12, color: f.area_pendiente ? 'var(--amarillo)' : 'var(--verde)' }}>
                      {f.area_pendiente ?? (f.estado === 'aprobada' ? 'Completada ✓' : '—')}
                    </td>
                    <td style={{ padding: '12px 16px', fontSize: 12, color: 'var(--gray-400)', whiteSpace: 'nowrap' }}>
                      {fmtDate(f.timestamp)}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* ── MODAL NUEVA FACTURA ── */}
      {showForm && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 50, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
          <div style={{ background: 'white', borderRadius: 16, width: '100%', maxWidth: 640, maxHeight: '92vh', overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>

            {/* Header modal */}
            <div style={{ padding: '20px 24px 16px', borderBottom: '1px solid var(--gray-100)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
              <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>Nueva factura a emitir</h2>
              <button onClick={resetForm} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--gray-400)', padding: 4 }}>
                <X size={18} />
              </button>
            </div>

            <div style={{ padding: '20px 24px', flex: 1, overflowY: 'auto' }}>

              {/* Datos de la factura */}
              <p style={{ margin: '0 0 12px', fontSize: 12, fontWeight: 600, color: 'var(--gray-600)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Datos de la factura</p>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
                <div style={{ gridColumn: '1/-1' }}>
                  <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--gray-600)', marginBottom: 5 }}>Nombre del cliente *</label>
                  <input style={inp} placeholder="Ej: Banco Santander Chile" value={cliente} onChange={e => setCliente(e.target.value)} />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--gray-600)', marginBottom: 5 }}>RUT del cliente *</label>
                  <input style={inp} placeholder="Ej: 97.036.000-K" value={rut} onChange={e => setRut(e.target.value)} />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--gray-600)', marginBottom: 5 }}>Monto neto (CLP) *</label>
                  <input style={inp} placeholder="Ej: 4500000" value={monto} onChange={e => setMonto(e.target.value)} />
                </div>
                <div style={{ gridColumn: '1/-1' }}>
                  <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--gray-600)', marginBottom: 5 }}>Concepto *</label>
                  <input style={inp} placeholder="Ej: Evento corporativo — Salón Gran Santiago, 200 personas" value={concepto} onChange={e => setConcepto(e.target.value)} />
                </div>
                <div style={{ gridColumn: '1/-1' }}>
                  <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--gray-600)', marginBottom: 5 }}>Descripción adicional</label>
                  <input style={inp} placeholder="Detalles del servicio..." value={desc} onChange={e => setDesc(e.target.value)} />
                </div>
              </div>

              {/* Preview montos */}
              {montoNum > 0 && (
                <div style={{ background: 'var(--gray-50)', border: '1px solid var(--gray-200)', borderRadius: 8, padding: '10px 14px', marginBottom: 20 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 3 }}>
                    <span style={{ color: 'var(--gray-500)' }}>Neto</span>
                    <span style={{ fontFamily: 'IBM Plex Mono, monospace' }}>{fmtCLP(montoNum)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 6 }}>
                    <span style={{ color: 'var(--gray-500)' }}>IVA 19%</span>
                    <span style={{ fontFamily: 'IBM Plex Mono, monospace' }}>{fmtCLP(ivaCalc)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, fontWeight: 600, borderTop: '1px solid var(--gray-200)', paddingTop: 6 }}>
                    <span>Total a cobrar</span>
                    <span style={{ fontFamily: 'IBM Plex Mono, monospace', color: 'var(--accent)' }}>{fmtCLP(totalCalc)}</span>
                  </div>
                </div>
              )}

              {/* Aprobadores dinámicos */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                <div>
                  <p style={{ margin: 0, fontSize: 12, fontWeight: 600, color: 'var(--gray-600)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    Flujo de aprobación *
                  </p>
                  <p style={{ margin: '2px 0 0', fontSize: 11, color: 'var(--gray-400)' }}>
                    Se notifica en orden — cada área recibe el email cuando la anterior aprueba
                  </p>
                </div>
                <button onClick={agregarAprobador}
                  style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '6px 12px', background: 'var(--gray-50)', border: '1px solid var(--gray-200)', borderRadius: 8, fontSize: 12, cursor: 'pointer', fontFamily: 'Sora, sans-serif', color: 'var(--gray-700)' }}>
                  <Plus size={13} /> Agregar etapa
                </button>
              </div>

              {aprobadores.length === 0 && (
                <div style={{ textAlign: 'center', padding: '20px 16px', border: '1.5px dashed var(--gray-200)', borderRadius: 10, marginBottom: 16 }}>
                  <p style={{ margin: 0, fontSize: 13, color: 'var(--gray-400)' }}>Sin etapas aún</p>
                  <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--gray-300)' }}>Agrega al menos una área de aprobación</p>
                </div>
              )}

              {aprobadores.map((apr, idx) => (
                <div key={idx} style={{ background: 'var(--gray-50)', border: '1px solid var(--gray-200)', borderRadius: 10, padding: '12px 14px', marginBottom: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                    <div style={{ width: 22, height: 22, borderRadius: 6, background: 'var(--accent)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700, color: 'white', flexShrink: 0 }}>
                      {idx + 1}
                    </div>
                    <p style={{ margin: 0, fontSize: 12, fontWeight: 600, flex: 1 }}>Etapa {idx + 1}</p>
                    <button onClick={() => quitarAprobador(idx)}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--gray-400)', padding: 2, display: 'flex' }}>
                      <Trash2 size={14} />
                    </button>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                    <div>
                      <label style={{ display: 'block', fontSize: 11, fontWeight: 600, color: 'var(--gray-500)', marginBottom: 4 }}>Área / Departamento *</label>
                      <select style={{ ...inp, cursor: 'pointer' }}
                        value={apr.area_id}
                        onChange={e => updateAprobador(idx, 'area_id', e.target.value)}>
                        <option value="">Seleccionar área…</option>
                        {deptos.map(d => (
                          <option key={d.id} value={d.id}>{d.nombre}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label style={{ display: 'block', fontSize: 11, fontWeight: 600, color: 'var(--gray-500)', marginBottom: 4 }}>Email del aprobador *</label>
                      <input style={inp} type="email" placeholder="nombre@renaissance.cl"
                        value={apr.email} onChange={e => updateAprobador(idx, 'email', e.target.value)} />
                    </div>
                  </div>
                </div>
              ))}

              {/* Preview flujo */}
              {aprobadores.length > 1 && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginTop: 12, padding: '10px 14px', background: '#eff6ff', borderRadius: 8 }}>
                  <span style={{ fontSize: 11, color: 'var(--accent)', fontWeight: 600 }}>Flujo:</span>
                  {aprobadores.map((a, i) => (
                    <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span style={{ fontSize: 11, color: 'var(--gray-700)', background: 'white', padding: '2px 8px', borderRadius: 20, border: '1px solid #bfdbfe' }}>
                        {a.nombre || `Etapa ${i + 1}`}
                      </span>
                      {i < aprobadores.length - 1 && <ChevronRight size={12} color="var(--gray-400)" />}
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* Footer modal */}
            <div style={{ padding: '16px 24px', borderTop: '1px solid var(--gray-100)', display: 'flex', gap: 10, justifyContent: 'flex-end', flexShrink: 0, background: 'white' }}>
              <button onClick={resetForm}
                style={{ padding: '9px 18px', background: 'white', border: '1px solid var(--gray-200)', borderRadius: 8, fontSize: 13, cursor: 'pointer', fontFamily: 'Sora, sans-serif' }}>
                Cancelar
              </button>
              <button onClick={crear} disabled={!formValido || enviando}
                style={{ padding: '9px 20px', background: formValido ? 'var(--accent)' : 'var(--gray-200)', color: formValido ? 'white' : 'var(--gray-400)', border: 'none', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: formValido ? 'pointer' : 'default', fontFamily: 'Sora, sans-serif' }}>
                {enviando ? 'Iniciando flujo…' : `Iniciar flujo de aprobación (${aprobadores.length} etapa${aprobadores.length !== 1 ? 's' : ''}) →`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── MODAL DETALLE ── */}
      {detalle && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 50, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}
          onClick={() => setDetalle(null)}>
          <div style={{ background: 'white', borderRadius: 16, padding: 24, width: '100%', maxWidth: 520, maxHeight: '85vh', overflowY: 'auto' }}
            onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
              <h2 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>{detalle.cliente}</h2>
              <button onClick={() => setDetalle(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--gray-400)', padding: 0 }}><X size={18} /></button>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 16 }}>
              {[['ID', detalle.id], ['RUT', detalle.rut_cliente], ['Neto', fmtCLP(detalle.monto_neto)], ['Total', fmtCLP(detalle.total)], ['Concepto', detalle.concepto], ['Creada', fmtDate(detalle.timestamp)]].map(([k, v]) => (
                <div key={k} style={{ background: 'var(--gray-50)', padding: '8px 10px', borderRadius: 8 }}>
                  <p style={{ margin: 0, fontSize: 10, color: 'var(--gray-400)', fontWeight: 600, textTransform: 'uppercase' }}>{k}</p>
                  <p style={{ margin: '2px 0 0', fontSize: 12, fontWeight: 500, wordBreak: 'break-all' }}>{v}</p>
                </div>
              ))}
            </div>

            <p style={{ margin: '0 0 10px', fontSize: 12, fontWeight: 600, color: 'var(--gray-600)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Flujo de aprobación — {detalle.aprobadores.length} etapas
            </p>
            {detalle.aprobadores.sort((a, b) => a.orden - b.orden).map((apr, i) => {
              const estado = detalle.aprobaciones[apr.area_id]
              const color = estado === 'aprobado' ? 'var(--verde)' : estado === 'rechazado' ? 'var(--rojo)' : 'var(--gray-400)'
              const bg    = estado === 'aprobado' ? 'var(--verde-bg)' : estado === 'rechazado' ? 'var(--rojo-bg)' : 'var(--gray-100)'
              return (
                <div key={apr.area_id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: '1px solid var(--gray-100)' }}>
                  <div style={{ width: 20, height: 20, borderRadius: 6, background: 'var(--accent)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 700, color: 'white', flexShrink: 0 }}>{apr.orden}</div>
                  <div style={{ flex: 1 }}>
                    <p style={{ margin: 0, fontSize: 12, fontWeight: 500 }}>{apr.nombre}</p>
                    <p style={{ margin: 0, fontSize: 11, color: 'var(--gray-400)' }}>{apr.email}</p>
                  </div>
                  <span style={{ fontSize: 11, fontWeight: 600, color, background: bg, padding: '2px 8px', borderRadius: 20 }}>
                    {estado === 'aprobado' ? 'Aprobado ✓' : estado === 'rechazado' ? 'Rechazado ✗' : 'Pendiente'}
                  </span>
                </div>
              )
            })}

            <p style={{ margin: '16px 0 8px', fontSize: 12, fontWeight: 600, color: 'var(--gray-600)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Historial</p>
            {detalle.historial.map((h, i) => (
              <div key={i} style={{ display: 'flex', gap: 8, fontSize: 12, padding: '5px 0', borderBottom: '1px solid var(--gray-100)' }}>
                <span style={{ color: 'var(--gray-400)', whiteSpace: 'nowrap' }}>{fmtDate(h.ts)}</span>
                <span>{h.accion}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
