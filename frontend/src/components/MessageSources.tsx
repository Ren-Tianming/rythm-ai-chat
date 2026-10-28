import { useTranslation } from 'react-i18next'
import type { MessageSource } from '../types'

export function MessageSources({ sources }: { sources: MessageSource[] }) {
  const { t } = useTranslation()
  if (!sources.length) return null
  return <section className="message-sources" aria-label={t('sources')}><strong>{t('sources')}</strong><small>{t('sourceHint')}</small>
    {sources.map(source => <details key={source.id || source.label}><summary>[{source.label}] {source.filename}{source.page_number ? ` · ${t('page', { page: source.page_number })}` : ''}{source.source_kind === 'vision' ? ` · ${t('visualSource')}` : ''}</summary>
      <blockquote>{source.source_kind === 'vision' ? t('visualSource') : source.excerpt}</blockquote><a href={`/api/v1/documents/${source.document_id}/content`} target="_blank" rel="noopener noreferrer">{t('download')}</a>
    </details>)}
  </section>
}
