import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

export const resources = {
  'zh-CN': { translation: {
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
    passwordConfirm: '确认密码', acceptTerms: '我同意', terms: '服务条款', privacy: '隐私政策',
    resendVerification: '重新发送验证邮件', searchConversations: '搜索对话', archived: '已归档',
    activeChats: '当前对话', archive: '归档', restore: '恢复', rename: '改名', language: '语言',
    changePassword: '修改密码', currentPassword: '当前密码', newPassword: '新密码',
    unknownDevice: '未知设备', you: '你', outputTokens: '输出 Token', contextLabel: '上下文 5 轮',
    example1: '帮我规划本周的学习安排', example2: '用简单语言解释一个复杂概念', example3: '润色一封专业邮件',
    legalBack: '返回首页', privacyTitle: '隐私政策', termsTitle: '服务条款',
    privacyBody: '聊天内容会保存于本服务的数据库，并发送给你选择的第三方模型供应商处理。请勿提交密码、密钥、健康、财务或其他机密信息。会话删除后会从在线查询中隐藏，备份按保留周期自然过期。',
    termsBody: '本服务为非商用测试版，不承诺服务等级。AI 输出可能不准确，用户应独立核实。禁止滥用、攻击服务或提交违法内容。',
    models: { deepseek: '高性价比综合模型', gemini: '多语言轻量模型', groq: '极速开源模型推理' },
  }},
  'ja-JP': { translation: {
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
    passwordConfirm: 'パスワード確認', acceptTerms: '同意します', terms: '利用規約', privacy: 'プライバシーポリシー',
    resendVerification: '確認メールを再送', searchConversations: '会話を検索', archived: 'アーカイブ',
    activeChats: '現在の会話', archive: 'アーカイブ', restore: '復元', rename: '名前変更', language: '言語',
    changePassword: 'パスワード変更', currentPassword: '現在のパスワード', newPassword: '新しいパスワード',
    unknownDevice: '不明な端末', you: 'あなた', outputTokens: '出力トークン', contextLabel: 'コンテキスト 5 往復',
    example1: '今週の学習計画を立てて', example2: '難しい概念をやさしく説明して', example3: 'ビジネスメールを推敲して',
    legalBack: 'ホームへ戻る', privacyTitle: 'プライバシーポリシー', termsTitle: '利用規約',
    privacyBody: 'チャット内容は本サービスのデータベースに保存され、選択した第三者AI事業者へ送信されます。パスワード、鍵、健康・金融情報などの機密情報を入力しないでください。',
    termsBody: '本サービスは非商用テスト版で、SLAはありません。AIの回答は誤る場合があるため、利用者自身で確認してください。不正利用や違法な内容は禁止します。',
    models: { deepseek: 'コスト性能に優れた汎用モデル', gemini: '多言語対応の軽量モデル', groq: '高速なオープンモデル推論' },
  }},
  'en-US': { translation: {
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
    passwordConfirm: 'Confirm password', acceptTerms: 'I agree to the', terms: 'Terms', privacy: 'Privacy Policy',
    resendVerification: 'Resend verification email', searchConversations: 'Search conversations', archived: 'Archived',
    activeChats: 'Active chats', archive: 'Archive', restore: 'Restore', rename: 'Rename', language: 'Language',
    changePassword: 'Change password', currentPassword: 'Current password', newPassword: 'New password',
    unknownDevice: 'Unknown device', you: 'You', outputTokens: 'output tokens', contextLabel: 'Context · 5 rounds',
    example1: 'Plan my study schedule for this week', example2: 'Explain a complex idea simply', example3: 'Polish a professional email',
    legalBack: 'Back to home', privacyTitle: 'Privacy Policy', termsTitle: 'Terms of Service',
    privacyBody: 'Chat content is stored in this service database and sent to the third-party AI provider you select. Do not submit passwords, keys, health, financial, or other confidential information. Deleted conversations are hidden from online queries and expire from backups under the retention policy.',
    termsBody: 'This is a non-commercial test service without an SLA. AI output may be inaccurate and must be independently verified. Abuse, attacks, and unlawful content are prohibited.',
    models: { deepseek: 'Balanced quality at low cost', gemini: 'Lightweight multilingual model', groq: 'Ultra-fast open model inference' },
  }},
} as const

const detectedLanguage = typeof navigator === 'undefined'
  ? 'en-US'
  : navigator.language.startsWith('ja')
    ? 'ja-JP'
    : navigator.language.startsWith('en')
      ? 'en-US'
      : 'zh-CN'
const savedLanguage = typeof localStorage === 'undefined' ? null : localStorage.getItem('rythm_locale')

void i18n.use(initReactI18next).init({
  resources,
  lng: savedLanguage || detectedLanguage,
  fallbackLng: 'en-US',
  interpolation: { escapeValue: false },
})

export default i18n
