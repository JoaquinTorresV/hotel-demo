'use client'
import { useState, useEffect } from 'react'
import { Send, CheckCircle, XCircle, Clock, AlertCircle, Plus, ChevronRight } from 'lucide-react'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface FacturaEmitida {
  id: string
  cliente: string
  rut_cliente: string
  concepto: string
  monto_neto: number
  iva: number
  total: number
  estado: 'pendiente' | 'en_proceso' | 'aprobada' | 'rechazada'
  aprobaciones: Record<string, string>
  areas_requeridas: string[]
  area_pendiente: string | null
  progreso: number
  total_etapas: number
  requiere_gerencia: boolean
  timestamp: string
  historial: { accion: string; ts: string }[]
}

const AREAS = [
  { id: 'rrhh',      label: 'Recursos Humanos', desc: 'Confirma asignación de personal' },
  { id: 'marketing', label: 'Marketing',          desc: 'Valida contrato y datos del cliente' },
  { id: 'gerencia',  label: 'Gerencia General',   desc: 'Aprobación final (solo >$5M)' },
]

const ESTADO_CONFIG: Record<string, { label: string; color: string; bg: string; icon: React.ReactNode }> = {
  pendiente:   { label: 'Pendiente',   color: 'var(--gray-600)',  bg: 'var(--gray-100)', icon: <Clock size={12} /> },
  en_proceso:  { label: 'En proceso',  color: 'var(--amarillo)',  bg: 'var(--amarillo-bg)', icon: <AlertCircle size={12} /> },
  aprobada:    { label: 'Aprobada',    color: 'var(--verde)',     bg: 'var(--verde-bg)',    icon: <CheckCircle size={12} /> },
  rechazada:   { label: 'Rechazada',   color: 'var(--rojo)',      bg: 'var(--rojo-bg)',     icon: <XCircle size={12} /> },
}

