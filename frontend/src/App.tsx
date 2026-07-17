import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from './api/client'
import { AuthPage } from './components/AuthPage'
import { ChatApp } from './components/ChatApp'
import type { User } from './types'

export default function App() {
  const { t, i18n } = useTranslation()
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [notice, setNotice] = useState('')
  const initialized = useRef(false)
  const params = new URLSearchParams(window.location.search)
  const resetToken = params.get('reset') || undefined

  useEffect(() => {
    if (initialized.current) return
    initialized.current = true
    const verify = params.get('verify')
    const initialize = async () => {
      if (verify) {
        try { await api.verify(verify); setNotice(t('verified')); window.history.replaceState({}, '', '/') }
        catch (reason) { setNotice(reason instanceof Error ? reason.message : t('error')) }
      }
      try {
        const current = await api.me(); setUser(current); await i18n.changeLanguage(current.locale)
      } catch { setUser(null) }
      finally { setLoading(false) }
    }
    void initialize()
    // URL tokens are intentionally read only on first mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (loading) return <div className="app-loader"><img src="/rythm-logo.png" alt="RyThM" /><span>RyThM Chatbot</span></div>
  if (!user) return <AuthPage onAuthenticated={setUser} initialMode={resetToken ? 'reset' : 'login'} resetToken={resetToken} notice={notice} />
  return <ChatApp user={user} onLogout={() => setUser(null)} onUserChange={setUser} />
}
