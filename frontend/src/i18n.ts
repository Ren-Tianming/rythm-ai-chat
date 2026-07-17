import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

export const resources = {
  zh: { translation: {
    brandSubtitle: '天铭聊天机器人', login: '登录', register: '注册', forgot: '找回密码', reset: '重置密码',
    email: '邮箱', password: '密码', displayName: '显示名称', send: '发送', stop: '停止',
    verifyHint: '注册后请打开验证邮件完成激活。', passwordHint: '至少12个字符',
    newChat: '新建对话', conversations: '历史对话', noConversations: '还没有对话',
    welcome: '今天想聊些什么？', welcomeHint: '选择模型开始对话。系统仅发送最近5轮历史内容。',
    placeholder: '输入消息…', model: '模型', settings: '设置', logout: '退出登录',
    account: '账户', sessions: '登录设备', current: '当前设备', revoke: '退出此设备', close: '关闭',
    usage: '今日用量', requests: '次请求', tokens: 'Token', save: '保存', delete: '删除',
    deleteConfirm: '确定删除这个对话吗？', loading: '加载中…', retry: '重试',
    registrationSent: '验证邮件已发送，请检查邮箱。', resetSent: '如果账户存在，重置邮件已发送。',
    verified: '邮箱验证成功，请登录。', resetDone: '密码已重置，请使用新密码登录。',
    error: '操作失败', providerNotice: '消息会发送到你选择的第三方模型服务。请勿输入机密信息。',
    models: { deepseek: '高性价比综合模型', gemini: '多语言轻量模型', groq: '极速开源模型推理' },
  }},
  ja: { translation: {
    brandSubtitle: '天銘チャットボット', login: 'ログイン', register: '登録', forgot: 'パスワード再設定', reset: 'パスワードを変更',
    email: 'メールアドレス', password: 'パスワード', displayName: '表示名', send: '送信', stop: '停止',
    verifyHint: '登録後、確認メールからアカウントを有効化してください。', passwordHint: '12文字以上',
    newChat: '新しいチャット', conversations: '会話履歴', noConversations: '会話はまだありません',
    welcome: '今日は何を話しましょう？', welcomeHint: 'モデルを選択して会話を開始します。直近5往復のみ送信されます。',
    placeholder: 'メッセージを入力…', model: 'モデル', settings: '設定', logout: 'ログアウト',
    account: 'アカウント', sessions: 'ログイン端末', current: '現在の端末', revoke: 'この端末をログアウト', close: '閉じる',
    usage: '本日の利用量', requests: 'リクエスト', tokens: 'Token', save: '保存', delete: '削除',
    deleteConfirm: 'この会話を削除しますか？', loading: '読み込み中…', retry: '再試行',
    registrationSent: '確認メールを送信しました。', resetSent: 'アカウントが存在する場合、再設定メールを送信しました。',
    verified: 'メール確認が完了しました。ログインしてください。', resetDone: 'パスワードを変更しました。',
    error: '処理に失敗しました', providerNotice: 'メッセージは選択した外部AIサービスへ送信されます。機密情報は入力しないでください。',
    models: { deepseek: 'コスト性能に優れた汎用モデル', gemini: '多言語対応の軽量モデル', groq: '高速なオープンモデル推論' },
  }},
  en: { translation: {
    brandSubtitle: 'Tianming Chatbot', login: 'Sign in', register: 'Create account', forgot: 'Forgot password', reset: 'Reset password',
    email: 'Email', password: 'Password', displayName: 'Display name', send: 'Send', stop: 'Stop',
    verifyHint: 'Open the verification email after registration to activate your account.', passwordHint: 'At least 12 characters',
    newChat: 'New chat', conversations: 'Conversations', noConversations: 'No conversations yet',
    welcome: 'What would you like to explore?', welcomeHint: 'Choose a model and start chatting. Only the latest 5 rounds are sent.',
    placeholder: 'Type a message…', model: 'Model', settings: 'Settings', logout: 'Sign out',
    account: 'Account', sessions: 'Signed-in devices', current: 'Current device', revoke: 'Sign out device', close: 'Close',
    usage: 'Today’s usage', requests: 'requests', tokens: 'tokens', save: 'Save', delete: 'Delete',
    deleteConfirm: 'Delete this conversation?', loading: 'Loading…', retry: 'Retry',
    registrationSent: 'Verification email sent. Check your inbox.', resetSent: 'If the account exists, a reset email was sent.',
    verified: 'Email verified. You can now sign in.', resetDone: 'Password reset. Sign in with your new password.',
    error: 'Something went wrong', providerNotice: 'Messages are sent to the selected third-party AI provider. Do not enter confidential information.',
    models: { deepseek: 'Balanced quality at low cost', gemini: 'Lightweight multilingual model', groq: 'Ultra-fast open model inference' },
  }},
} as const

void i18n.use(initReactI18next).init({
  resources,
  lng: localStorage.getItem('rythm_locale') || navigator.language.slice(0, 2),
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
})

export default i18n
