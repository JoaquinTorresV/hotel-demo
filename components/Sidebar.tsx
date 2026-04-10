'use client'
import { useState, useEffect } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { LayoutDashboard, Settings, FileText, Hotel, Send, Sparkles, X } from 'lucide-react'

const NAV = [
  { section: 'Flujo 1 — Hotel recibe', items: [
    { href: '/',           icon: LayoutDashboard, label: 'Dashboard' },
    { href: '/documentos', icon: FileText,         label: 'Documentos' },
    { href: '/chat',       icon: Sparkles,         label: 'Chat IA' },
  ]},
  { section: 'Flujo 2 — Hotel emite', items: [
    { href: '/emision', icon: Send, label: 'Emisión y aprobación' },
  ]},
  { section: 'Sistema', items: [
    { href: '/configuracion', icon: Settings, label: 'Configuración' },
  ]},
]

function Logo() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <div style={{ width: 34, height: 34, borderRadius: 8, background: 'linear-gradient(135deg,#2563eb,#1d4ed8)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
        <Hotel size={18} color="white" />
      </div>
      <div>
        <p style={{ margin: 0, fontSize: 13, fontWeight: 600, color: 'white', lineHeight: 1.2 }}>Renaissance Santiago</p>
        <p style={{ margin: 0, fontSize: 10, color: '#64748b', lineHeight: 1.2 }}>Sistema de Aprobación</p>
      </div>
    </div>
  )
}

function NavLinks({ path, onClose }: { path: string; onClose?: () => void }) {
  return (
    <nav style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      {NAV.map((group, gi) => (
        <div key={gi}>
          {gi > 0 && <div style={{ margin: '10px 8px', borderTop: '1px solid rgba(255,255,255,0.07)' }} />}
          <p style={{ fontSize: 10, fontWeight: 600, color: '#334155', letterSpacing: '0.08em', textTransform: 'uppercase', padding: '4px 16px 8px', margin: 0 }}>
            {group.section}
          </p>
          {group.items.map(item => {
            const Icon = item.icon
            return (
              <Link key={item.href} href={item.href}
                className={`nav-item ${path === item.href ? 'active' : ''}`}
                onClick={onClose}>
                <Icon size={16} />{item.label}
              </Link>
            )
          })}
        </div>
      ))}
    </nav>
  )
}

function StatusDot() {
  return (
    <div style={{ padding: '24px 8px 0' }}>
      <div style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 10, padding: '10px 12px', border: '1px solid rgba(255,255,255,0.06)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ width: 7, height: 7, borderRadius: '50%', background: '#22c55e', boxShadow: '0 0 6px #22c55e' }} />
          <span style={{ fontSize: 12, color: '#94a3b8' }}>Motor activo</span>
        </div>
      </div>
    </div>
  )
}

export default function Sidebar() {
  const path = usePathname()
  const [open, setOpen] = useState(false)

  useEffect(() => { setOpen(false) }, [path])
  useEffect(() => {
    document.body.style.overflow = open ? 'hidden' : ''
    return () => { document.body.style.overflow = '' }
  }, [open])

  return (
    <>
      {/* Desktop */}
      <div className="sidebar" style={{ padding: '0 12px 24px' }}>
        <div style={{ padding: '24px 8px 20px', borderBottom: '1px solid rgba(255,255,255,0.07)', marginBottom: 16 }}>
          <Logo />
        </div>
        <NavLinks path={path} />
        <StatusDot />
      </div>

      {/* Mobile topbar */}
      <div className="mobile-topbar">
        <Logo />
        <button className="hamburger" onClick={() => setOpen(true)} aria-label="Menú">
          <span /><span /><span />
        </button>
      </div>

      {/* Overlay */}
      <div className={`sidebar-overlay ${open ? 'visible' : ''}`} onClick={() => setOpen(false)} />

      {/* Drawer */}
      <div className={`sidebar-drawer ${open ? 'open' : ''}`}>
        <div style={{ padding: '20px 8px 20px', borderBottom: '1px solid rgba(255,255,255,0.07)', marginBottom: 16, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Logo />
          <button onClick={() => setOpen(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#64748b', padding: 4 }}>
            <X size={18} />
          </button>
        </div>
        <NavLinks path={path} onClose={() => setOpen(false)} />
        <StatusDot />
      </div>
    </>
  )
}
