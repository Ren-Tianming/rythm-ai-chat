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
      <select value={i18n.resolvedLanguage || 'en-US'} onChange={(event) => change(event.target.value as Locale)}>
        <option value="zh-CN">中文</option>
        <option value="ja-JP">日本語</option>
        <option value="en-US">English</option>
      </select>
    </label>
  )
}
