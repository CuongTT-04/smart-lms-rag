import { useEffect, useRef, useState } from 'react'
import { ArrowUp } from 'lucide-react'
import { sendChat, chatErrorMessage } from '../../services/ai.service'
import ChatAnswer from './ChatAnswer'
import './assistant.css'

export default function SessionAssistant(props) {
  const key = JSON.stringify([props.scope, props.exercise?.assessment_id, props.exercise?.question_id])
  return <AssistantForm key={key} {...props} />
}

function AssistantForm({ scope, exercise, onOpenCitation, visible = true }) {
  const [question, setQuestion] = useState('')
  const [mode, setMode] = useState(exercise ? 'hint' : 'qa')
  const [turns, setTurns] = useState([])
  const [busy, setBusy] = useState(false)
  const active = useRef(null)
  const input = useRef(null)
  const thread = useRef(null)
  const content = useRef(null)
  const pinned = useRef(true)
  const sequence = useRef(0)
  useEffect(() => () => active.current?.abort(), [])
  useEffect(() => {
    const scroll = () => { if (pinned.current && thread.current) thread.current.scrollTop = thread.current.scrollHeight }
    scroll()
    if (!window.ResizeObserver || !content.current) return
    const observer = new ResizeObserver(scroll)
    observer.observe(content.current)
    return () => observer.disconnect()
  }, [turns])
  function resizeInput() {
    if (input.current) {
      input.current.style.height = 'auto'
      input.current.style.height = `${Math.min(120, Math.max(24, input.current.scrollHeight - 8))}px`
    }
  }
  async function submit(event) {
    event.preventDefault()
    if (busy || !question.trim()) return
    const controller = new AbortController()
    active.current = controller
    const text = question.trim()
    const id = ++sequence.current
    pinned.current = true
    setTurns((current) => [...current, { id, question: text, pending: true }])
    setQuestion('')
    if (input.current) input.current.style.height = '24px'
    setBusy(true)
    try {
      const data = await sendChat({ ...scope, question: text, mode,
        ...(mode === 'hint' ? exercise : {}) }, { signal: controller.signal })
      if (!controller.signal.aborted) setTurns((current) => current.map((turn) => turn.id === id ? { ...turn, pending: false, result: data } : turn))
    } catch (err) {
      if (!controller.signal.aborted) setTurns((current) => current.map((turn) => turn.id === id ? { ...turn, pending: false, error: chatErrorMessage(err) } : turn))
    } finally {
      if (!controller.signal.aborted) setBusy(false)
    }
  }
  return <div className="ai-chat-content">
    {exercise && <label className="ai-chat-mode">Cách hỗ trợ<select value={mode} disabled={busy} onChange={(event) => setMode(event.target.value)}><option value="qa">Hỏi đáp học liệu</option><option value="hint">Gợi ý ôn tập</option></select></label>}
    <div className="ai-chat-result" ref={thread} aria-label="Hội thoại với trợ lý" onScroll={() => {
      const box = thread.current
      pinned.current = box.scrollHeight - box.scrollTop - box.clientHeight < 60
    }}>
      <div ref={content} className="ai-chat-thread">{turns.map((turn) => <section className="ai-chat-turn" key={turn.id}>
        <div className="ai-user-message">{turn.question}</div>
        {turn.pending && <div className="ai-thinking" role="status"><span className="ai-thinking-dots" aria-hidden="true"><i /><i /><i /></span>Đang suy nghĩ…</div>}
        {turn.error && <div><p className="error-banner" role="alert">{turn.error}</p><button className="ai-chat-retry" type="button" disabled={busy} onClick={() => { setQuestion(turn.question); input.current?.focus() }}>Soạn lại câu hỏi</button></div>}
        {turn.result && <ChatAnswer result={turn.result} onOpenCitation={onOpenCitation} active={visible} />}
      </section>)}</div>
    </div>
    <form className="ai-chat-compose" onSubmit={submit}>
      <textarea ref={input} aria-label="Câu hỏi cho trợ lý" value={question} onChange={(event) => { setQuestion(event.target.value); resizeInput() }} onKeyDown={(event) => {
        if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); submit(event) }
      }} maxLength={8000} rows={1} disabled={busy} placeholder="Hỏi bất cứ điều gì…" />
      <button className="ai-chat-send" aria-label="Gửi câu hỏi" title="Gửi câu hỏi" disabled={busy || !question.trim()} type="submit"><ArrowUp size={19} /></button>
    </form>
    <p className="ai-chat-disclaimer">Chatbot AI có thể sai — hãy đối chiếu với học liệu.</p>
  </div>
}