function fmtCLP(n: number) {
  return `$ ${n.toLocaleString('es-CL')} CLP`
}
function fmtDate(ts: string) {
  return new Date(ts).toLocaleString('es-CL', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

const inputStyle: React.CSSProperties = {
  width: '100%', padding: '9px 12px', borderRadius: 8,
  border: '1px solid var(--gray-200)', fontSize: 13,
  fontFamily: 'Sora, sans-serif', outline: 'none',
  background: 'white', color: 'var(--gray-900)',
}

export default function Emision() {
  const [facturas, setFacturas]       = useState<FacturaEmitida[]>([])
  const [loading, setLoading]         = useState(true)
  const [showForm, setShowForm]       = useState(false)
  const [enviando, setEnviando]       = useState(false)
  const [detalle, setDetalle]         = useState<FacturaEmitida | null>(null)
  const [form, setForm] = useState({
    cliente: '', rut_cliente: '', concepto: '',
    monto_neto: '', descripcion: '',
    email_rrhh: '', email_marketing: '', email_gerencia_aprobador: '',
  })

  const cargar = () => {
    setLoading(true)
    fetch(`${API}/emision/listar`)
      .then(r => r.json())
      .then(d => { setFacturas(d.facturas || []); setLoading(false) })
      .catch(() => setLoading(false))
  }

  useEffect(() => { cargar() }, [])

  const setF = (k: string, v: string) => setForm(p => ({ ...p, [k]: v }))

  const crear = async () => {
    if (!form.cliente || !form.rut_cliente || !form.concepto || !form.monto_neto) return
    setEnviando(true)
    try {
      const res = await fetch(`${API}/emision/crear`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, monto_neto: parseInt(form.monto_neto.replace(/\D/g, '')) }),
      })
      if (res.ok) {
        setShowForm(false)
        setForm({ cliente: '', rut_cliente: '', concepto: '', monto_neto: '', descripcion: '', email_rrhh: '', email_marketing: '', email_gerencia_aprobador: '' })
        cargar()
      }
    } finally { setEnviando(false) }
  }

  const montoNum = parseInt(form.monto_neto.replace(/\D/g, '') || '0')
  const ivaCalc  = Math.round(montoNum * 0.19)
  const totalCalc = montoNum + ivaCalc

  return (
    <div style={{ padding: '32px 36px', maxWidth: 1100 }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 20 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
            <div style={{ background: '#dbeafe', padding: '4px 10px', borderRadius: 20, fontSize: 11, fontWeight: 600, color: 'var(--accent)' }}>
              Flujo 2 — Facturas que el hotel emite
            </div>
          </div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 600 }}>Emisión y aprobación interna</h1>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--gray-400)' }}>
            Facturas que Renaissance emite a clientes · Requieren aprobación de RRHH → Marketing → Gerencia
          </p>
        </div>
        <button
          onClick={() => setShowForm(true)}
          style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 18px', background: 'var(--accent)', color: 'white', border: 'none', borderRadius: 10, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'Sora, sans-serif' }}>
          <Plus size={15} /> Nueva factura
        </button>
      </div>

      {/* Aviso separación flujos */}
      <div style={{ background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 10, padding: '10px 16px', marginBottom: 20, fontSize: 12, color: '#1d4ed8', display: 'flex', gap: 8, alignItems: 'flex-start' }}>
        <AlertCircle size={14} style={{ flexShrink: 0, marginTop: 1 }} />
        <span>Este módulo es independiente del sistema de facturas recibidas. Aquí gestionas las facturas que <strong>Renaissance le cobra a sus clientes</strong> — eventos, conferencias, servicios corporativos — antes de emitirlas oficialmente.</span>
      </div>

      {/* Flujo visual */}
      <div style={{ background: 'white', border: '1px solid var(--gray-200)', borderRadius: 16, padding: '16px 20px', marginBottom: 20 }}>
        <p style={{ margin: '0 0 12px', fontSize: 12, fontWeight: 600, color: 'var(--gray-600)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          Flujo de aprobación — 3 etapas
        </p>
        <div style={{ display: 'flex', alignItems: 'center', gap: 0, flexWrap: "wrap" }}>
          {AREAS.map((a, i) => (
            <div key={a.id} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{ background: i === 2 ? 'var(--amarillo-bg)' : 'var(--gray-100)', border: `1px solid ${i === 2 ? 'var(--amarillo-bd)' : 'var(--gray-200)'}`, borderRadius: 8, padding: '8px 14px' }}>
                <p style={{ margin: 0, fontSize: 12, fontWeight: 600, color: i === 2 ? 'var(--amarillo)' : 'var(--gray-900)' }}>{a.label}</p>
                <p style={{ margin: 0, fontSize: 11, color: 'var(--gray-400)' }}>{a.desc}</p>
                {i === 2 && <p style={{ margin: '3px 0 0', fontSize: 10, color: 'var(--amarillo)', fontStyle: 'italic' }}>Solo si monto {">"} $5M</p>}
              </div>
              {i < 2 && <ChevronRight size={14} color="var(--gray-400)" />}
            </div>
          ))}
          <ChevronRight size={14} color="var(--gray-400)" />
          <div style={{ background: 'var(--verde-bg)', border: '1px solid var(--verde-bd)', borderRadius: 8, padding: '8px 14px' }}>
            <p style={{ margin: 0, fontSize: 12, fontWeight: 600, color: 'var(--verde)' }}>Lista para emitir</p>
            <p style={{ margin: 0, fontSize: 11, color: 'var(--gray-400)' }}>Factura oficial al SII</p>
          </div>
        </div>
      </div>

      {/* Lista facturas */}
      <div style={{ background: 'white', border: '1px solid var(--gray-200)', borderRadius: 16, overflow: 'hidden' }}>
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--gray-400)', fontSize: 13 }}>Cargando…</div>
        ) : facturas.length === 0 ? (
          <div style={{ padding: 60, textAlign: 'center' }}>
            <Send size={32} style={{ color: 'var(--gray-200)', margin: '0 auto 12px', display: 'block' }} />
            <p style={{ margin: 0, fontSize: 13, color: 'var(--gray-400)' }}>No hay facturas en proceso.</p>
            <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--gray-400)' }}>Crea la primera con el botón "Nueva factura".</p>
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--gray-100)', background: 'var(--gray-50)' }}>
                {['Estado', 'Cliente', 'Concepto', 'Total', 'Progreso aprobación', 'Área pendiente', 'Creada'].map(h => (
                  <th key={h} style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: 'var(--gray-400)', textTransform: 'uppercase', letterSpacing: '0.05em', whiteSpace: 'nowrap' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {facturas.map((f, i) => {
                const est = ESTADO_CONFIG[f.estado] || ESTADO_CONFIG.pendiente
                return (
                  <tr
                    key={f.id}
                    onClick={() => setDetalle(f)}
                    style={{ borderBottom: '1px solid var(--gray-100)', background: i % 2 === 0 ? 'white' : 'var(--gray-50)', cursor: 'pointer', transition: 'background 0.1s' }}
                    onMouseEnter={e => (e.currentTarget.style.background = '#f0f7ff')}
                    onMouseLeave={e => (e.currentTarget.style.background = i % 2 === 0 ? 'white' : 'var(--gray-50)')}
                  >
                    <td style={{ padding: '12px 16px' }}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, background: est.bg, color: est.color, padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 600 }}>
                        {est.icon}{est.label}
                      </span>
                    </td>
                    <td style={{ padding: '12px 16px', fontWeight: 500 }}>{f.cliente}</td>
                    <td style={{ padding: '12px 16px', color: 'var(--gray-600)', maxWidth: 200 }}>
                      <span style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.concepto}</span>
                    </td>
                    <td style={{ padding: '12px 16px', fontFamily: 'IBM Plex Mono, monospace', fontWeight: 600, color: 'var(--accent)', whiteSpace: 'nowrap' }}>
                      {fmtCLP(f.total)}
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div style={{ flex: 1, height: 6, background: 'var(--gray-100)', borderRadius: 3, overflow: 'hidden', minWidth: 80 }}>
                          <div style={{ height: '100%', width: `${f.total_etapas > 0 ? (f.progreso / f.total_etapas) * 100 : 0}%`, background: f.estado === 'aprobada' ? 'var(--verde)' : f.estado === 'rechazada' ? 'var(--rojo)' : 'var(--accent)', borderRadius: 3, transition: 'width 0.3s' }} />
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

      {/* MODAL: Nueva factura */}
      {showForm && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 50, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
          <div style={{ background: 'white', borderRadius: 16, padding: 28, width: '100%', maxWidth: 560, maxHeight: '90vh', overflowY: 'auto' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
              <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>Nueva factura a emitir</h2>
              <button onClick={() => setShowForm(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--gray-400)', fontSize: 20, padding: 0, lineHeight: 1 }}>×</button>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 14 }}>
              <div style={{ gridColumn: '1/-1' }}>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--gray-600)', marginBottom: 6 }}>Nombre del cliente *</label>
                <input style={inputStyle} placeholder="Ej: Banco Santander Chile" value={form.cliente} onChange={e => setF('cliente', e.target.value)} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--gray-600)', marginBottom: 6 }}>RUT del cliente *</label>
                <input style={inputStyle} placeholder="Ej: 97.036.000-K" value={form.rut_cliente} onChange={e => setF('rut_cliente', e.target.value)} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--gray-600)', marginBottom: 6 }}>Monto neto (CLP) *</label>
                <input style={inputStyle} placeholder="Ej: 4500000" value={form.monto_neto} onChange={e => setF('monto_neto', e.target.value)} />
              </div>
              <div style={{ gridColumn: '1/-1' }}>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--gray-600)', marginBottom: 6 }}>Concepto / Servicio *</label>
                <input style={inputStyle} placeholder="Ej: Evento corporativo — Salón Gran Santiago, 15/02/2025" value={form.concepto} onChange={e => setF('concepto', e.target.value)} />
              </div>
              <div style={{ gridColumn: '1/-1' }}>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--gray-600)', marginBottom: 6 }}>Descripción adicional</label>
                <input style={inputStyle} placeholder="Detalles del servicio prestado..." value={form.descripcion} onChange={e => setF('descripcion', e.target.value)} />
              </div>
            </div>

            {/* Preview montos */}
            {montoNum > 0 && (
              <div style={{ background: 'var(--gray-50)', border: '1px solid var(--gray-200)', borderRadius: 8, padding: '10px 14px', marginBottom: 14 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
                  <span style={{ color: 'var(--gray-600)' }}>Neto</span>
                  <span style={{ fontFamily: 'IBM Plex Mono, monospace' }}>{fmtCLP(montoNum)}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 6 }}>
                  <span style={{ color: 'var(--gray-600)' }}>IVA 19%</span>
                  <span style={{ fontFamily: 'IBM Plex Mono, monospace' }}>{fmtCLP(ivaCalc)}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, fontWeight: 600, borderTop: '1px solid var(--gray-200)', paddingTop: 6 }}>
                  <span>Total a cobrar</span>
                  <span style={{ fontFamily: 'IBM Plex Mono, monospace', color: 'var(--accent)' }}>{fmtCLP(totalCalc)}</span>
                </div>
                {montoNum > 5_000_000 && (
                  <p style={{ margin: '8px 0 0', fontSize: 11, color: 'var(--amarillo)' }}>
                    Monto mayor a $5M — se requerirá aprobación de Gerencia General (3 etapas)
                  </p>
                )}
                {montoNum <= 5_000_000 && montoNum > 0 && (
                  <p style={{ margin: '8px 0 0', fontSize: 11, color: 'var(--verde)' }}>
                    Monto menor a $5M — solo RRHH y Marketing (2 etapas)
                  </p>
                )}
              </div>
            )}

            {/* Emails aprobadores */}
            <div style={{ marginBottom: 14 }}>
              <p style={{ margin: '0 0 10px', fontSize: 12, fontWeight: 600, color: 'var(--gray-600)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Emails de aprobadores (opcional — usa los de configuración si está vacío)
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {[
                  { key: 'email_rrhh', label: 'Email RRHH' },
                  { key: 'email_marketing', label: 'Email Marketing' },
                  ...(montoNum > 5_000_000 ? [{ key: 'email_gerencia_aprobador', label: 'Email Gerencia' }] : []),
                ].map(({ key, label }) => (
                  <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <label style={{ fontSize: 12, color: 'var(--gray-600)', width: 120, flexShrink: 0 }}>{label}</label>
                    <input style={{ ...inputStyle, flex: 1 }} type="email" placeholder="email@renaissance.cl"
                      value={(form as any)[key]} onChange={e => setF(key, e.target.value)} />
                  </div>
                ))}
              </div>
            </div>

            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button onClick={() => setShowForm(false)} style={{ padding: '9px 18px', background: 'white', border: '1px solid var(--gray-200)', borderRadius: 8, fontSize: 13, cursor: 'pointer', fontFamily: 'Sora, sans-serif' }}>
                Cancelar
              </button>
              <button onClick={crear} disabled={enviando || !form.cliente || !form.concepto || !form.monto_neto}
                style={{ padding: '9px 20px', background: 'var(--accent)', color: 'white', border: 'none', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'Sora, sans-serif', opacity: (enviando || !form.cliente || !form.concepto || !form.monto_neto) ? 0.6 : 1 }}>
                {enviando ? 'Enviando…' : 'Iniciar flujo de aprobación →'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL: Detalle factura */}
      {detalle && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 50, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}
          onClick={() => setDetalle(null)}>
          <div style={{ background: 'white', borderRadius: 16, padding: 28, width: '100%', maxWidth: 500, maxHeight: '85vh', overflowY: 'auto' }}
            onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 18 }}>
              <h2 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>{detalle.cliente}</h2>
              <button onClick={() => setDetalle(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--gray-400)', fontSize: 20, padding: 0, lineHeight: 1 }}>×</button>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 16 }}>
              {[
                ['ID', detalle.id],
                ['RUT cliente', detalle.rut_cliente],
                ['Neto', fmtCLP(detalle.monto_neto)],
                ['Total', fmtCLP(detalle.total)],
                ['Concepto', detalle.concepto],
                ['Creada', fmtDate(detalle.timestamp)],
              ].map(([k, v]) => (
                <div key={k} style={{ background: 'var(--gray-50)', padding: '8px 10px', borderRadius: 8 }}>
                  <p style={{ margin: 0, fontSize: 10, color: 'var(--gray-400)', fontWeight: 600, textTransform: 'uppercase' }}>{k}</p>
                  <p style={{ margin: '2px 0 0', fontSize: 12, fontWeight: 500 }}>{v}</p>
                </div>
              ))}
            </div>

            <p style={{ margin: '0 0 10px', fontSize: 12, fontWeight: 600, color: 'var(--gray-600)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Estado por área</p>
            {AREAS.map(area => {
              const requerida = detalle.areas_requeridas.includes(area.id)
              const estado = detalle.aprobaciones[area.id]
              const color = estado === 'aprobado' ? 'var(--verde)' : estado === 'rechazado' ? 'var(--rojo)' : 'var(--gray-400)'
              const bg    = estado === 'aprobado' ? 'var(--verde-bg)' : estado === 'rechazado' ? 'var(--rojo-bg)' : 'var(--gray-100)'
              return (
                <div key={area.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: '1px solid var(--gray-100)', opacity: requerida ? 1 : 0.4 }}>
                  <div style={{ width: 8, height: 8, borderRadius: '50%', background: color, flexShrink: 0 }} />
                  <div style={{ flex: 1 }}>
                    <p style={{ margin: 0, fontSize: 12, fontWeight: 500 }}>{area.label}</p>
                    <p style={{ margin: 0, fontSize: 11, color: 'var(--gray-400)' }}>{requerida ? area.desc : 'No requerida para este monto'}</p>
                  </div>
                  <span style={{ fontSize: 11, fontWeight: 600, color, background: bg, padding: '2px 8px', borderRadius: 20 }}>
                    {!requerida ? 'N/A' : estado === 'aprobado' ? 'Aprobado ✓' : estado === 'rechazado' ? 'Rechazado ✗' : 'Pendiente'}
                  </span>
                </div>
              )
            })}

            <p style={{ margin: '16px 0 8px', fontSize: 12, fontWeight: 600, color: 'var(--gray-600)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Historial</p>
            {detalle.historial.map((h, i) => (
              <div key={i} style={{ display: 'flex', gap: 8, fontSize: 12, padding: '5px 0', borderBottom: '1px solid var(--gray-100)' }}>
                <span style={{ color: 'var(--gray-400)', whiteSpace: 'nowrap' }}>{fmtDate(h.ts)}</span>
                <span style={{ color: 'var(--gray-700)' }}>{h.accion}</span>
              </div>
            ))}
          </div>
        </div>
      )}

    </div>
  )
}
