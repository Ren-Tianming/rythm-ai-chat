import { motion } from 'framer-motion'

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`brand ${compact ? 'brand--compact' : ''}`}>
      <motion.img
        src="/rythm-logo.png"
        alt="RyThM Chatbot"
        className="brand__logo"
        animate={{ filter: ['drop-shadow(0 0 8px #8b5cf666)', 'drop-shadow(0 0 18px #d946efaa)', 'drop-shadow(0 0 8px #8b5cf666)'] }}
        transition={{ repeat: Infinity, duration: 4, ease: 'easeInOut' }}
      />
      <div className="brand__text">
        <strong>RyThM <span>Chatbot</span></strong>
        {!compact && <small>天铭聊天机器人 · 天銘チャットボット</small>}
      </div>
    </div>
  )
}
