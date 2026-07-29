import { useTranslation } from 'react-i18next'
import { Brand } from './Brand'
import { LanguagePicker } from './LanguagePicker'


export function LegalPage({ kind }: { kind: 'privacy' | 'terms' }) {
  const { t } = useTranslation()
  return (
    <main className="legal-page">
      <header><Brand compact /><LanguagePicker /></header>
      <article>
        <h1>{t(kind === 'privacy' ? 'privacyTitle' : 'termsTitle')}</h1>
        <p>{t(kind === 'privacy' ? 'privacyBody' : 'termsBody')}</p>
        <p><strong>{kind === 'privacy' ? 'Version' : 'Version'}:</strong> 2026-07-29</p>
        <a href="/">{t('legalBack')}</a>
      </article>
    </main>
  )
}
