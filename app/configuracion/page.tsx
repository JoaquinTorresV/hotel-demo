'use client'
import { useState } from 'react'
import { Mail, Save, CheckCircle, Bell, Shield, Sliders, Eye, EyeOff, AlertCircle, Sparkles, MessageCircle, Users } from 'lucide-react'
import { getConfig, saveConfig, Config } from '@/lib/api'

function Toggle({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className={`toggle-track ${on?'on':''}`} onClick={()=>onChange(!on)}>
      <div className="toggle-thumb" />
    </div>
  )
}

function Section({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div style={{ background:'white', border:'1px solid var(--gray-200)', borderRadius:16, padding:24, marginBottom:16 }}>
      <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:20 }}>
        <div style={{ width:32, height:32, borderRadius:8, background:'#eff6ff', display:'flex', alignItems:'center', justifyContent:'center' }}>{icon}</div>
        <h2 style={{ margin:0, fontSize:14, fontWeight:600 }}>{title}</h2>
      </div>
      {children}
    </div>
  )
}

const inp: React.CSSProperties = {
  width:'100%', padding:'9px 12px', borderRadius:8,
  border:'1px solid var(--gray-200)', fontSize:13,
  fontFamily:'Sora,sans-serif', outline:'none',
  background:'white', color:'var(--gray-900)',
}

function fmtM(n: number) {
  if (n>=1000000) return `$${(n/1000000).toFixed(n%1000000===0?0:1)}M`
  return `$${(n/1000).toFixed(0)}K`
}

