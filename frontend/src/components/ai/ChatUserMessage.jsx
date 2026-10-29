export default function ChatUserMessage({ question, createdAt }) {
  const date = createdAt ? new Date(createdAt) : null
  const valid = date && Number.isFinite(date.getTime())
  const time = valid ? new Intl.DateTimeFormat('vi-VN', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(date) : null
  return <div className="ai-user-turn">
    {valid && <time className="ai-chat-asked-time" dateTime={createdAt} title={date.toLocaleString('vi-VN')}>{time}</time>}
    <div className="ai-user-message">{question}</div>
  </div>
}
