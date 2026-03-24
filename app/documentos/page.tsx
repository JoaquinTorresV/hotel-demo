'use client'
import { useEffect, useState } from 'react'
import { listarDocumentos, DocListItem } from '@/lib/api'
import { CheckCircle, AlertCircle, XCircle, RefreshCw, Clock } from 'lucide-react'

const ZONA_LABEL: Record<string,string> = { verde:'Verde', amarilla:'Amarilla', roja:'Roja' }
const ZONA_COLOR: Record<string,string> = { verde:'var(--verde)', amarilla:'var(--amarillo)', roja:'var(--rojo)' }

function ZonaBadge({ zona }: { zona: string }) {
  return <span className={`badge-${zona}`} style={{ padding: '2px 10px', borderRadius: 20, fontSize: 11, fontWeight: 600 }}>{ZONA_LABEL[zona]??zona}</span>
}

function fmtCLP(n: number) { return `$ ${n.toLocaleString('es-CL')}` }
function fmtDate(ts: string) { return new Date(ts).toLocaleString('es-CL', { day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit' }) }

export default function Documentos() {
  const [docs, setDocs] = useState<DocListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [filtro, setFiltro] = useState<'todos'|'verde'|'amarilla'|'roja'>('todos')

  const cargar = () => {
    setLoading(true)
    listarDocumentos().then(d => { setDocs(d.documentos.slice().reverse()); setLoading(false) }).catch(() => setLoading(false))
  }
  useEffect(() => { cargar() }, [])

  const filtrados = filtro === 'todos' ? docs : docs.filter(d => d.zona === filtro)

  return (
    <div style={{ padding: '32px 36px', maxWidth: 1100 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 28 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 600 }}>Documentos</h1>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--gray-400)' }}>{docs.length} documentos procesados</p>
        </div>
        <button onClick={cargar} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px', background: 'white', border: '1px solid var(--gray-200)', borderRadius: 8, fontSize: 12, cursor: 'pointer', fontFamily: 'Sora, sans-serif', color: 'var(--gray-600)' }}>
          <RefreshCw size={13} />Actualizar
        </button>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
        {(['todos','verde','amarilla','roja'] as const).map(f => (
          <button key={f} onClick={() => setFiltro(f)} style={{ padding: '6px 14px', borderRadius: 20, fontSize: 12, fontWeight: 500, cursor: 'pointer', fontFamily: 'Sora, sans-serif', border: 'none', background: filtro === f ? 'var(--gray-900)' : 'white', color: filtro === f ? 'white' : 'var(--gray-600)', boxShadow: filtro === f ? 'none' : '0 0 0 1px var(--gray-200)', transition: 'all 0.15s' }}>
            {f === 'todos' ? 'Todos' : `Zona ${ZONA_LABEL[f]}`}
          </button>
        ))}
      </div>

      <div style={{ background: 'white', borderRadius: 16, border: '1px solid var(--gray-200)', overflow: 'hidden' }}>
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--gray-400)' }}>
            <RefreshCw size={20} style={{ animation: 'spin 1s linear infinite', margin: '0 auto 12px', display: 'block' }} />
            <p style={{ margin: 0, fontSize: 13 }}>Cargando documentos…</p>
          </div>
        ) : filtrados.length === 0 ? (
          <div style={{ padding: 60, textAlign: 'center', color: 'var(--gray-400)' }}>
            <p style={{ margin: 0, fontSize: 13 }}>No hay documentos aún. Sube una factura desde el Dashboard.</p>
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--gray-100)', background: 'var(--gray-50)' }}>
                {['Zona','Proveedor','Folio','Total CLP','Procesado','Estado','Acción'].map(h => (
                  <th key={h} style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: 'var(--gray-400)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtrados.map((doc, i) => (
                <tr key={doc.doc_id} style={{ borderBottom: '1px solid var(--gray-100)', background: i % 2 === 0 ? 'white' : 'var(--gray-50)' }}>
                  <td style={{ padding: '12px 16px' }}><ZonaBadge zona={doc.zona} /></td>
                  <td style={{ padding: '12px 16px', fontWeight: 500 }}>{doc.proveedor ?? '—'}</td>
                  <td style={{ padding: '12px 16px', fontFamily: 'IBM Plex Mono, monospace', fontSize: 12, color: 'var(--gray-600)' }}>
                    {doc.folio ? `N° ${doc.folio}` : '—'}
                  </td>
                  <td style={{ padding: '12px 16px', fontFamily: 'IBM Plex Mono, monospace', fontWeight: 600, color: ZONA_COLOR[doc.zona] }}>
                    {fmtCLP(doc.total_clp)}
                  </td>
                  <td style={{ padding: '12px 16px', fontSize: 12, color: 'var(--gray-400)', display: 'flex', alignItems: 'center', gap: 4 }}>
                    <Clock size={11} />{fmtDate(doc.timestamp)}
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <span style={{ fontSize: 12, color: ZONA_COLOR[doc.zona], display: 'flex', alignItems: 'center', gap: 4 }}>
                      {doc.zona === 'verde'    && <><CheckCircle size={12} /> Aprobado</>}
                      {doc.zona === 'amarilla' && <><AlertCircle size={12} /> En revisión</>}
                      {doc.zona === 'roja'     && <><XCircle size={12} /> Bloqueado</>}
                    </span>
                  </td>
                  <td style={{ padding: '12px 16px', fontSize: 11, color: 'var(--gray-400)', maxWidth: 200 }}>
                    <span style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                      {doc.accion}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
