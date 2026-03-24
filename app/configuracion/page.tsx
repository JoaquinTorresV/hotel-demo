'use client'
import { useState } from 'react'
import { Mail, MessageCircle, Save, CheckCircle, Bell, Shield, Users, Sliders } from 'lucide-react'

interface Config {
  email_aprobador: string
  email_gerencia: string
  whatsapp_activo: boolean
  whatsapp_numero: string
  umbral_verde: number
  umbral_rojo: number
  tolerancia_historico: number
  dias_duplicados: number
  sla_24h: boolean
  sla_48h: boolean
  sla_72h: boolean
  sla_96h: boolean
  proveedores: { rut: string; nombre: string; activo: boolean; media: number }[]
}

const DEFAULT: Config = {
  email_aprobador:      '',
  email_gerencia:       '',
  whatsapp_activo:      false,
  whatsapp_numero:      '',
  umbral_verde:         1000000,
  umbral_rojo:          10000000,
  tolerancia_historico: 15,
  dias_duplicados:      90,
  sla_24h: true, sla_48h: true, sla_72h: true, sla_96h: true,
  proveedores: [
    { rut: '12.456.789-5', nombre: 'Distribuidora López e Hijos Ltda.', activo: true, media: 650000 },
    { rut: '76.321.654-K', nombre: 'Sistemas Técnicos SA',              activo: true, media: 1060000 },
    { rut: '9.876.543-2',  nombre: 'Lavandería Industrial Norte Ltda.', activo: true, media: 280000 },
    { rut: '15.432.100-8', nombre: 'Suministros Gastronómicos SPA',     activo: true, media: 420000 },
  ],
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
        <div style={{ width: 32, height: 32, borderRadius: 8, background: '#eff6ff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          {icon}
        </div>
        <h2 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>{title}</h2>
      </div>
      {children}
    </div>
  )
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--gray-600)', marginBottom: 6 }}>{label}</label>
      {hint && <p style={{ margin: '0 0 8px', fontSize: 11, color: 'var(--gray-400)' }}>{hint}</p>}
      {children}
    </div>
  )
}

const inputStyle = {
  width: '100%', padding: '9px 12px', borderRadius: 8,
  border: '1px solid var(--gray-200)', fontSize: 13,
  fontFamily: 'Sora, sans-serif', outline: 'none',
  background: 'white', color: 'var(--gray-900)',
}

function formatM(n: number) {
  if (n >= 1000000) return `$${(n/1000000).toFixed(n%1000000===0?0:1)}M`
  if (n >= 1000)    return `$${(n/1000).toFixed(0)}K`
  return `$${n}`
}

