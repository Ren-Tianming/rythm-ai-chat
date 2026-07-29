import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from './api/client'
import { AuthPage } from './components/AuthPage'
import { ChatApp } from './components/ChatApp'
import { LegalPage } from './components/LegalPage'
import type { User } from './types'

function accountActionTokens(): { verify?: string; reset?: string } {
  const query = new URLSearchParams(window.location.search)
  const fragment = new URLSearchParams(window.location.hash.replace(/^#/, ''))
  return {
    verify: fragment.get('verify') || query.get('verify') || undefined,
    reset: fragment.get('reset') || query.get('reset') || undefined,
  }
}

function clearAccountActionTokens() {
  const url = new URL(window.location.href)
  url.searchParams.delete('verify')
  url.searchParams.delete('reset')
  url.hash = ''
  window.history.replaceState({}, '', `${url.pathname}${url.search}`)
}

export default function App() {
  const { t, i18n } = useTranslation()
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [notice, setNotice] = useState('')
  const initialized = useRef(false)
  const actionTokens = useRef(accountActionTokens())
  const resetToken = actionTokens.current.reset
  const legalRoute = window.location.pathname === '/privacy' ? 'privacy' : window.location.pathname === '/terms' ? 'terms' : null

  useEffect(() => {
    if (initialized.current) return
    initialized.current = true
    const verify = actionTokens.current.verify
    if (verify || resetToken) clearAccountActionTokens()
    const initialize = async () => {
      if (verify) {
        try { await api.verify(verify); setNotice(t('verified')) }
        catch (reason) { setNotice(reason instanceof Error ? reason.message : t('error')) }
      }
      try {
        const current = await api.me(); setUser(current); await i18n.changeLanguage(current.locale)
      } catch { setUser(null) }
      finally { setLoading(false) }
    }
    void initialize()
    // One-time tokens are kept only in memory after the first mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (legalRoute) return <LegalPage kind={legalRoute} />
  if (loading) return <div className="app-loader"><img src="/rythm-logo.png" alt="RyThM" /><span>RyThM Chatbot</span></div>
  if (!user) return <AuthPage onAuthenticated={setUser} initialMode={resetToken ? 'reset' : 'login'} resetToken={resetToken} notice={notice} />
  return <ChatApp user={user} onLogout={() => setUser(null)} onUserChange={setUser} />
}
