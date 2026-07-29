import { describe, expect, it } from 'vitest'
import { resources } from './i18n'

function keys(value: object, prefix = ''): string[] {
  return Object.entries(value).flatMap(([key, item]) => {
    const path = prefix ? `${prefix}.${key}` : key
    return typeof item === 'object' && item !== null ? keys(item, path) : [path]
  }).sort()
}

describe('translations', () => {
  it('has the same keys for Chinese, Japanese, and English', () => {
    const chinese = keys(resources['zh-CN'].translation)
    expect(keys(resources['ja-JP'].translation)).toEqual(chinese)
    expect(keys(resources['en-US'].translation)).toEqual(chinese)
  })
})
