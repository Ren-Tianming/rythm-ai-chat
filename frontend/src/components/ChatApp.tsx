import { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { Bot, ChevronDown, LogOut, Menu, MessageSquarePlus, Send, Settings, Sparkles, Square, Trash2, UserRound, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api, streamChat } from '../api/client'
import type { ChatMessage, Conversation, ModelProfile, UsageSummary, User } from '../types'
import { Brand } from './Brand'
import { LanguagePicker } from './LanguagePicker'
import { SettingsModal } from './SettingsModal'

interface Props { user: User; onLogout: () => void; onUserChange: (user: User) => void }

const tempId = () => `temp-${crypto.randomUUID()}`

export function ChatApp({ user, onLogout, onUserChange }: Props) {
  const { t } = useTranslation()
  const [models, setModels] = useState<ModelProfile[]>([])
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [active, setActive] = useState<Conversation | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [selectedModel, setSelectedModel] = useState('')
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState('')
  const [usage, setUsage] = useState<UsageSummary | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const endRef = useRef<HTMLDivElement>(null)

  const loadConversations = async () => setConversations(await api.conversations())
  useEffect(() => {
    void Promise.all([api.models(), api.conversations(), api.usage()]).then(([modelList, chatList, summary]) => {
      setModels(modelList); setConversations(chatList); setUsage(summary)
      setSelectedModel(modelList.find((item) => item.is_default)?.id || modelList[0]?.id || '')
    }).catch((reason: Error) => setError(reason.message))
  }, [])
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  const activeModel = useMemo(() => models.find((item) => item.id === (active?.model_profile_id || selectedModel)), [models, active, selectedModel])

  const openConversation = async (conversation: Conversation) => {
    setActive(conversation); setSelectedModel(conversation.model_profile_id); setSidebarOpen(false); setError('')
    try { setMessages(await api.messages(conversation.id)) } catch (reason) { setError(reason instanceof Error ? reason.message : t('error')) }
  }

  const newConversation = () => { setActive(null); setMessages([]); setSidebarOpen(false); setError('') }

  const chooseModel = async (modelId: string) => {
    setSelectedModel(modelId)
    if (active) {
      try {
        const updated = await api.updateConversation(active.id, { model_profile_id: modelId })
        setActive(updated); setConversations((list) => list.map((item) => item.id === updated.id ? updated : item))
      } catch (reason) { setError(reason instanceof Error ? reason.message : t('error')) }
    }
  }

  const deleteConversation = async (conversation: Conversation) => {
    if (!window.confirm(t('deleteConfirm'))) return
    await api.deleteConversation(conversation.id)
    setConversations((list) => list.filter((item) => item.id !== conversation.id))
    if (active?.id === conversation.id) newConversation()
  }

  const submit = async (event?: FormEvent) => {
    event?.preventDefault()
    const content = input.trim()
    if (!content || streaming || !selectedModel) return
    setInput(''); setError(''); setStreaming(true)
    let conversation = active
    try {
      if (!conversation) {
        conversation = await api.createConversation(selectedModel)
        setActive(conversation); setConversations((list) => [conversation!, ...list])
      }
      const userMessage: ChatMessage = { id: tempId(), sequence_no: messages.length + 1, role: 'user', content, status: 'completed', model_profile_id: null, input_tokens: null, output_tokens: null, created_at: new Date().toISOString() }
      const assistantId = tempId()
      const assistantMessage: ChatMessage = { ...userMessage, id: assistantId, sequence_no: userMessage.sequence_no + 1, role: 'assistant', content: '', status: 'streaming', model_profile_id: selectedModel }
      setMessages((list) => [...list, userMessage, assistantMessage])
      const controller = new AbortController(); abortRef.current = controller
      let streamError = ''
      await streamChat(conversation.id, content, controller.signal, {
        onDelta: (text) => setMessages((list) => list.map((item) => item.id === assistantId ? { ...item, content: item.content + text } : item)),
        onError: (message) => { streamError = message },
      })
      if (streamError) throw new Error(streamError)
      setMessages(await api.messages(conversation.id))
      await Promise.all([loadConversations(), api.usage().then(setUsage)])
    } catch (reason) {
      if (!(reason instanceof DOMException && reason.name === 'AbortError')) setError(reason instanceof Error ? reason.message : t('error'))
      if (conversation) void api.messages(conversation.id).then(setMessages)
    } finally { setStreaming(false); abortRef.current = null }
  }

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void submit() }
  }

  const logout = async () => { try { await api.logout() } finally { onLogout() } }

  return <div className="chat-layout">
    <aside className={`sidebar ${sidebarOpen ? 'sidebar--open' : ''}`}>
      <div className="sidebar__top"><Brand compact /><button className="icon-button mobile-only" onClick={() => setSidebarOpen(false)}><X /></button></div>
      <button className="new-chat" onClick={newConversation}><MessageSquarePlus size={19} /><span>{t('newChat')}</span><kbd>⌘ K</kbd></button>
      <div className="sidebar__label">{t('conversations')}<span>{conversations.length}</span></div>
      <nav className="conversation-list">{conversations.length === 0 && <p>{t('noConversations')}</p>}{conversations.map((conversation) => (
        <div className={`conversation-item ${active?.id === conversation.id ? 'active' : ''}`} key={conversation.id}>
          <button onClick={() => void openConversation(conversation)}><span className="conversation-dot" /><span>{conversation.title}</span></button>
          <button className="conversation-delete" title={t('delete')} onClick={() => void deleteConversation(conversation)}><Trash2 size={15} /></button>
        </div>
      ))}</nav>
      <div className="usage-card"><div><span>{t('usage')}</span><strong>{usage?.requests_today || 0}<small>/{usage?.daily_limit || 50}</small></strong></div><div className="usage-bar"><i style={{ width: `${Math.min(100, ((usage?.requests_today || 0) / (usage?.daily_limit || 50)) * 100)}%` }} /></div><small>{((usage?.input_tokens || 0) + (usage?.output_tokens || 0)).toLocaleString()} {t('tokens')}</small></div>
      <div className="profile-menu"><div className="avatar">{(user.display_name || user.email).slice(0, 1).toUpperCase()}</div><div><strong>{user.display_name || user.email.split('@')[0]}</strong><small>{user.email}</small></div><button className="icon-button" title={t('settings')} onClick={() => setSettingsOpen(true)}><Settings size={18} /></button><button className="icon-button" title={t('logout')} onClick={() => void logout()}><LogOut size={18} /></button></div>
    </aside>
    {sidebarOpen && <button className="sidebar-scrim" onClick={() => setSidebarOpen(false)} />}
    <main className="chat-main">
      <header className="chat-header"><button className="icon-button mobile-only" onClick={() => setSidebarOpen(true)}><Menu /></button><div className="model-select"><span><Sparkles size={15} />{t('model')}</span><select value={active?.model_profile_id || selectedModel} onChange={(e) => void chooseModel(e.target.value)}>{models.map((model) => <option value={model.id} key={model.id}>{model.display_name}</option>)}</select><ChevronDown size={16} /></div><div className="header-actions"><span className="secure-indicator"><i /> Context · 5</span><LanguagePicker onChange={(locale) => onUserChange({ ...user, locale })} /></div></header>
      <section className="messages"><div className="messages__inner">{messages.length === 0 ? (
        <motion.div className="empty-chat" initial={{ opacity: 0, scale: .98 }} animate={{ opacity: 1, scale: 1 }}><div className="empty-chat__logo"><img src="/rythm-logo.png" alt="" /></div><h1>{t('welcome')}</h1><p>{t('welcomeHint')}</p><div className="model-cards">{models.map((model) => <button key={model.id} className={selectedModel === model.id ? 'active' : ''} onClick={() => void chooseModel(model.id)}><span>{model.provider.slice(0, 1).toUpperCase()}</span><div><strong>{model.display_name}</strong><small>{t(model.description_key)}</small></div></button>)}</div></motion.div>
      ) : messages.map((message) => (
        <motion.article className={`message message--${message.role}`} key={message.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}><div className="message__avatar">{message.role === 'assistant' ? <Bot size={20} /> : <UserRound size={20} />}</div><div className="message__body"><header><strong>{message.role === 'assistant' ? 'RyThM' : (user.display_name || 'You')}</strong>{message.role === 'assistant' && <span>{models.find((m) => m.id === message.model_profile_id)?.display_name || activeModel?.display_name}</span>}</header><div className="markdown"><ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content || (streaming ? '● ● ●' : '')}</ReactMarkdown></div>{message.output_tokens !== null && <small className="token-meta">{message.output_tokens} output tokens</small>}</div></motion.article>
      ))}<div ref={endRef} />{error && <div className="notice notice--error chat-error">{error}</div>}</div></section>
      <footer className="composer-wrap"><form className="composer" onSubmit={(e) => void submit(e)}><textarea value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={onKeyDown} placeholder={t('placeholder')} maxLength={4000} rows={1} disabled={streaming} /><div className="composer__bottom"><span>{input.length}/4000 · {activeModel?.display_name}</span>{streaming ? <button type="button" className="send-button stop" onClick={() => abortRef.current?.abort()} title={t('stop')}><Square size={17} /></button> : <button className="send-button" disabled={!input.trim() || !selectedModel} title={t('send')}><Send size={18} /></button>}</div></form><p>{t('providerNotice')}</p></footer>
    </main>
    <SettingsModal open={settingsOpen} user={user} onClose={() => setSettingsOpen(false)} onUserChange={onUserChange} />
  </div>
}
