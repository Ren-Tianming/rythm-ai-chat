import { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { Archive, Bot, ChevronDown, Edit3, LogOut, Menu, MessageSquarePlus, Search, Send, Settings, Sparkles, Square, Trash2, UserRound, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api, streamChat } from '../api/client'
import type { ChatMessage, Conversation, ModelProfile, UsageSummary, User } from '../types'
import { Brand } from './Brand'
import { LanguagePicker } from './LanguagePicker'
import { SettingsModal } from './SettingsModal'
import { DocumentPanel } from './DocumentPanel'
import { MessageSources } from './MessageSources'

interface Props { user: User; onLogout: () => void; onUserChange: (user: User) => void }

const tempId = () => `temp-${crypto.randomUUID()}`

export function ChatApp({ user, onLogout, onUserChange }: Props) {
  const { t } = useTranslation()
  const [models, setModels] = useState<ModelProfile[]>([])
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [active, setActive] = useState<Conversation | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [selectedModel, setSelectedModel] = useState('')
  const [selectedDocuments, setSelectedDocuments] = useState<string[]>([])
  const [documentsBusy, setDocumentsBusy] = useState(false)
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState('')
  const [usage, setUsage] = useState<UsageSummary | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [archivedView, setArchivedView] = useState(false)
  const [search, setSearch] = useState('')
  const abortRef = useRef<AbortController | null>(null)
  const generationIdRef = useRef<string | null>(null)
  const endRef = useRef<HTMLDivElement>(null)

  const loadConversations = async () => setConversations(await api.conversations(archivedView))
  useEffect(() => {
    void Promise.all([api.models(), api.conversations(false), api.usage()]).then(([modelList, chatList, summary]) => {
      setModels(modelList); setConversations(chatList); setUsage(summary)
      setSelectedModel(modelList.find((item) => item.is_default)?.id || modelList[0]?.id || '')
    }).catch((reason: Error) => setError(reason.message))
  }, [])
  useEffect(() => { void api.conversations(archivedView).then(setConversations).catch((reason: Error) => setError(reason.message)) }, [archivedView])
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  const activeModel = useMemo(() => models.find((item) => item.id === (active?.model_profile_id || selectedModel)), [models, active, selectedModel])

  const openConversation = async (conversation: Conversation) => {
    if (streaming || documentsBusy) return
    setSelectedDocuments([]); setActive(conversation); setSelectedModel(conversation.model_profile_id); setSidebarOpen(false); setError('')
    try { setMessages(await api.messages(conversation.id)) } catch (reason) { setError(reason instanceof Error ? reason.message : t('error')) }
  }

  const newConversation = () => { if (streaming || documentsBusy) return; setSelectedDocuments([]); setActive(null); setMessages([]); setSidebarOpen(false); setError('') }

  const chooseModel = async (modelId: string) => {
    if (streaming) return
    setSelectedModel(modelId)
    if (active) {
      try {
        const updated = await api.updateConversation(active.id, { model_profile_id: modelId })
        setActive(updated); setConversations((list) => list.map((item) => item.id === updated.id ? updated : item))
      } catch (reason) { setError(reason instanceof Error ? reason.message : t('error')) }
    }
  }

  const deleteConversation = async (conversation: Conversation) => {
    if (streaming || documentsBusy) return
    if (!window.confirm(t('deleteConfirm'))) return
    await api.deleteConversation(conversation.id)
    setConversations((list) => list.filter((item) => item.id !== conversation.id))
    if (active?.id === conversation.id) newConversation()
  }

  const archiveConversation = async (conversation: Conversation) => {
    if (streaming || documentsBusy) return
    await api.updateConversation(conversation.id, { archived: !conversation.archived })
    setConversations((list) => list.filter((item) => item.id !== conversation.id))
    if (active?.id === conversation.id) newConversation()
  }

  const renameConversation = async (conversation: Conversation) => {
    const title = window.prompt(t('rename'), conversation.title)?.trim()
    if (!title) return
    const updated = await api.updateConversation(conversation.id, { title })
    setConversations((list) => list.map((item) => item.id === updated.id ? updated : item))
    if (active?.id === updated.id) setActive(updated)
  }

  const ensureConversation = async () => {
    if (active) return active.id
    const conversation = await api.createConversation(selectedModel)
    setActive(conversation); setConversations(list => [conversation, ...list])
    return conversation.id
  }

  const submit = async (event?: FormEvent, continuation?: ChatMessage) => {
    event?.preventDefault()
    const content = continuation ? t('continuePrompt') : input.trim()
    if (!content || streaming || documentsBusy || !selectedModel) return
    if (!continuation) setInput(''); setError(''); setStreaming(true)
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
      const clientRequestId = crypto.randomUUID()
      let streamError = ''
      await streamChat(conversation.id, content, clientRequestId, selectedModel, controller.signal, {
        onMetadata: (data) => {
          generationIdRef.current = String(data.generation_id || '') || null
          setMessages(list => list.map(item => item.id === assistantId ? { ...item, sources: (data.sources || []) as ChatMessage['sources'] } : item))
        },
        onDelta: (text) => setMessages((list) => list.map((item) => item.id === assistantId ? { ...item, content: item.content + text } : item)),
        onError: (message) => { streamError = message },
      }, continuation ? [...new Set(continuation.sources?.map(source => source.document_id) || [])] : selectedDocuments, continuation?.id)
      if (streamError) throw new Error(streamError)
      setMessages(await api.messages(conversation.id))
      await Promise.all([loadConversations(), api.usage().then(setUsage)])
    } catch (reason) {
      if (!(reason instanceof DOMException && reason.name === 'AbortError')) setError(reason instanceof Error ? reason.message : t('error'))
      if (conversation) await api.messages(conversation.id).then(setMessages).catch(() => {})
    } finally { setStreaming(false); abortRef.current = null; generationIdRef.current = null }
  }

  const stopGeneration = async () => {
    const generationId = generationIdRef.current
    if (generationId) {
      try { await api.cancelGeneration(generationId); return } catch { /* Disconnect still cancels. */ }
    }
    abortRef.current?.abort()
  }

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void submit() }
  }

  const logout = async () => { try { await api.logout() } finally { onLogout() } }

  return <div className="chat-layout">
    <aside className={`sidebar ${sidebarOpen ? 'sidebar--open' : ''}`}>
      <div className="sidebar__top"><Brand compact /><button className="icon-button mobile-only" onClick={() => setSidebarOpen(false)}><X /></button></div>
      <button className="new-chat" onClick={newConversation}><MessageSquarePlus size={19} /><span>{t('newChat')}</span><kbd>⌘ K</kbd></button>
      <div className="conversation-tools"><label><Search size={14} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t('searchConversations')} /></label><button className={archivedView ? 'active' : ''} onClick={() => setArchivedView((value) => !value)}><Archive size={15} />{t(archivedView ? 'activeChats' : 'archived')}</button></div>
      <div className="sidebar__label">{t('conversations')}<span>{conversations.length}</span></div>
      <nav className="conversation-list">{conversations.length === 0 && <p>{t('noConversations')}</p>}{conversations.filter((conversation) => conversation.title.toLocaleLowerCase().includes(search.toLocaleLowerCase())).map((conversation) => (
        <div className={`conversation-item ${active?.id === conversation.id ? 'active' : ''}`} key={conversation.id}>
          <button onClick={() => void openConversation(conversation)}><span className="conversation-dot" /><span>{conversation.title}</span></button>
          <button className="conversation-action" title={t('rename')} onClick={() => void renameConversation(conversation)}><Edit3 size={14} /></button>
          <button className="conversation-action" title={t(conversation.archived ? 'restore' : 'archive')} onClick={() => void archiveConversation(conversation)}><Archive size={14} /></button>
          <button className="conversation-delete" title={t('delete')} onClick={() => void deleteConversation(conversation)}><Trash2 size={15} /></button>
        </div>
      ))}</nav>
      <div className="usage-card"><div><span>{t('usage')}</span><strong>{usage?.requests_today || 0}<small>/{usage?.daily_limit || 50}</small></strong></div><div className="usage-bar"><i style={{ width: `${Math.min(100, ((usage?.requests_today || 0) / (usage?.daily_limit || 50)) * 100)}%` }} /></div><small>{((usage?.input_tokens || 0) + (usage?.output_tokens || 0)).toLocaleString()} {t('tokens')}</small></div>
      <div className="profile-menu"><div className="avatar">{(user.display_name || user.email).slice(0, 1).toUpperCase()}</div><div><strong>{user.display_name || user.email.split('@')[0]}</strong><small>{user.email}</small></div><button className="icon-button" title={t('settings')} onClick={() => setSettingsOpen(true)}><Settings size={18} /></button><button className="icon-button" title={t('logout')} onClick={() => void logout()}><LogOut size={18} /></button></div>
    </aside>
    {sidebarOpen && <button className="sidebar-scrim" onClick={() => setSidebarOpen(false)} />}
    <main className="chat-main">
      <header className="chat-header"><button className="icon-button mobile-only" onClick={() => setSidebarOpen(true)}><Menu /></button><div className="chat-title">{active?.title}</div><div className="model-select"><span><Sparkles size={15} />{t('model')}</span><select disabled={streaming || documentsBusy} value={active?.model_profile_id || selectedModel} onChange={(e) => void chooseModel(e.target.value)}>{models.map((model) => <option value={model.id} key={model.id}>{model.display_name}</option>)}</select><ChevronDown size={16} /></div><div className="header-actions"><span className="secure-indicator"><i /> {t('contextLabel')}</span><LanguagePicker onChange={(locale) => void api.updateMe({ locale }).then(onUserChange).catch(() => onUserChange({ ...user, locale }))} /></div></header>
      <section className="messages"><div className="messages__inner">{messages.length === 0 ? (
        <motion.div className="empty-chat" initial={{ opacity: 0, scale: .98 }} animate={{ opacity: 1, scale: 1 }}><div className="empty-chat__logo"><img src="/rythm-logo.png" alt="" /></div><h1>{t('welcome')}</h1><p>{t('welcomeHint')}</p><div className="example-prompts">{['example1', 'example2', 'example3'].map((key) => <button key={key} onClick={() => setInput(t(key))}>{t(key)}</button>)}</div><div className="model-cards">{models.map((model) => <button key={model.id} className={selectedModel === model.id ? 'active' : ''} onClick={() => void chooseModel(model.id)}><span>{model.provider.slice(0, 1).toUpperCase()}</span><div><strong>{model.display_name}</strong><small>{t(model.description_key)}</small></div></button>)}</div></motion.div>
      ) : messages.map((message) => (
        <motion.article className={`message message--${message.role}`} key={message.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}><div className="message__avatar">{message.role === 'assistant' ? <Bot size={20} /> : <UserRound size={20} />}</div><div className="message__body"><header><strong>{message.role === 'assistant' ? 'RyThM' : (user.display_name || t('you'))}</strong>{message.role === 'assistant' && <span>{models.find((m) => m.id === message.model_profile_id)?.display_name || activeModel?.display_name}</span>}</header><div className="markdown"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: (props) => <a {...props} rel="noopener noreferrer" target="_blank" /> }}>{message.content || (streaming ? '● ● ●' : '')}</ReactMarkdown></div>{message.sources && <MessageSources sources={message.sources} />}
          {['length', 'MAX_TOKENS', 'max_tokens'].includes(message.finish_reason || '') && <p className="generation-notice">{t('outputTruncated')}</p>}
          {message.status === 'cancelled' && <p className="generation-notice">{t('generationStopped')}</p>}
          {message.role === 'assistant' && message.id === messages.at(-1)?.id && message.content && (['length', 'MAX_TOKENS', 'max_tokens'].includes(message.finish_reason || '') || ['cancelled', 'failed'].includes(message.status)) && <button className="continue-button" disabled={streaming || documentsBusy} onClick={() => void submit(undefined, message)}>{t('continueGeneration')}</button>}
          {message.output_tokens !== null && <small className="token-meta">{message.output_tokens} {t('outputTokens')}</small>}</div></motion.article>
      ))}<div ref={endRef} />{error && <div className="notice notice--error chat-error">{error}</div>}</div></section>
      <footer className="composer-wrap"><DocumentPanel conversationId={active?.id} ensureConversation={ensureConversation} selected={selectedDocuments} onSelected={setSelectedDocuments} disabled={streaming || !selectedModel} vision={!!activeModel?.supports_vision} onError={setError} onBusy={setDocumentsBusy}
        onDocumentRemoved={id => setMessages(list => list.map(message => ({ ...message, sources: message.sources?.filter(source => source.document_id !== id) })))}><form className="composer" onSubmit={(e) => void submit(e)}><textarea value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={onKeyDown} placeholder={t('placeholder')} maxLength={4000} rows={1} disabled={streaming} /><div className="composer__bottom"><span>{input.length}/4000 · {activeModel?.display_name}</span>{streaming ? <button type="button" className="send-button stop" onClick={() => void stopGeneration()} title={t('stop')}><Square size={17} /></button> : <button className="send-button" disabled={!input.trim() || !selectedModel || documentsBusy} title={t('send')}><Send size={18} /></button>}</div></form></DocumentPanel><p>{t('providerNotice')}</p></footer>
    </main>
    <SettingsModal open={settingsOpen} user={user} onClose={() => setSettingsOpen(false)} onUserChange={onUserChange} />
  </div>
}
