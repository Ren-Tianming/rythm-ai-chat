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
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [newPasswordConfirm, setNewPasswordConfirm] = useState('')
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
    const isCurrent = sessions.some((item) => item.id === id && item.current)
    await api.revokeSession(id)
    if (isCurrent) {
      window.location.reload()
      return
    }
    setSessions((current) => current.filter((item) => item.id !== id))
  }

  const changePassword = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError('')
    try {
      await api.changePassword(currentPassword, newPassword, newPasswordConfirm)
      setCurrentPassword(''); setNewPassword(''); setNewPasswordConfirm('')
    } catch (reason) { setError(reason instanceof Error ? reason.message : t('error')) }
    finally { setBusy(false) }
  }

  return <AnimatePresence>{open && (
    <motion.div className="modal-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onMouseDown={onClose}>
      <motion.section className="settings-modal" initial={{ scale: .96, y: 16 }} animate={{ scale: 1, y: 0 }} exit={{ scale: .96, y: 16 }} onMouseDown={(e) => e.stopPropagation()}>
        <header><div><small>{t('settings')}</small><h2>{t('account')}</h2></div><button className="icon-button" onClick={onClose}><X /></button></header>
        {error && <div className="notice notice--error">{error}</div>}
        <form onSubmit={save} className="settings-form">
          <label><span>{t('displayName')}</span><input value={displayName} maxLength={80} onChange={(e) => setDisplayName(e.target.value)} /></label>
          <label><span>{t('email')}</span><input value={user.email} disabled /></label>
          <label><span>{t('language')}</span><select value={i18n.language} onChange={(e) => void changeLocale(e.target.value as Locale)}><option value="zh-CN">中文</option><option value="ja-JP">日本語</option><option value="en-US">English</option></select></label>
          <button className="primary-button" disabled={busy}>{t('save')}</button>
        </form>
        <form onSubmit={changePassword} className="password-form">
          <h3>{t('changePassword')}</h3>
          <input type="password" required minLength={1} maxLength={128} value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} placeholder={t('currentPassword')} autoComplete="current-password" />
          <input type="password" required minLength={12} maxLength={128} value={newPassword} onChange={(e) => setNewPassword(e.target.value)} placeholder={t('newPassword')} autoComplete="new-password" />
          <input type="password" required minLength={12} maxLength={128} value={newPasswordConfirm} onChange={(e) => setNewPasswordConfirm(e.target.value)} placeholder={t('passwordConfirm')} autoComplete="new-password" />
          <button className="primary-button" disabled={busy}>{t('changePassword')}</button>
        </form>
        <div className="sessions-panel"><h3><MonitorSmartphone size={18} />{t('sessions')}</h3>{sessions.map((session) => (
          <div className="session-row" key={session.id}><div><strong>{session.user_agent?.split(')')[0] || t('unknownDevice')}</strong><small>{session.ip_address || '—'} · {new Date(session.last_seen_at).toLocaleString(user.locale)}</small></div>{session.current && <span className="current-pill">{t('current')}</span>}<button className="icon-button danger" title={t('revoke')} onClick={() => void revoke(session.id)}><LogOut size={17} /></button></div>
        ))}</div>
      </motion.section>
    </motion.div>
  )}</AnimatePresence>
}
