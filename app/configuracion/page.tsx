'use client'
import { useState, useEffect } from 'react'
import { Mail, MessageCircle, Save, CheckCircle, Bell, Shield, Users, Sliders, Eye, EyeOff, AlertCircle, Sparkles } from 'lucide-react'
import { getConfiguracion, saveConfiguracion, ConfigData } from '@/lib/api'

const DEFAULT: ConfigData = {
  email_remitente: '', email_password: '',
  email_aprobador: '', email_gerencia: '',
  whatsapp_activo: false, whatsapp_numero: '',
  umbral_verde: 1000000, umbral_rojo: 10000000,
  tolerancia: 15, dias_duplicados: 90,
  sla_24h: true, sla_48h: true, sla_72h: true, sla_96h: true,
  gemini_api_key: '',
}

function Toggle({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className={`toggle-track ${on ? 'on' : ''}`} onClick={() => onChange(!on)}>
      <div className="toggle-thumb" />
    </div>
  )
}

function Section({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div style={{ background: 'white', border: '1px solid var(--gray-200)', borderRadius: 16, padding: 24, marginBottom: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
        <div style={{ width: 32, height: 32, borderRadius: 8, background: '#eff6ff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{icon}</div>
        <h2 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>{title}</h2>
      </div>
      {children}
    </div>
  )
}

const inputStyle: React.CSSProperties = {
  width: '100%', padding: '9px 12px', borderRadius: 8,
  border: '1px solid var(--gray-200)', fontSize: 13,
  fontFamily: 'Sora, sans-serif', outline: 'none',
  background: 'white', color: 'var(--gray-900)',
}

function fmtM(n: number) {
  if (n >= 1000000) return `$${(n / 1000000).toFixed(n % 1000000 === 0 ? 0 : 1)}M`
  return `$${(n / 1000).toFixed(0)}K`
}

export default function Configuracion() {
  const [cfg, setCfg]         = useState<ConfigData>(DEFAULT)
  const [saved, setSaved]     = useState(false)
  const [saving, setSaving]   = useState(false)
  const [loading, setLoading] = useState(true)
  const [showPass, setShowPass] = useState(false)
  const [emailOk, setEmailOk] = useState(false)
  const [error, setError]     = useState<string | null>(null)
  const geminiSource = cfg.gemini_api_key_source ?? (cfg.gemini_api_key_set ? 'config' : 'none')
  const geminiActiva = geminiSource !== 'none'

  useEffect(() => {
    getConfiguracion()
      .then(data => {
        setCfg(prev => ({ ...prev, ...data, email_password: '', gemini_api_key: '' }))
        setEmailOk(!!data.email_password_set)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  const set = <K extends keyof ConfigData>(k: K, v: ConfigData[K]) =>
    setCfg(p => ({ ...p, [k]: v }))

  const guardar = async () => {
    setSaving(true); setError(null)
    try {
      const payload: Partial<ConfigData> = { ...cfg }
      if (!payload.email_password) delete payload.email_password
      if (!payload.gemini_api_key) delete payload.gemini_api_key
      const res = await saveConfiguracion(payload)
      setEmailOk(res.email_configurado)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch {
      setError('No se pudo conectar al backend. ¿Está corriendo motor.py?')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return (
    <div style={{ padding: '32px 36px' }}>
      <p style={{ color: 'var(--gray-400)', fontSize: 13 }}>Cargando configuración…</p>
    </div>
  )

  return (
    <div style={{ padding: '32px 36px', maxWidth: 800 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 28 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 600 }}>Configuración</h1>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--gray-400)' }}>Ajusta el sistema sin tocar código</p>
        </div>
        <button onClick={guardar} disabled={saving}
          style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 20px', background: saved ? 'var(--verde)' : 'var(--accent)', color: 'white', border: 'none', borderRadius: 10, fontSize: 13, fontWeight: 600, cursor: saving ? 'wait' : 'pointer', fontFamily: 'Sora, sans-serif', transition: 'background 0.2s', opacity: saving ? 0.7 : 1 }}>
          {saved ? <CheckCircle size={15} /> : <Save size={15} />}
          {saving ? 'Guardando…' : saved ? 'Guardado' : 'Guardar cambios'}
        </button>
      </div>

      {error && (
        <div style={{ marginBottom: 16, padding: '12px 16px', background: 'var(--rojo-bg)', border: '1px solid var(--rojo-bd)', borderRadius: 10, fontSize: 13, color: 'var(--rojo)', display: 'flex', gap: 8, alignItems: 'center' }}>
          <AlertCircle size={15} />{error}
        </div>
      )}

      {/* ── Email remitente ── */}
      <Section icon={<Mail size={16} color="var(--accent)" />} title="Cuenta de correo remitente">
        <div style={{ padding: '10px 14px', background: emailOk ? 'var(--verde-bg)' : 'var(--amarillo-bg)', border: `1px solid ${emailOk ? 'var(--verde-bd)' : 'var(--amarillo-bd)'}`, borderRadius: 8, marginBottom: 16, fontSize: 12, color: emailOk ? 'var(--verde)' : 'var(--amarillo)', display: 'flex', alignItems: 'center', gap: 6 }}>
          {emailOk ? <CheckCircle size={13} /> : <AlertCircle size={13} />}
          {emailOk ? 'Cuenta de envío configurada correctamente.' : 'Completa el email y contraseña para activar el envío de notificaciones.'}
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <div>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--gray-600)', marginBottom: 6 }}>Gmail remitente</label>
            <p style={{ margin: '0 0 8px', fontSize: 11, color: 'var(--gray-400)' }}>El email que envía las notificaciones automáticas</p>
            <input style={inputStyle} type="email" placeholder="sistema@hotel.cl"
              value={cfg.email_remitente} onChange={e => set('email_remitente', e.target.value)} />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--gray-600)', marginBottom: 6 }}>Contraseña de aplicación Gmail</label>
            <p style={{ margin: '0 0 8px', fontSize: 11, color: 'var(--gray-400)' }}>
              <a href="https://myaccount.google.com/apppasswords" target="_blank" style={{ color: 'var(--accent)', textDecoration: 'none' }}>Generar en Google Account →</a>
            </p>
            <div style={{ position: 'relative' }}>
              <input style={{ ...inputStyle, paddingRight: 36, fontFamily: showPass ? 'Sora, sans-serif' : 'monospace', letterSpacing: showPass ? 'normal' : '0.15em' }}
                type={showPass ? 'text' : 'password'}
                placeholder={emailOk ? '(contraseña guardada — deja vacío para no cambiarla)' : 'xxxx xxxx xxxx xxxx'}
                value={cfg.email_password}
                onChange={e => set('email_password', e.target.value)} />
              <button onClick={() => setShowPass(!showPass)} style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--gray-400)', padding: 0 }}>
                {showPass ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
          </div>
        </div>
      </Section>

      {/* ── Destinatarios ── */}
      <Section icon={<Users size={16} color="var(--accent)" />} title="Destinatarios de notificaciones">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <div>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--gray-600)', marginBottom: 6 }}>Email del aprobador</label>
            <p style={{ margin: '0 0 8px', fontSize: 11, color: 'var(--gray-400)' }}>Recibe alertas de Zona Amarilla con botones de acción directa</p>
            <input style={inputStyle} type="email" placeholder="jefe.finanzas@hotel.cl"
              value={cfg.email_aprobador} onChange={e => set('email_aprobador', e.target.value)} />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--gray-600)', marginBottom: 6 }}>Email de gerencia</label>
            <p style={{ margin: '0 0 8px', fontSize: 11, color: 'var(--gray-400)' }}>Recibe alertas Zona Roja + copia de alertas + resumen diario</p>
            <input style={inputStyle} type="email" placeholder="gerente@hotel.cl"
              value={cfg.email_gerencia} onChange={e => set('email_gerencia', e.target.value)} />
          </div>
        </div>
      </Section>

      {/* ── WhatsApp ── */}
      <Section icon={<MessageCircle size={16} color="var(--accent)" />} title="WhatsApp Business (opcional)">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: cfg.whatsapp_activo ? 16 : 0, padding: '12px 14px', background: cfg.whatsapp_activo ? 'var(--verde-bg)' : 'var(--gray-50)', borderRadius: 8, border: `1px solid ${cfg.whatsapp_activo ? 'var(--verde-bd)' : 'var(--gray-200)'}`, transition: 'all 0.2s' }}>
          <div>
            <p style={{ margin: 0, fontSize: 13, fontWeight: 500 }}>Activar notificaciones por WhatsApp</p>
            <p style={{ margin: 0, fontSize: 12, color: 'var(--gray-400)' }}>Requiere cuenta WhatsApp Business API (Twilio o Meta)</p>
          </div>
          <Toggle on={cfg.whatsapp_activo} onChange={v => set('whatsapp_activo', v)} />
        </div>
        {cfg.whatsapp_activo && (
          <div>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--gray-600)', marginBottom: 6 }}>Número de WhatsApp</label>
            <input style={inputStyle} type="tel" placeholder="+56 9 1234 5678"
              value={cfg.whatsapp_numero} onChange={e => set('whatsapp_numero', e.target.value)} />
          </div>
        )}
      </Section>

      {/* ── Umbrales ── */}
      <Section icon={<Sliders size={16} color="var(--accent)" />} title="Umbrales de clasificación">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 16 }}>
          <div>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--gray-600)', marginBottom: 6 }}>
              Zona Verde — hasta {fmtM(cfg.umbral_verde)} CLP
            </label>
            <p style={{ margin: '0 0 8px', fontSize: 11, color: 'var(--gray-400)' }}>Aprobación automática sin intervención</p>
            <input type="range" min={100000} max={5000000} step={50000} value={cfg.umbral_verde}
              onChange={e => set('umbral_verde', +e.target.value)} style={{ width: '100%', accentColor: 'var(--verde)' }} />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--gray-600)', marginBottom: 6 }}>
              Zona Roja — desde {fmtM(cfg.umbral_rojo)} CLP
            </label>
            <p style={{ margin: '0 0 8px', fontSize: 11, color: 'var(--gray-400)' }}>Bloqueo automático y escalada a gerencia</p>
            <input type="range" min={5000000} max={50000000} step={500000} value={cfg.umbral_rojo}
              onChange={e => set('umbral_rojo', +e.target.value)} style={{ width: '100%', accentColor: 'var(--rojo)' }} />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--gray-600)', marginBottom: 6 }}>
              Tolerancia sobre histórico: ±{cfg.tolerancia}%
            </label>
            <p style={{ margin: '0 0 8px', fontSize: 11, color: 'var(--gray-400)' }}>Variación antes de pasar a Zona Amarilla</p>
            <input type="range" min={5} max={50} step={1} value={cfg.tolerancia}
              onChange={e => set('tolerancia', +e.target.value)} style={{ width: '100%', accentColor: 'var(--amarillo)' }} />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--gray-600)', marginBottom: 6 }}>
              Ventana duplicados: {cfg.dias_duplicados} días
            </label>
            <p style={{ margin: '0 0 8px', fontSize: 11, color: 'var(--gray-400)' }}>Periodo para detectar facturas duplicadas</p>
            <input type="range" min={30} max={180} step={10} value={cfg.dias_duplicados}
              onChange={e => set('dias_duplicados', +e.target.value)} style={{ width: '100%', accentColor: 'var(--accent)' }} />
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          {[
            { label: 'Verde', sub: `hasta ${fmtM(cfg.umbral_verde)}`, cl: 'verde' },
            { label: 'Amarilla', sub: `${fmtM(cfg.umbral_verde)} – ${fmtM(cfg.umbral_rojo)}`, cl: 'amarilla' },
            { label: 'Roja', sub: `desde ${fmtM(cfg.umbral_rojo)}`, cl: 'roja' },
          ].map(z => (
            <div key={z.cl} style={{ flex: 1, background: `var(--${z.cl}-bg)`, border: `1px solid var(--${z.cl}-bd)`, borderRadius: 8, padding: '8px 12px' }}>
              <p style={{ margin: 0, fontSize: 11, fontWeight: 600, color: `var(--${z.cl})` }}>{z.label}</p>
              <p style={{ margin: 0, fontSize: 11, color: `var(--${z.cl})` }}>{z.sub}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* ── IA / Gemini ── */}
      <Section icon={<Sparkles size={16} color="var(--accent)" />} title="Inteligencia Artificial — Gemini">
        <div style={{ padding: '10px 14px', background: geminiActiva ? 'var(--verde-bg)' : 'var(--amarillo-bg)', border: `1px solid ${geminiActiva ? 'var(--verde-bd)' : 'var(--amarillo-bd)'}`, borderRadius: 8, marginBottom: 14, fontSize: 12, color: geminiActiva ? 'var(--verde)' : 'var(--amarillo)', display: 'flex', alignItems: 'center', gap: 6 }}>
          {geminiActiva ? <CheckCircle size={13} /> : <AlertCircle size={13} />}
          {geminiActiva
            ? (geminiSource === 'env'
              ? 'IA activa — usando GEMINI_API_KEY desde el entorno. La clave no se guarda en config.json.'
              : 'IA activa — Análisis automático, resumen ejecutivo y chat habilitados.')
            : 'Sin API key — la IA no está activa. Obtén una gratis en aistudio.google.com.'}
        </div>
        <div>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--gray-600)', marginBottom: 6 }}>API Key de Gemini</label>
          <p style={{ margin: '0 0 8px', fontSize: 11, color: 'var(--gray-400)' }}>
            Gratis en <a href="https://aistudio.google.com" target="_blank" style={{ color: 'var(--accent)', textDecoration: 'none' }}>aistudio.google.com</a> → "Get API key" → copia y pega aquí para uso local.
          </p>
          <input style={inputStyle} type="password" placeholder="AIzaSy..."
            value={cfg.gemini_api_key || ''} onChange={e => set('gemini_api_key', e.target.value)} disabled={geminiSource === 'env'} />
          {geminiSource === 'env' && (
            <p style={{ margin: '8px 0 0', fontSize: 11, color: 'var(--gray-400)' }}>
              La clave se toma desde el entorno del backend. Este campo queda deshabilitado para evitar sobrescribirla desde la UI.
            </p>
          )}
        </div>
        <div style={{ marginTop: 12, display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
          {[
            { t: 'Análisis de facturas', d: 'Explica por qué una factura es sospechosa en lenguaje natural' },
            { t: 'Resumen ejecutivo', d: 'Resume cada factura para el equipo directivo automáticamente' },
            { t: 'Chat con documentos', d: 'Consulta el historial financiero en lenguaje natural' },
          ].map(f => (
            <div key={f.t} style={{ background: 'var(--gray-50)', border: '1px solid var(--gray-200)', borderRadius: 8, padding: '8px 10px' }}>
              <p style={{ margin: '0 0 3px', fontSize: 11, fontWeight: 600 }}>{f.t}</p>
              <p style={{ margin: 0, fontSize: 10, color: 'var(--gray-400)' }}>{f.d}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* ── SLA ── */}
      <Section icon={<Bell size={16} color="var(--accent)" />} title="Escalamiento automático por tiempo (SLA)">
        {([
          { key: 'sla_24h', label: 'Primer recordatorio',  sub: 'Si el aprobador no responde en 24h' },
          { key: 'sla_48h', label: 'Segundo aviso',         sub: 'Alerta de vencimiento de SLA a las 48h' },
          { key: 'sla_72h', label: 'Escala al superior',    sub: 'Deriva al jerárquico a las 72h' },
          { key: 'sla_96h', label: 'Bloqueo crítico',       sub: 'Alerta crítica a dirección a las 96h' },
        ] as const).map(s => (
          <div key={s.key} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '11px 0', borderBottom: '1px solid var(--gray-100)' }}>
            <div>
              <p style={{ margin: 0, fontSize: 13, fontWeight: 500 }}>{s.label}</p>
              <p style={{ margin: 0, fontSize: 12, color: 'var(--gray-400)' }}>{s.sub}</p>
            </div>
            <Toggle on={cfg[s.key]} onChange={v => set(s.key, v)} />
          </div>
        ))}
      </Section>

      {/* ── Proveedores ── */}
      <Section icon={<Shield size={16} color="var(--accent)" />} title="Lista blanca de proveedores">
        <p style={{ margin: '0 0 14px', fontSize: 12, color: 'var(--gray-400)' }}>Solo se aprueban automáticamente facturas de proveedores activos en esta lista.</p>
        {[
          { rut: '12.456.789-5', nombre: 'Distribuidora López e Hijos Ltda.', media: 650000 },
          { rut: '76.321.654-K', nombre: 'Sistemas Técnicos SA',              media: 1060000 },
          { rut: '9.876.543-2',  nombre: 'Lavandería Industrial Norte Ltda.', media: 280000 },
          { rut: '15.432.100-8', nombre: 'Suministros Gastronómicos SPA',     media: 420000 },
        ].map((p, i) => (
          <div key={p.rut} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '11px 0', borderBottom: '1px solid var(--gray-100)' }}>
            <div style={{ flex: 1 }}>
              <p style={{ margin: 0, fontSize: 13, fontWeight: 500 }}>{p.nombre}</p>
              <p style={{ margin: 0, fontSize: 12, color: 'var(--gray-400)', fontFamily: 'IBM Plex Mono, monospace' }}>
                {p.rut} · Media: ${p.media.toLocaleString('es-CL')} CLP
              </p>
            </div>
            <Shield size={13} color="var(--verde)" />
          </div>
        ))}
      </Section>
    </div>
  )
}
