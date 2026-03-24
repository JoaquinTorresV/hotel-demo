'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { LayoutDashboard, Settings, FileText, Hotel, Send } from 'lucide-react'

export default function Sidebar() {
  const path = usePathname()

  return (
    <div className="sidebar" style={{ padding: '0 12px 24px' }}>
      {/* Logo */}
      <div style={{ padding: '24px 8px 20px', borderBottom: '1px solid rgba(255,255,255,0.07)', marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 34, height: 34, borderRadius: 8,
            background: 'linear-gradient(135deg, #2563eb, #1d4ed8)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Hotel size={18} color="white" />
          </div>
          <div>
            <p style={{ margin: 0, fontSize: 13, fontWeight: 600, color: 'white', lineHeight: 1.2 }}>Renaissance Santiago</p>
            <p style={{ margin: 0, fontSize: 10, color: '#64748b', lineHeight: 1.2 }}>Sistema de Aprobación</p>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <p style={{ fontSize: 10, fontWeight: 600, color: '#334155', letterSpacing: '0.08em', textTransform: 'uppercase', padding: '4px 16px 8px', margin: 0 }}>
          Principal
        </p>
        <Link href="/" className={`nav-item ${path === '/' ? 'active' : ''}`}>
          <LayoutDashboard size={16} />
          Dashboard
        </Link>
        <Link href="/documentos" className={`nav-item ${path === '/documentos' ? 'active' : ''}`}>
          <FileText size={16} />
          Documentos
        </Link>

        <p style={{ fontSize: 10, fontWeight: 600, color: '#334155', letterSpacing: '0.08em', textTransform: 'uppercase', padding: '16px 16px 8px', margin: 0 }}>
          Sistema
        </p>
        <Link href="/configuracion" className={`nav-item ${path === '/configuracion' ? 'active' : ''}`}>
          <Settings size={16} />
          Configuración
        </Link>
      </nav>

      {/* Status dot */}
      <div style={{ marginTop: 'auto', paddingTop: 32, padding: '32px 8px 0' }}>
        <div style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 10, padding: '10px 12px', border: '1px solid rgba(255,255,255,0.06)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ width: 7, height: 7, borderRadius: '50%', background: '#22c55e', boxShadow: '0 0 6px #22c55e' }} />
            <span style={{ fontSize: 12, color: '#94a3b8' }}>Motor activo</span>
          </div>
          <p style={{ margin: '4px 0 0', fontSize: 11, color: '#475569', fontFamily: 'IBM Plex Mono, monospace' }}>
            localhost:8000
          </p>
        </div>
      </div>
    </div>
  )
}
