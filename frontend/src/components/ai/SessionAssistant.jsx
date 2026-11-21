import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowUp } from 'lucide-react'
import { sendChat, chatErrorMessage } from '../../services/ai.service'
import ChatAnswer from './ChatAnswer'
import ChatUserMessage from './ChatUserMessage'
import DocumentAssistant from './DocumentAssistant'
import './assistant.css'

export default function SessionAssistant(props) {
  const key = JSON.stringify(props.exercise
    ? [props.scope, props.exercise.assessment_id, props.exercise.question_id]
    : [props.scope, props.documentId, props.documentVersion])
  if (!props.exercise && props.documentId) return <DocumentAssistant key={key} {...props} />
  if (!props.exercise && props.requireDocument) return <div className="ai-chat-content"><p className="ai-chat-empty">Chọn một học liệu để bắt đầu trò chuyện và xem lịch sử.</p></div>
  return <AssistantForm key={key} {...props} />
}

function AssistantForm({ scope, exercise, onOpenCitation, visible = true }) {
  const [question, setQuestion] = useState('')
  const [turns, setTurns] = useState([])
  const [busy, setBusy] = useState(false)
  const active = useRef(null)
  const input = useRef(null)
  const thread = useRef(null)
  const content = useRef(null)
  const pinned = useRef(true)
  const sequence = useRef(0)
  const initialRequested = useRef(false)
  const pendingRequest = useRef(false)
  const lastHint = useRef(null)
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
  const ask = useCallback(async (text, automatic = false, hintAction = 'practice', previousHintId = lastHint.current) => {
    text = text.trim()
    if (pendingRequest.current || !text) return
    pendingRequest.current = true
    const controller = new AbortController()
    active.current = controller
    const id = ++sequence.current
    pinned.current = true
    setTurns((current) => [...current, { id, question: text, automatic, hintAction, previousHintId, createdAt: new Date().toISOString(), pending: true }])
    setQuestion('')
    if (input.current) input.current.style.height = '24px'
    setBusy(true)
    try {
      const data = await sendChat({ ...scope, question: text, mode: exercise ? 'hint' : 'qa',
        ...(exercise ? { assessment_id: exercise.assessment_id,
          hint_action: previousHintId ? hintAction : 'initial',
          ...(previousHintId && hintAction !== 'initial' ? { previous_hint_id: previousHintId } : {}),
          ...(exercise.question_id ? { question_id: exercise.question_id } : {}) } : {}) }, { signal: controller.signal })
      if (!controller.signal.aborted) {
        if (exercise && data.status === 'ANSWERED') lastHint.current = data.request_id
        setTurns((current) => current.map((turn) => turn.id === id ? { ...turn, pending: false, result: data } : turn))
      }
    } catch (err) {
      if (!controller.signal.aborted) setTurns((current) => current.map((turn) => turn.id === id ? { ...turn, pending: false, error: chatErrorMessage(err) } : turn))
    } finally {
      pendingRequest.current = false
      if (!controller.signal.aborted) setBusy(false)
    }
  }, [scope, exercise])
  useEffect(() => {
    if (!exercise || !visible || initialRequested.current) return
    // Defer until mount settles so StrictMode does not submit the same hint twice.
    const timer = setTimeout(() => {
      initialRequested.current = true
      void ask('Gợi ý cách tiếp cận bài này, không đưa lời giải hoàn chỉnh.', true, 'initial')
    }, 0)
    return () => clearTimeout(timer)
  }, [exercise, visible, ask])
  function submit(event) {
    event.preventDefault()
    void ask(question)
  }
  const latest = turns.at(-1)
  return <div className="ai-chat-content">
    <div className="ai-chat-result" ref={thread} aria-label="Hội thoại với ayo" onScroll={() => {
      const box = thread.current
      pinned.current = box.scrollHeight - box.scrollTop - box.clientHeight < 60
    }}>
      <div ref={content} className="ai-chat-thread">{turns.map((turn) => <section className="ai-chat-turn" key={turn.id}>
        <ChatUserMessage question={turn.question} createdAt={turn.createdAt} />
        {turn.pending && <div className="ai-thinking" role="status"><span className="ai-thinking-dots" aria-hidden="true"><i /><i /><i /></span>{exercise ? 'Đang đọc đề và tìm học liệu liên quan…' : 'Đang suy nghĩ…'}</div>}
        {turn.error && <div><p className="error-banner" role="alert">{turn.error}</p><button className="ai-chat-retry" type="button" disabled={busy} onClick={() => {
          if (exercise) void ask(turn.question, turn.automatic, turn.hintAction, turn.previousHintId)
          else { setQuestion(turn.question); input.current?.focus() }
        }}>{exercise ? 'Thử lại gợi ý' : 'Soạn lại câu hỏi'}</button></div>}
        {turn.result && <ChatAnswer result={turn.result} onOpenCitation={onOpenCitation} active={visible} />}
      </section>)}</div>
    </div>
    {exercise && !busy && latest?.result?.status === 'ANSWERED' && <div className="ai-hint-actions" aria-label="Hỏi tiếp về bài ôn tập">
      <button type="button" onClick={() => ask('Giải thích rõ yêu cầu của đề và gợi ý cách tự đọc học liệu, không giải bài.', false, 'explain_task')}>Giải thích rõ yêu cầu đề</button>
      {latest.result.hint?.can_advance !== false
        ? <button type="button" onClick={() => ask('Gợi ý bước tiếp theo để tôi tự làm bài, không đưa lời giải hoàn chỉnh.', false, 'next_step')}>Gợi ý bước tiếp theo</button>
        : <button type="button" onClick={() => input.current?.focus()}>Thử trả lời</button>}
    </div>}
    <form className="ai-chat-compose" onSubmit={submit}>
      <textarea ref={input} aria-label="Câu hỏi cho ayo" value={question} onChange={(event) => { setQuestion(event.target.value); resizeInput() }} onKeyDown={(event) => {
        if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); submit(event) }
      }} maxLength={8000} rows={1} disabled={busy} placeholder={exercise ? 'Bạn đang vướng ở bước nào?' : 'Hỏi ayo…'} />
      <button className="ai-chat-send" aria-label="Gửi câu hỏi" title="Gửi câu hỏi" disabled={busy || !question.trim()} type="submit"><ArrowUp size={19} /></button>
    </form>
    <p className="ai-chat-disclaimer">ayo có thể sai — hãy đối chiếu với học liệu.</p>
  </div>
}
