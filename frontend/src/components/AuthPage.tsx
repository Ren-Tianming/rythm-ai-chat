import { FormEvent, useMemo, useState } from 'react'
import { Turnstile } from '@marsidev/react-turnstile'
import { motion } from 'framer-motion'
import { ArrowRight, LockKeyhole, Mail, UserRound } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { User } from '../types'
import { Brand } from './Brand'
import { LanguagePicker } from './LanguagePicker'

type Mode = 'login' | 'register' | 'forgot' | 'reset'

interface Props {
  onAuthenticated: (user: User) => void
  initialMode?: Mode
  resetToken?: string
  notice?: string
}

export function AuthPage({ onAuthenticated, initialMode = 'login', resetToken, notice }: Props) {
  const { t, i18n } = useTranslation()
  const [mode, setMode] = useState<Mode>(initialMode)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [passwordConfirm, setPasswordConfirm] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [termsAccepted, setTermsAccepted] = useState(false)
  const [turnstileToken, setTurnstileToken] = useState<string>()
  const [message, setMessage] = useState(notice || '')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const siteKey = import.meta.env.VITE_TURNSTILE_SITE_KEY as string | undefined
  const termsVersion = (import.meta.env.VITE_TERMS_VERSION as string | undefined) || '2026-07-29'
  const title = useMemo(() => t(mode), [mode, t])
  const locale = i18n.language.startsWith('ja') ? 'ja-JP' : i18n.language.startsWith('en') ? 'en-US' : 'zh-CN'

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true); setError(''); setMessage('')
    try {
      if (mode === 'login') {
        const result = await api.login(email, password, turnstileToken)
        onAuthenticated(result.user)
      } else if (mode === 'register') {
        await api.register({
          email,
          password,
          password_confirm: passwordConfirm,
          display_name: displayName || undefined,
          locale,
          terms_version: termsVersion,
          terms_accepted: termsAccepted,
          turnstile_token: turnstileToken,
        })
        setMessage(t('registrationSent')); setMode('login')
      } else if (mode === 'forgot') {
        await api.forgot(email, turnstileToken)
        setMessage(t('resetSent'))
      } else if (mode === 'reset' && resetToken) {
        await api.reset(resetToken, password, passwordConfirm)
        setMessage(t('resetDone')); setMode('login')
        window.history.replaceState({}, '', '/')
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('error'))
    } finally { setBusy(false) }
  }

  return (
    <main className="auth-page">
      <div className="ambient ambient--one" /><div className="ambient ambient--two" />
      <header className="auth-header"><Brand compact /><LanguagePicker /></header>
      <motion.section className="auth-card" initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }}>
        <div className="auth-card__visual">
          <Brand />
          <p>{t('welcomeHint')}</p>
          <div className="model-orbits"><i /><i /><i /></div>
        </div>
        <div className="auth-card__form">
          <div className="auth-tabs">
            {(['login', 'register'] as const).map((item) => (
              <button className={mode === item ? 'active' : ''} key={item} onClick={() => setMode(item)} type="button">{t(item)}</button>
            ))}
          </div>
          <h1>{title}</h1>
          {message && <div className="notice notice--success">{message}</div>}
          {error && <div className="notice notice--error">{error}</div>}
          <form onSubmit={submit}>
            {mode === 'register' && <label><span>{t('displayName')}</span><div className="field"><UserRound size={18} /><input value={displayName} onChange={(e) => setDisplayName(e.target.value)} maxLength={80} /></div></label>}
            {mode !== 'reset' && <label><span>{t('email')}</span><div className="field"><Mail size={18} /><input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" /></div></label>}
            {mode !== 'forgot' && <label><span>{t('password')}</span><div className="field"><LockKeyhole size={18} /><input type="password" aria-label={t('password')} required minLength={mode === 'login' ? 1 : 12} maxLength={128} value={password} onChange={(e) => setPassword(e.target.value)} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} /></div>{mode !== 'login' && <small>{t('passwordHint')}</small>}</label>}
            {(mode === 'register' || mode === 'reset') && <label><span>{t('passwordConfirm')}</span><div className="field"><LockKeyhole size={18} /><input type="password" aria-label={t('passwordConfirm')} required minLength={12} maxLength={128} value={passwordConfirm} onChange={(e) => setPasswordConfirm(e.target.value)} autoComplete="new-password" /></div></label>}
            {mode === 'register' && <label className="consent-field"><input type="checkbox" checked={termsAccepted} onChange={(e) => setTermsAccepted(e.target.checked)} required /><span>{t('acceptTerms')} <a href="/terms" target="_blank">{t('terms')}</a> · <a href="/privacy" target="_blank">{t('privacy')}</a></span></label>}
            {siteKey && <Turnstile siteKey={siteKey} onSuccess={setTurnstileToken} options={{ theme: 'dark' }} />}
            <button className="primary-button" disabled={busy} type="submit">{busy ? t('loading') : title}<ArrowRight size={18} /></button>
          </form>
          {mode === 'login' && <button className="text-button" type="button" onClick={() => setMode('forgot')}>{t('forgot')}</button>}
          {mode === 'login' && message && email && <button className="text-button" type="button" onClick={() => void api.resendVerification(email, turnstileToken).then(() => setMessage(t('registrationSent'))).catch((reason: Error) => setError(reason.message))}>{t('resendVerification')}</button>}
          {(mode === 'forgot' || mode === 'reset') && <button className="text-button" type="button" onClick={() => setMode('login')}>{t('login')}</button>}
          <p className="privacy-note">{t('providerNotice')}</p>
        </div>
      </motion.section>
    </main>
  )
}