export default function Configuracion() {
  const [cfg, setCfg]       = useState<Config>(getConfig())
  const [saved, setSaved]   = useState(false)
  const [showPass, setShowPass] = useState(false)
  const [showGem,  setShowGem]  = useState(false)

  const set = <K extends keyof Config>(k: K, v: Config[K]) =>
    setCfg(p => ({ ...p, [k]: v }))

  const guardar = () => {
    saveConfig(cfg)
    setSaved(true)
    setTimeout(() => setSaved(false), 2500)
  }

  return (
    <div style={{ padding:'32px 36px', maxWidth:800 }}>
      <div style={{ display:'flex', alignItems:'flex-start', justifyContent:'space-between', marginBottom:28 }}>
        <div>
          <h1 style={{ margin:0, fontSize:22, fontWeight:600 }}>Configuración</h1>
          <p style={{ margin:'4px 0 0', fontSize:13, color:'var(--gray-400)' }}>Ajusta el sistema sin tocar código · Guardado en el navegador</p>
        </div>
        <button onClick={guardar}
          style={{ display:'flex', alignItems:'center', gap:8, padding:'10px 20px', background:saved?'var(--verde)':'var(--accent)', color:'white', border:'none', borderRadius:10, fontSize:13, fontWeight:600, cursor:'pointer', fontFamily:'Sora,sans-serif', transition:'background 0.2s' }}>
          {saved ? <CheckCircle size={15} /> : <Save size={15} />}
          {saved ? 'Guardado' : 'Guardar cambios'}
        </button>
      </div>

      {/* Email remitente */}
      <Section icon={<Mail size={16} color="var(--accent)" />} title="Cuenta de correo remitente (Gmail)">
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}>
          <div>
            <label style={{ display:'block', fontSize:12, fontWeight:600, color:'var(--gray-600)', marginBottom:6 }}>Gmail remitente</label>
            <p style={{ margin:'0 0 8px', fontSize:11, color:'var(--gray-400)' }}>El email que envía las notificaciones</p>
            <input style={inp} type="email" placeholder="sistema@hotel.cl"
              value={cfg.email_remitente} onChange={e=>set('email_remitente',e.target.value)} />
          </div>
          <div>
            <label style={{ display:'block', fontSize:12, fontWeight:600, color:'var(--gray-600)', marginBottom:6 }}>Contraseña de aplicación</label>
            <p style={{ margin:'0 0 8px', fontSize:11, color:'var(--gray-400)' }}>
              <a href="https://myaccount.google.com/apppasswords" target="_blank" style={{ color:'var(--accent)', textDecoration:'none' }}>Generar en Google →</a>
            </p>
            <div style={{ position:'relative' }}>
              <input style={{ ...inp, paddingRight:36 }} type={showPass?'text':'password'}
                placeholder="xxxx xxxx xxxx xxxx"
                value={cfg.email_password} onChange={e=>set('email_password',e.target.value)} />
              <button onClick={()=>setShowPass(!showPass)} style={{ position:'absolute', right:10, top:'50%', transform:'translateY(-50%)', background:'none', border:'none', cursor:'pointer', color:'var(--gray-400)', padding:0 }}>
                {showPass ? <EyeOff size={15}/> : <Eye size={15}/>}
              </button>
            </div>
          </div>
        </div>
      </Section>

      {/* Destinatarios */}
      <Section icon={<Users size={16} color="var(--accent)" />} title="Destinatarios de notificaciones">
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}>
          <div>
            <label style={{ display:'block', fontSize:12, fontWeight:600, color:'var(--gray-600)', marginBottom:6 }}>Email aprobador</label>
            <p style={{ margin:'0 0 8px', fontSize:11, color:'var(--gray-400)' }}>Recibe alertas Zona Amarilla con botones de acción</p>
            <input style={inp} type="email" placeholder="jefe.finanzas@hotel.cl"
              value={cfg.email_aprobador} onChange={e=>set('email_aprobador',e.target.value)} />
          </div>
          <div>
            <label style={{ display:'block', fontSize:12, fontWeight:600, color:'var(--gray-600)', marginBottom:6 }}>Email gerencia</label>
            <p style={{ margin:'0 0 8px', fontSize:11, color:'var(--gray-400)' }}>Recibe alertas Zona Roja + resumen diario</p>
            <input style={inp} type="email" placeholder="gerente@hotel.cl"
              value={cfg.email_gerencia} onChange={e=>set('email_gerencia',e.target.value)} />
          </div>
        </div>
      </Section>

      {/* IA Gemini */}
      <Section icon={<Sparkles size={16} color="var(--accent)" />} title="Inteligencia Artificial — Gemini">
        <div style={{ padding:'10px 14px', background:cfg.gemini_api_key?'var(--verde-bg)':'var(--amarillo-bg)', border:`1px solid ${cfg.gemini_api_key?'var(--verde-bd)':'var(--amarillo-bd)'}`, borderRadius:8, marginBottom:14, fontSize:12, color:cfg.gemini_api_key?'var(--verde)':'var(--amarillo)', display:'flex', alignItems:'center', gap:6 }}>
          {cfg.gemini_api_key ? <CheckCircle size={13}/> : <AlertCircle size={13}/>}
          {cfg.gemini_api_key ? 'IA activa — análisis automático y chat habilitados.' : 'Sin API key — obtén una gratis en aistudio.google.com'}
        </div>
        <div>
          <label style={{ display:'block', fontSize:12, fontWeight:600, color:'var(--gray-600)', marginBottom:6 }}>API Key de Gemini</label>
          <p style={{ margin:'0 0 8px', fontSize:11, color:'var(--gray-400)' }}>
            Gratis en <a href="https://aistudio.google.com" target="_blank" style={{ color:'var(--accent)', textDecoration:'none' }}>aistudio.google.com</a> → Get API key
          </p>
          <div style={{ position:'relative' }}>
            <input style={{ ...inp, paddingRight:36 }} type={showGem?'text':'password'}
              placeholder="AIzaSy..." value={cfg.gemini_api_key||''}
              onChange={e=>set('gemini_api_key',e.target.value)} />
            <button onClick={()=>setShowGem(!showGem)} style={{ position:'absolute', right:10, top:'50%', transform:'translateY(-50%)', background:'none', border:'none', cursor:'pointer', color:'var(--gray-400)', padding:0 }}>
              {showGem ? <EyeOff size={15}/> : <Eye size={15}/>}
            </button>
          </div>
        </div>
      </Section>

      {/* Umbrales */}
      <Section icon={<Sliders size={16} color="var(--accent)" />} title="Umbrales de clasificación">
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:20, marginBottom:16 }}>
          <div>
            <label style={{ display:'block', fontSize:12, fontWeight:600, color:'var(--gray-600)', marginBottom:6 }}>Zona Verde — hasta {fmtM(cfg.umbral_verde)} CLP</label>
            <input type="range" min={100000} max={5000000} step={50000} value={cfg.umbral_verde}
              onChange={e=>set('umbral_verde',+e.target.value)} style={{ width:'100%', accentColor:'var(--verde)' }} />
          </div>
          <div>
            <label style={{ display:'block', fontSize:12, fontWeight:600, color:'var(--gray-600)', marginBottom:6 }}>Zona Roja — desde {fmtM(cfg.umbral_rojo)} CLP</label>
            <input type="range" min={5000000} max={50000000} step={500000} value={cfg.umbral_rojo}
              onChange={e=>set('umbral_rojo',+e.target.value)} style={{ width:'100%', accentColor:'var(--rojo)' }} />
          </div>
        </div>
        <div style={{ display:'flex', gap:8 }}>
          {[{label:'Verde',cl:'verde',sub:`hasta ${fmtM(cfg.umbral_verde)}`},{label:'Amarilla',cl:'amarilla',sub:`${fmtM(cfg.umbral_verde)}–${fmtM(cfg.umbral_rojo)}`},{label:'Roja',cl:'roja',sub:`desde ${fmtM(cfg.umbral_rojo)}`}].map(z=>(
            <div key={z.cl} style={{ flex:1, background:`var(--${z.cl}-bg)`, border:`1px solid var(--${z.cl}-bd)`, borderRadius:8, padding:'8px 12px' }}>
              <p style={{ margin:0, fontSize:11, fontWeight:600, color:`var(--${z.cl})` }}>{z.label}</p>
              <p style={{ margin:0, fontSize:11, color:`var(--${z.cl})` }}>{z.sub}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* WhatsApp placeholder */}
      <Section icon={<MessageCircle size={16} color="var(--accent)" />} title="WhatsApp Business (fase 2)">
        <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', padding:'12px 14px', background:'var(--gray-50)', borderRadius:8, border:'1px solid var(--gray-200)' }}>
          <div>
            <p style={{ margin:0, fontSize:13, fontWeight:500 }}>Activar notificaciones por WhatsApp</p>
            <p style={{ margin:0, fontSize:12, color:'var(--gray-400)' }}>Requiere WhatsApp Business API (Twilio o Meta)</p>
          </div>
          <Toggle on={cfg.whatsapp_activo} onChange={v=>set('whatsapp_activo',v)} />
        </div>
      </Section>
    </div>
  )
}
