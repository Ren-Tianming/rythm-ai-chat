import { FormEvent, useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { LogOut, MonitorSmartphone, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { Locale, User, UserSession } from '../types'

interface Props {
  open: boolean
  user: User
  onClose: () => void
  onUserChange: (user: User) => void
}

export function SettingsModal({ open, user, onClose, onUserChange }: Props) {
  const { t, i18n } = useTranslation()
  const [sessions, setSessions] = useState<UserSession[]>([])
  const [displayName, setDisplayName] = useState(user.display_name || '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (open) void api.sessions().then(setSessions).catch((reason: Error) => setError(reason.message))
  }, [open])

  const save = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError('')
    try {
      onUserChange(await api.updateMe({ display_name: displayName || null }))
      onClose()
    } catch (reason) { setError(reason instanceof Error ? reason.message : t('error')) }
    finally { setBusy(false) }
  }

  const changeLocale = async (locale: Locale) => {
    await i18n.changeLanguage(locale); localStorage.setItem('rythm_locale', locale)
    try { onUserChange(await api.updateMe({ locale })) } catch { /* Local preference still works. */ }
  }

  const revoke = async (id: string) => {
    await api.revokeSession(id)
    setSessions((current) => current.filter((item) => item.id !== id))
  }

  return <AnimatePresence>{open && (
    <motion.div className="modal-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onMouseDown={onClose}>
      <motion.section className="settings-modal" initial={{ scale: .96, y: 16 }} animate={{ scale: 1, y: 0 }} exit={{ scale: .96, y: 16 }} onMouseDown={(e) => e.stopPropagation()}>
        <header><div><small>{t('settings')}</small><h2>{t('account')}</h2></div><button className="icon-button" onClick={onClose}><X /></button></header>
        {error && <div className="notice notice--error">{error}</div>}
        <form onSubmit={save} className="settings-form">
          <label><span>{t('displayName')}</span><input value={displayName} maxLength={80} onChange={(e) => setDisplayName(e.target.value)} /></label>
          <label><span>{t('email')}</span><input value={user.email} disabled /></label>
          <label><span>Language</span><select value={i18n.language.slice(0, 2)} onChange={(e) => void changeLocale(e.target.value as Locale)}><option value="zh">中文</option><option value="ja">日本語</option><option value="en">English</option></select></label>
          <button className="primary-button" disabled={busy}>{t('save')}</button>
        </form>
        <div className="sessions-panel"><h3><MonitorSmartphone size={18} />{t('sessions')}</h3>{sessions.map((session) => (
          <div className="session-row" key={session.id}><div><strong>{session.user_agent?.split(')')[0] || 'Unknown device'}</strong><small>{session.ip_address || '—'} · {new Date(session.last_seen_at).toLocaleString()}</small></div>{session.current ? <span className="current-pill">{t('current')}</span> : <button className="icon-button danger" title={t('revoke')} onClick={() => void revoke(session.id)}><LogOut size={17} /></button>}</div>
        ))}</div>
      </motion.section>
    </motion.div>
  )}</AnimatePresence>
}
