import type { ChatMessage, Conversation, ModelProfile, UsageSummary, User, UserSession } from '../types'

const API = '/api/v1'

function cookie(name: string): string {
  const match = document.cookie.split('; ').find((item) => item.startsWith(`${name}=`))
  return match ? decodeURIComponent(match.split('=').slice(1).join('=')) : ''
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method || 'GET').toUpperCase()
  const headers = new Headers(init.headers)
  if (init.body) headers.set('Content-Type', 'application/json')
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const csrf = cookie('rythm_csrf')
    if (csrf) headers.set('X-CSRF-Token', csrf)
  }
  const response = await fetch(`${API}${path}`, { ...init, headers, credentials: 'include' })
  if (!response.ok) {
    let message = response.statusText
    try {
      const data = await response.json()
      message = data.detail || data.message || message
    } catch {
      // Keep HTTP status text.
    }
    throw new ApiError(response.status, message)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const api = {
  me: () => request<User>('/auth/me'),
  login: (email: string, password: string, turnstileToken?: string) =>
    request<{ user: User; csrf_token: string }>('/auth/login', {
      method: 'POST', body: JSON.stringify({ email, password, turnstile_token: turnstileToken || null }),
    }),
  register: (data: { email: string; password: string; display_name?: string; locale: string; turnstile_token?: string }) =>
    request<{ message: string }>('/auth/register', { method: 'POST', body: JSON.stringify(data) }),
  forgot: (email: string, turnstileToken?: string) =>
    request<{ message: string }>('/auth/forgot-password', {
      method: 'POST', body: JSON.stringify({ email, turnstile_token: turnstileToken || null }),
    }),
  reset: (token: string, password: string) =>
    request<{ message: string }>('/auth/reset-password', { method: 'POST', body: JSON.stringify({ token, password }) }),
  verify: (token: string) =>
    request<{ message: string }>('/auth/verify-email', { method: 'POST', body: JSON.stringify({ token }) }),
  logout: () => request<{ message: string }>('/auth/logout', { method: 'POST' }),
  models: () => request<ModelProfile[]>('/model-profiles'),
  conversations: () => request<Conversation[]>('/conversations'),
  createConversation: (model_profile_id: string) =>
    request<Conversation>('/conversations', { method: 'POST', body: JSON.stringify({ model_profile_id }) }),
  updateConversation: (id: string, data: Partial<Pick<Conversation, 'title' | 'model_profile_id' | 'archived'>>) =>
    request<Conversation>(`/conversations/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteConversation: (id: string) => request(`/conversations/${id}`, { method: 'DELETE' }),
  messages: (id: string) => request<ChatMessage[]>(`/conversations/${id}/messages`),
  usage: () => request<UsageSummary>('/usage/me'),
  sessions: () => request<UserSession[]>('/auth/sessions'),
  revokeSession: (id: string) => request(`/auth/sessions/${id}`, { method: 'DELETE' }),
  updateMe: (data: { display_name?: string | null; locale?: string }) =>
    request<User>('/users/me', { method: 'PATCH', body: JSON.stringify(data) }),
}

export interface StreamHandlers {
  onMetadata?: (data: Record<string, unknown>) => void
  onDelta: (text: string) => void
  onDone?: (data: Record<string, unknown>) => void
  onError?: (message: string) => void
}

export async function streamChat(
  conversationId: string,
  content: string,
  signal: AbortSignal,
  handlers: StreamHandlers,
): Promise<void> {
  const response = await fetch(`${API}/conversations/${conversationId}/messages/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': cookie('rythm_csrf') },
    credentials: 'include',
    body: JSON.stringify({ content }),
    signal,
  })
  if (!response.ok || !response.body) {
    let message = response.statusText
    try { message = (await response.json()).detail || message } catch { /* noop */ }
    throw new ApiError(response.status, message)
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
    const frames = buffer.split('\n\n')
    buffer = frames.pop() || ''
    for (const frame of frames) {
      let event = 'message'
      let data = '{}'
      for (const line of frame.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        if (line.startsWith('data:')) data = line.slice(5).trim()
      }
      const parsed = JSON.parse(data) as Record<string, unknown>
      if (event === 'delta') handlers.onDelta(String(parsed.text || ''))
      else if (event === 'metadata') handlers.onMetadata?.(parsed)
      else if (event === 'done') handlers.onDone?.(parsed)
      else if (event === 'error') handlers.onError?.(String(parsed.message || 'Generation failed'))
    }
  }
}
