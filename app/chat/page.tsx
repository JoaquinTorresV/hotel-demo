'use client'
import { useState, useEffect, useRef } from 'react'
import { Send, MessageCircle, Sparkles, AlertCircle } from 'lucide-react'
import { iaChat, iaEstado } from '@/lib/api'

interface Msg { rol: 'user'|'ia'; texto: string; ts: Date }

const SUGERENCIAS = [
  '¿Cuánto llevamos gastado este mes?',
  '¿Hay facturas bloqueadas pendientes?',
  '¿Qué proveedor tiene el monto más alto?',
  '¿Cuántas facturas se aprobaron automáticamente?',
  '¿Hay alguna anomalía que deba revisar?',
]

export default function Chat() {
  const [msgs, setMsgs]       = useState<Msg[]>([])
  const [input, setInput]     = useState('')
  const [cargando, setCargando] = useState(false)
  const [tieneIA, setTieneIA] = useState<boolean | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    iaEstado()
      .then((r) => setTieneIA(!!r.disponible))
      .catch(() => setTieneIA(false))
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior:'smooth' })
  }, [msgs])

  const enviar = async (texto?: string) => {
    const q = (texto ?? input).trim()
    if (!q || cargando) return
    setInput('')
    setMsgs(prev => [...prev, { rol:'user', texto:q, ts:new Date() }])
    setCargando(true)
    try {
      const res = await iaChat(q)
      setMsgs(prev => [...prev, { rol:'ia', texto:res.respuesta, ts:new Date() }])
    } catch {
      setMsgs(prev => [...prev, { rol:'ia', texto:'Error al conectar con el motor de IA.', ts:new Date() }])
    } finally { setCargando(false) }
  }

  return (
    <div style={{ padding:'32px 36px', maxWidth:800, display:'flex', flexDirection:'column', height:'calc(100vh - 64px)' }}>
      <div style={{ marginBottom:20 }}>
        <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:6 }}>
          <div style={{ width:36, height:36, borderRadius:10, background:'linear-gradient(135deg, #2563eb, #7c3aed)', display:'flex', alignItems:'center', justifyContent:'center' }}>
            <Sparkles size={18} color="white" />
          </div>
          <div>
            <h1 style={{ margin:0, fontSize:20, fontWeight:600 }}>Chat con los documentos</h1>
            <p style={{ margin:0, fontSize:12, color:'var(--gray-400)' }}>
              {tieneIA === null ? 'Verificando estado de IA...' : (tieneIA ? 'Activo — Gemini Flash' : 'IA no configurada en backend')}
            </p>
          </div>
        </div>
        {tieneIA === false && (
          <div style={{ background:'var(--amarillo-bg)', border:'1px solid var(--amarillo-bd)', borderRadius:10, padding:'10px 14px', fontSize:12, color:'var(--amarillo)', display:'flex', gap:8, alignItems:'center' }}>
            <AlertCircle size={14} style={{ flexShrink:0 }} />
            La API key de Gemini debe estar configurada en las variables de entorno del backend (Vercel).
          </div>
        )}
      </div>

      <div style={{ flex:1, overflowY:'auto', minHeight:0, marginBottom:16 }}>
        {msgs.length === 0 && (
          <div style={{ textAlign:'center', padding:'40px 20px' }}>
            <MessageCircle size={40} style={{ color:'var(--gray-200)', margin:'0 auto 16px', display:'block' }} />
            <p style={{ margin:'0 0 24px', fontSize:13, color:'var(--gray-400)' }}>Pregunta sobre las facturas del hotel</p>
            <div style={{ display:'flex', flexWrap:'wrap', gap:8, justifyContent:'center' }}>
              {SUGERENCIAS.map(s => (
                <button key={s} onClick={() => enviar(s)}
                  style={{ padding:'7px 14px', background:'white', border:'1px solid var(--gray-200)', borderRadius:20, fontSize:12, cursor:'pointer', fontFamily:'Sora,sans-serif', color:'var(--gray-700)' }}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {msgs.map((m,i) => (
          <div key={i} style={{ display:'flex', justifyContent:m.rol==='user'?'flex-end':'flex-start', marginBottom:14 }}>
            {m.rol==='ia' && (
              <div style={{ width:28, height:28, borderRadius:8, background:'linear-gradient(135deg,#2563eb,#7c3aed)', display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0, marginRight:10, marginTop:2 }}>
                <Sparkles size={13} color="white" />
              </div>
            )}
            <div style={{ maxWidth:'75%', padding:'10px 14px', borderRadius:m.rol==='user'?'16px 16px 4px 16px':'16px 16px 16px 4px', background:m.rol==='user'?'var(--accent)':'white', color:m.rol==='user'?'white':'var(--gray-900)', border:m.rol==='ia'?'1px solid var(--gray-200)':'none', fontSize:13, lineHeight:1.65 }}>
              {m.texto}
              <p style={{ margin:'5px 0 0', fontSize:10, opacity:0.6, textAlign:'right' }}>
                {m.ts.toLocaleTimeString('es-CL',{hour:'2-digit',minute:'2-digit'})}
              </p>
            </div>
          </div>
        ))}
        {cargando && (
          <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:14 }}>
            <div style={{ width:28, height:28, borderRadius:8, background:'linear-gradient(135deg,#2563eb,#7c3aed)', display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0 }}>
              <Sparkles size={13} color="white" />
            </div>
            <div style={{ background:'white', border:'1px solid var(--gray-200)', borderRadius:'16px 16px 16px 4px', padding:'12px 16px' }}>
              <span className="spinner" />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div style={{ background:'white', border:'1px solid var(--gray-200)', borderRadius:14, padding:'10px 12px', display:'flex', gap:10, alignItems:'flex-end' }}>
        <textarea value={input} onChange={e=>setInput(e.target.value)}
          onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();enviar()}}}
          placeholder="Pregunta sobre facturas, proveedores, gastos…" rows={1}
          style={{ flex:1, border:'none', outline:'none', resize:'none', fontSize:13, fontFamily:'Sora,sans-serif', background:'transparent', color:'var(--gray-900)', lineHeight:1.5, maxHeight:120, overflowY:'auto' }} />
        <button onClick={() => enviar()} disabled={!input.trim()||cargando}
          style={{ width:34, height:34, borderRadius:10, background:input.trim()&&!cargando?'var(--accent)':'var(--gray-200)', border:'none', display:'flex', alignItems:'center', justifyContent:'center', cursor:input.trim()&&!cargando?'pointer':'default', flexShrink:0 }}>
          <Send size={15} color={input.trim()&&!cargando?'white':'var(--gray-400)'} />
        </button>
      </div>
    </div>
  )
}
