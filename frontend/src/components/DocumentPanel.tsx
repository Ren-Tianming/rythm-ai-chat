import { ReactNode, useEffect, useRef, useState } from 'react'
import { Paperclip, Trash2, RefreshCw, Eye, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { DocumentInfo } from '../types'

interface Props {
  conversationId?: string; ensureConversation: () => Promise<string>
  selected: string[]; onSelected: (ids: string[]) => void; disabled: boolean
  vision: boolean; onError: (message: string) => void; onBusy: (busy: boolean) => void
  onDocumentRemoved: (id: string) => void
  children: ReactNode
}

export function DocumentPanel({ conversationId, ensureConversation, selected, onSelected, disabled, vision, onError, onBusy, onDocumentRemoved, children }: Props) {
  const { t } = useTranslation()
  const [documents, setDocuments] = useState<DocumentInfo[]>([])
  const [uploading, setUploading] = useState(false)
  const [limits, setLimits] = useState({ max_bytes: 10485760, batch_limit: 5, pdf_pages: 100 })
  const [preview, setPreview] = useState<DocumentInfo | null>(null)
  const [dragging, setDragging] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const currentId = useRef(conversationId)
  currentId.current = conversationId
  useEffect(() => { void api.documentLimits().then(setLimits).catch(() => {}) }, [])
  const needsProcessing = documents.some(doc => doc.status === 'pending' || doc.status === 'processing')
  useEffect(() => {
    let live = true
    setDocuments([]); setPreview(null)
    if (!conversationId) return
    const refresh = () => {
      if (document.visibilityState !== 'visible') return
      void api.documents(conversationId).then(rows => { if (live) setDocuments(rows) })
        .catch((e: Error) => { if (live) onError(e.message) })
    }
    refresh()
    window.addEventListener('focus', refresh)
    document.addEventListener('visibilitychange', refresh)
    return () => {
      live = false
      window.removeEventListener('focus', refresh)
      document.removeEventListener('visibilitychange', refresh)
    }
  }, [conversationId, onError])
  useEffect(() => {
    if (!conversationId || !needsProcessing) return
    let live = true
    let timer: number
    let delay = 5000
    const poll = async () => {
      if (document.visibilityState === 'visible') {
        try {
          const rows = await api.documents(conversationId)
          if (!live) return
          setDocuments(rows)
          delay = 5000
          if (!rows.some(doc => doc.status === 'pending' || doc.status === 'processing')) return
        } catch (e) {
          if (!live) return
          onError(e instanceof Error ? e.message : t('error'))
          delay = Math.min(delay * 2, 30000)
        }
      }
      if (live) timer = window.setTimeout(() => void poll(), delay)
    }
    timer = window.setTimeout(() => void poll(), delay)
    return () => { live = false; window.clearTimeout(timer) }
  }, [conversationId, needsProcessing, onError, t])
  useEffect(() => { onBusy(uploading || documents.some(d => selected.includes(d.id) && (d.status !== 'ready' || d.requires_reindex))) }, [uploading, documents, selected, onBusy])

  const upload = async (files: FileList | File[]) => {
    if (disabled || uploading || !files.length) return
    if (files.length > limits.batch_limit || Array.from(files).some(f => f.size > limits.max_bytes)) {
      onError(t('uploadLimits', { size: limits.max_bytes / 1048576, count: limits.batch_limit, pages: limits.pdf_pages })); return
    }
    setUploading(true)
    try {
      const id = await ensureConversation()
      const rows = await api.uploadDocuments(id, Array.from(files))
      // Ignore responses from a conversation the user has since left.
      if (currentId.current && currentId.current !== id) return
      setDocuments(list => [...list.filter(d => !rows.some(r => r.id === d.id)), ...rows])
      onSelected([...new Set([...selected, ...rows.map(d => d.id)])])
    } catch (e) { onError(e instanceof Error ? e.message : t('error')) }
    finally { setUploading(false); if (input.current) input.current.value = '' }
  }
  const remove = async (doc: DocumentInfo) => {
    if (!window.confirm(t('documentDeleteConfirm'))) return
    try { await api.deleteDocument(doc.id); onDocumentRemoved(doc.id); setDocuments(list => list.filter(d => d.id !== doc.id)); onSelected(selected.filter(id => id !== doc.id)); if (preview?.id === doc.id) setPreview(null) }
    catch (e) { onError(e instanceof Error ? e.message : t('error')) }
  }
  const retry = async (doc: DocumentInfo) => {
    try { const row = await api.retryDocument(doc.id); onDocumentRemoved(doc.id); setDocuments(list => list.map(d => d.id === row.id ? row : d)) }
    catch (e) { onError(e instanceof Error ? e.message : t('error')) }
  }
  return <div className={`document-composer ${dragging ? 'document-composer--drag' : ''}`}
    onDragOver={e => { if (e.dataTransfer.types.includes('Files')) { e.preventDefault(); setDragging(true) } }}
    onDragLeave={e => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false) }}
    onDrop={e => { e.preventDefault(); setDragging(false); void upload(e.dataTransfer.files) }}>
    <div className="attachment-toolbar"><button type="button" className="attachment-button" disabled={disabled || uploading} onClick={() => input.current?.click()}><Paperclip size={16} />{t('attach')}</button>
      <small>{uploading ? t('uploadProgress') : t('dropFiles')}</small>
      <input ref={input} type="file" disabled={disabled || uploading} accept=".pdf,.txt,.md,.png,.jpg,.jpeg,.webp" multiple hidden aria-label={t('attach')} onChange={e => { if (e.target.files) void upload(e.target.files) }} />
    </div>
    <div className="attachment-list" aria-label={t('attachments')} aria-live="polite">{documents.map(doc => <div className={`attachment attachment--${doc.status}`} key={doc.id}>
      <label><input type="checkbox" checked={selected.includes(doc.id)} disabled={disabled} aria-label={`${t('selectFile')}: ${doc.filename}`} onChange={e => onSelected(e.target.checked ? [...selected, doc.id] : selected.filter(id => id !== doc.id))} /><span><strong>{doc.filename}</strong><small>{doc.mime_type.split('/')[1]} · {(doc.size_bytes / 1024).toFixed(1)} KB · {t(doc.status)} {doc.progress}%</small></span></label>
      {(doc.status === 'pending' || doc.status === 'processing') && <progress value={doc.progress} max={100} aria-label={t('processing')} />}
      {(doc.error || doc.requires_reindex) && <p className="attachment-error">{doc.error || t('reindex')}</p>}
      <div className="attachment-actions"><button type="button" aria-label={`${t('preview')}: ${doc.filename}`} onClick={() => void api.document(doc.id).then(setPreview).catch((e: Error) => onError(e.message))}><Eye size={15} /></button>
        {(doc.status === 'ready' || doc.status === 'failed') && <button type="button" disabled={disabled} aria-label={`${t('reprocess')}: ${doc.filename}`} onClick={() => void retry(doc)}><RefreshCw size={15} /></button>}
        <button type="button" disabled={disabled} aria-label={`${t('delete')}: ${doc.filename}`} onClick={() => void remove(doc)}><Trash2 size={15} /></button></div>
    </div>)}</div>
    {!vision && documents.some(d => selected.includes(d.id) && d.mime_type.startsWith('image/')) && <p className="attachment-notice">{t('ocrOnly')}</p>}
    {children}
    <small className="attachment-limits">{t('uploadLimits', { size: limits.max_bytes / 1048576, count: limits.batch_limit, pages: limits.pdf_pages })}</small>
    <details className="attachment-privacy"><summary>{t('privacy')}</summary><p>{t('documentPrivacy')}</p></details>
    {preview && <div className="modal-overlay" role="presentation" onClick={() => setPreview(null)}><section className="document-preview" role="dialog" aria-modal="true" aria-label={t('preview')} onClick={e => e.stopPropagation()}>
      <header><strong>{preview.filename}</strong><button type="button" aria-label={t('close')} onClick={() => setPreview(null)}><X /></button></header>
      <a href={`/api/v1/documents/${preview.id}/content`} target="_blank" rel="noopener noreferrer">{t('download')}</a>
      {preview.mime_type.startsWith('image/') && <img src={`/api/v1/documents/${preview.id}/content`} alt={preview.filename} />}
      <small>{t('previewLimited')}</small>{preview.preview?.map((part, i) => <div key={i}>{part.page_number && <strong>{t('page', { page: part.page_number })}</strong>}<pre>{part.content}</pre></div>)}
      {preview.error && <p role="alert">{preview.error}</p>}
    </section></div>}
  </div>
}
