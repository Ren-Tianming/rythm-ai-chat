import { Languages } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { Locale } from '../types'

export function LanguagePicker({ onChange }: { onChange?: (locale: Locale) => void }) {
  const { i18n } = useTranslation()
  const change = (locale: Locale) => {
    void i18n.changeLanguage(locale)
    localStorage.setItem('rythm_locale', locale)
    onChange?.(locale)
  }
  return (
    <label className="language-picker" aria-label="Language">
      <Languages size={16} />
      <select value={i18n.resolvedLanguage?.slice(0, 2) || 'en'} onChange={(event) => change(event.target.value as Locale)}>
        <option value="zh">中文</option>
        <option value="ja">日本語</option>
        <option value="en">English</option>
      </select>
    </label>
  )
}
