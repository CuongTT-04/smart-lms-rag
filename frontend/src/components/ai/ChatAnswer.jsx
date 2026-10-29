import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { BookOpen, ChevronDown, ThumbsUp, ThumbsDown } from 'lucide-react'
import { sendChatFeedback } from '../../services/ai.service'
import CitationText from './CitationText'

function responseDuration(milliseconds) {
  if (typeof milliseconds !== 'number' || !Number.isFinite(milliseconds) || milliseconds < 0) return null
  const seconds = Math.round(milliseconds / 1000)
  const minutes = Math.floor(seconds / 60)
  return minutes ? `${minutes} phút ${String(seconds % 60).padStart(2, '0')} giây` : `${seconds} giây`
}

function AnimatedAnswer({ result, active, animate }) {
  const words = useMemo(() => result.answer.match(/\S+\s*/g) || [], [result.answer])
  const [count, setCount] = useState(() => !animate || window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? words.length : 0)
  useEffect(() => {
    if (count >= words.length) return
    const timer = setInterval(() => setCount((current) => Math.min(words.length, current + Math.max(1, Math.ceil(words.length / 180)))), 24)
    return () => clearInterval(timer)
  }, [count, words.length])
  const complete = count >= words.length
  return <div className={`ai-chat-answer ${result.status === 'INSUFFICIENT_EVIDENCE' ? 'ai-chat-insufficient' : ''}`}>
    {!complete && <span className="ai-screen-reader-only">{result.answer}</span>}
    <div aria-hidden={!complete}><CitationText text={words.slice(0, count).join('')} citations={active ? result.citations : []} />
      {!complete && <span className="ai-typing-cursor" aria-hidden="true" />}</div>
  </div>
}

export default function ChatAnswer({ result, onOpenCitation, active = true, animate = true }) {
  const [sourcesOpen, setSourcesOpen] = useState(false)
  const sourcesId = useId()
  const [rating, setRating] = useState(result.rating || null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const request = useRef(null)
  const duration = responseDuration(result.timing?.total_ms)
  useEffect(() => () => request.current?.abort(), [])
  async function rate(value) {
    if (saving) return
    const controller = new AbortController()
    request.current = controller
    setSaving(true); setError('')
    try {
      const data = await sendChatFeedback(result.request_id, rating === value ? null : value, { signal: controller.signal })
      if (!controller.signal.aborted) setRating(data.rating)
    } catch {
      if (!controller.signal.aborted) setError('Chưa lưu được đánh giá. Vui lòng thử lại.')
    } finally {
      if (!controller.signal.aborted) setSaving(false)
    }
  }
  return <div className="ai-assistant-message">
    <div className="ai-chat-response">
      {duration !== null && <p className="ai-chat-response-time">Phản hồi trong {duration}</p>}
      <AnimatedAnswer result={result} active={active} animate={animate} />
    </div>
    {result.citations?.length > 0 && <section className="ai-chat-sources">
      <button className="ai-chat-sources-toggle" type="button" aria-expanded={sourcesOpen} aria-controls={sourcesId} onClick={() => setSourcesOpen(open => !open)}>
        <span>Nguồn học liệu ({result.citations.length})</span><ChevronDown size={15} />
      </button>
      <div id={sourcesId} className={`ai-chat-source-panel ${sourcesOpen ? 'is-open' : 'is-closed'}`} aria-hidden={!sourcesOpen} inert={!sourcesOpen}>
      <div className="ai-chat-source-clip"><div className="ai-chat-source-list">
      {result.citations.map((citation) => <button className="ai-chat-source" key={citation.label} type="button" onClick={() => onOpenCitation?.(citation)}>
        <BookOpen size={15} /><span>[{citation.label}] {citation.document_title} — trang {citation.page_number}</span>
      </button>)}
      </div></div>
      </div>
    </section>}
    {result.request_id && <div className="ai-chat-feedback" aria-label="Đánh giá câu trả lời">
      <button type="button" className="ai-feedback-like" aria-label="Thích câu trả lời" title="Thích" aria-pressed={rating === 'LIKE'} disabled={saving} onClick={() => rate('LIKE')}><ThumbsUp size={16} fill={rating === 'LIKE' ? 'currentColor' : 'none'} /></button>
      <button type="button" className="ai-feedback-dislike" aria-label="Không thích câu trả lời" title="Không thích" aria-pressed={rating === 'DISLIKE'} disabled={saving} onClick={() => rate('DISLIKE')}><ThumbsDown size={16} fill={rating === 'DISLIKE' ? 'currentColor' : 'none'} /></button>
      {saving && <span>Đang lưu…</span>}
    </div>}
    {error && <p className="ai-feedback-error" role="alert">{error}</p>}
  </div>
}