export default function Configuracion() {
  const [cfg, setCfg] = useState<Config>(DEFAULT)
  const [saved, setSaved] = useState(false)

  const set = <K extends keyof Config>(k: K, v: Config[K]) => setCfg(p => ({ ...p, [k]: v }))

  const guardar = () => {
    // Aquí iría el POST a la API — por ahora simulamos
    setSaved(true)
    setTimeout(() => setSaved(false), 3000)
  }

  const toggleProveedor = (i: number) => {
    const provs = [...cfg.proveedores]
    provs[i] = { ...provs[i], activo: !provs[i].activo }
    set('proveedores', provs)
  }

  return (
    <div style={{ padding: '32px 36px', maxWidth: 800 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 28 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 600 }}>Configuración</h1>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--gray-400)' }}>
            Ajusta el sistema sin tocar código
          </p>
        </div>
        <button
          onClick={guardar}
          style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 20px', background: saved ? 'var(--verde)' : 'var(--accent)', color: 'white', border: 'none', borderRadius: 10, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'Sora, sans-serif', transition: 'background 0.2s' }}
        >
          {saved ? <CheckCircle size={15} /> : <Save size={15} />}
          {saved ? 'Guardado' : 'Guardar cambios'}
        </button>
      </div>

      {/* ── Notificaciones Email ── */}
      <Section icon={<Mail size={16} color="var(--accent)" />} title="Notificaciones por email">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <Field label="Email del aprobador" hint="Recibe alertas de Zona Amarilla con botones de acción">
            <input style={inputStyle} type="email" placeholder="jefe.finanzas@hotel.cl"
              value={cfg.email_aprobador} onChange={e => set('email_aprobador', e.target.value)} />
          </Field>
          <Field label="Email de gerencia" hint="Recibe alertas de Zona Roja y resumen diario">
            <input style={inputStyle} type="email" placeholder="gerente@hotel.cl"
              value={cfg.email_gerencia} onChange={e => set('email_gerencia', e.target.value)} />
          </Field>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 14px', background: 'var(--gray-50)', borderRadius: 8, border: '1px solid var(--gray-200)' }}>
          <div>
            <p style={{ margin: 0, fontSize: 13, fontWeight: 500 }}>Resumen diario automático</p>
            <p style={{ margin: 0, fontSize: 12, color: 'var(--gray-400)' }}>Email con todas las facturas Zona Verde procesadas ese día</p>
          </div>
          <Toggle on={true} onChange={() => {}} />
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
          <Field label="Número de WhatsApp" hint="Formato internacional: +56 9 XXXX XXXX">
            <input style={inputStyle} type="tel" placeholder="+56 9 1234 5678"
              value={cfg.whatsapp_numero} onChange={e => set('whatsapp_numero', e.target.value)} />
          </Field>
        )}
      </Section>

      {/* ── Umbrales ── */}
      <Section icon={<Sliders size={16} color="var(--accent)" />} title="Umbrales de clasificación">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 16 }}>
          <Field label={`Umbral Zona Verde — máximo: ${formatM(cfg.umbral_verde)} CLP`} hint="Facturas bajo este monto se aprueban automáticamente">
            <input type="range" min={100000} max={5000000} step={50000}
              value={cfg.umbral_verde} onChange={e => set('umbral_verde', +e.target.value)}
              style={{ width: '100%', accentColor: 'var(--verde)' }} />
          </Field>
          <Field label={`Umbral Zona Roja — desde: ${formatM(cfg.umbral_rojo)} CLP`} hint="Facturas sobre este monto se bloquean automáticamente">
            <input type="range" min={5000000} max={50000000} step={500000}
              value={cfg.umbral_rojo} onChange={e => set('umbral_rojo', +e.target.value)}
              style={{ width: '100%', accentColor: 'var(--rojo)' }} />
          </Field>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
          <Field label={`Tolerancia sobre histórico: ±${cfg.tolerancia_historico}%`} hint="Variación permitida antes de enviar a Zona Amarilla">
            <input type="range" min={5} max={50} step={1}
              value={cfg.tolerancia_historico} onChange={e => set('tolerancia_historico', +e.target.value)}
              style={{ width: '100%', accentColor: 'var(--amarillo)' }} />
          </Field>
          <Field label={`Ventana duplicados: ${cfg.dias_duplicados} días`} hint="Periodo para detectar facturas duplicadas del mismo proveedor">
            <input type="range" min={30} max={180} step={10}
              value={cfg.dias_duplicados} onChange={e => set('dias_duplicados', +e.target.value)}
              style={{ width: '100%', accentColor: 'var(--accent)' }} />
          </Field>
        </div>

        {/* Resumen visual de zonas */}
        <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
          <div style={{ flex: cfg.umbral_verde, background: 'var(--verde-bg)', border: '1px solid var(--verde-bd)', borderRadius: 8, padding: '8px 12px', minWidth: 0 }}>
            <p style={{ margin: 0, fontSize: 11, fontWeight: 600, color: 'var(--verde)' }}>Verde</p>
            <p style={{ margin: 0, fontSize: 11, color: 'var(--verde)' }}>hasta {formatM(cfg.umbral_verde)}</p>
          </div>
          <div style={{ flex: cfg.umbral_rojo - cfg.umbral_verde, background: 'var(--amarillo-bg)', border: '1px solid var(--amarillo-bd)', borderRadius: 8, padding: '8px 12px', minWidth: 0 }}>
            <p style={{ margin: 0, fontSize: 11, fontWeight: 600, color: 'var(--amarillo)' }}>Amarilla</p>
            <p style={{ margin: 0, fontSize: 11, color: 'var(--amarillo)' }}>{formatM(cfg.umbral_verde)} – {formatM(cfg.umbral_rojo)}</p>
          </div>
          <div style={{ flex: 2, background: 'var(--rojo-bg)', border: '1px solid var(--rojo-bd)', borderRadius: 8, padding: '8px 12px' }}>
            <p style={{ margin: 0, fontSize: 11, fontWeight: 600, color: 'var(--rojo)' }}>Roja</p>
            <p style={{ margin: 0, fontSize: 11, color: 'var(--rojo)' }}>desde {formatM(cfg.umbral_rojo)}</p>
          </div>
        </div>
      </Section>

      {/* ── SLA ── */}
      <Section icon={<Bell size={16} color="var(--accent)" />} title="Escalamiento automático por tiempo (SLA)">
        {[
          { key: 'sla_24h', label: 'Primer recordatorio',    sub: 'Si el aprobador no responde en 24h', val: cfg.sla_24h },
          { key: 'sla_48h', label: 'Segundo aviso',          sub: 'Alerta de vencimiento de SLA a las 48h', val: cfg.sla_48h },
          { key: 'sla_72h', label: 'Escala al superior',     sub: 'Deriva al jerárquico automáticamente a las 72h', val: cfg.sla_72h },
          { key: 'sla_96h', label: 'Bloqueo crítico',        sub: 'Alerta crítica a dirección a las 96h', val: cfg.sla_96h },
        ].map(s => (
          <div key={s.key} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '11px 0', borderBottom: '1px solid var(--gray-100)' }}>
            <div>
              <p style={{ margin: 0, fontSize: 13, fontWeight: 500 }}>{s.label}</p>
              <p style={{ margin: 0, fontSize: 12, color: 'var(--gray-400)' }}>{s.sub}</p>
            </div>
            <Toggle on={s.val} onChange={v => set(s.key as keyof Config, v as Config[keyof Config])} />
          </div>
        ))}
      </Section>

      {/* ── Proveedores ── */}
      <Section icon={<Users size={16} color="var(--accent)" />} title="Lista blanca de proveedores">
        <p style={{ margin: '0 0 14px', fontSize: 12, color: 'var(--gray-400)' }}>
          Solo se aprueban automáticamente facturas de proveedores activos en esta lista.
        </p>
        {cfg.proveedores.map((p, i) => (
          <div key={p.rut} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '11px 0', borderBottom: '1px solid var(--gray-100)' }}>
            <div style={{ flex: 1 }}>
              <p style={{ margin: 0, fontSize: 13, fontWeight: 500 }}>{p.nombre}</p>
              <p style={{ margin: 0, fontSize: 12, color: 'var(--gray-400)', fontFamily: 'IBM Plex Mono, monospace' }}>
                {p.rut} · Media histórica: ${p.media.toLocaleString('es-CL')} CLP
              </p>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Shield size={13} color={p.activo ? 'var(--verde)' : 'var(--gray-400)'} />
              <Toggle on={p.activo} onChange={() => toggleProveedor(i)} />
            </div>
          </div>
        ))}
        <button style={{ marginTop: 14, padding: '8px 16px', background: 'var(--gray-50)', border: '1px dashed var(--gray-200)', borderRadius: 8, fontSize: 12, color: 'var(--gray-600)', cursor: 'pointer', fontFamily: 'Sora, sans-serif', width: '100%' }}>
          + Añadir proveedor
        </button>
      </Section>

    </div>
  )
}
