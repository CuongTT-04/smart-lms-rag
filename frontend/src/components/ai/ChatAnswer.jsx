import { useEffect, useMemo, useRef, useState } from 'react'
import { BookOpen, ThumbsUp, ThumbsDown } from 'lucide-react'
import { sendChatFeedback } from '../../services/ai.service'
import CitationText from './CitationText'

function AnimatedAnswer({ result, active }) {
  const words = useMemo(() => result.answer.match(/\S+\s*/g) || [], [result.answer])
  const [count, setCount] = useState(() => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? words.length : 0)
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

export default function ChatAnswer({ result, onOpenCitation, active = true }) {
  const [rating, setRating] = useState(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const request = useRef(null)
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
    <AnimatedAnswer result={result} active={active} />
    {result.citations?.length > 0 && <div className="ai-chat-sources"><strong>Nguồn học liệu</strong>
      {result.citations.map((citation) => <button className="ai-chat-source" key={citation.label} type="button" onClick={() => onOpenCitation?.(citation)}>
        <BookOpen size={15} /><span>[{citation.label}] {citation.document_title} — trang {citation.page_number}</span>
      </button>)}
    </div>}
    {result.request_id && <div className="ai-chat-feedback" aria-label="Đánh giá câu trả lời">
      <button type="button" className="ai-feedback-like" aria-label="Thích câu trả lời" title="Thích" aria-pressed={rating === 'LIKE'} disabled={saving} onClick={() => rate('LIKE')}><ThumbsUp size={16} fill={rating === 'LIKE' ? 'currentColor' : 'none'} /></button>
      <button type="button" className="ai-feedback-dislike" aria-label="Không thích câu trả lời" title="Không thích" aria-pressed={rating === 'DISLIKE'} disabled={saving} onClick={() => rate('DISLIKE')}><ThumbsDown size={16} fill={rating === 'DISLIKE' ? 'currentColor' : 'none'} /></button>
      {saving && <span>Đang lưu…</span>}
    </div>}
    {error && <p className="ai-feedback-error" role="alert">{error}</p>}
  </div>
}
