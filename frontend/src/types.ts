export type Locale = 'zh-CN' | 'ja-JP' | 'en-US'

export interface User {
  id: string
  email: string
  display_name: string | null
  locale: Locale
  role: string
  email_verified: boolean
}

export interface ModelProfile {
  id: string
  slug: string
  provider: string
  display_name: string
  description_key: string
  is_default: boolean
  max_output_tokens: number
}

export interface Conversation {
  id: string
  title: string
  model_profile_id: string
  archived: boolean
  created_at: string
  updated_at: string
}

export interface ChatMessage {
  id: string
  sequence_no: number
  role: 'user' | 'assistant'
  content: string
  status: string
  model_profile_id: string | null
  input_tokens: number | null
  output_tokens: number | null
  created_at: string
}

export interface UsageSummary {
  requests_today: number
  daily_limit: number
  input_tokens: number
  output_tokens: number
  estimated_cost_microusd: number
}

export interface UserSession {
  id: string
  user_agent: string | null
  ip_address: string | null
  last_seen_at: string
  created_at: string
  current: boolean
}
