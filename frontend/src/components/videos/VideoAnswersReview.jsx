import { useEffect, useState } from 'react'
import { ChevronDown, RefreshCw } from 'lucide-react'
import { getMyVideoAnswers } from '../../services/video.service'
import { courseErrorMessage } from '../../services/course.service'
import { formatVideoTime } from './videoTime'

export default function VideoAnswersReview({ path, videoId, questions, refreshToken = 0 }) {
  const [answers, setAnswers] = useState([])
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    getMyVideoAnswers(path, videoId, controller.signal)
      .then((items) => { if (!controller.signal.aborted) { setAnswers(items); setError('') } })
      .catch((err) => { if (!controller.signal.aborted) setError(courseErrorMessage(err)) })
    return () => controller.abort()
  }, [path, videoId, refreshToken, revision])
  const groups = new Map()
  for (const answer of answers) {
    const key = `${answer.question_id}:${answer.question_revision}`
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(answer)
  }
  return <section className="video-answers-review" aria-label="Câu hỏi đã trả lời">
    <header><h3>Câu hỏi đã trả lời</h3><button type="button" className="icon-button" aria-label="Làm mới câu hỏi đã trả lời" onClick={() => setRevision((value) => value + 1)}><RefreshCw size={17} /></button></header>
    {error && <p className="error-banner" role="alert">{error}</p>}
    {!answers.length && !error && <p className="video-help-copy">Các câu hỏi bạn đã trả lời sẽ xuất hiện tại đây.</p>}
    {[...groups].map(([key, attempts]) => {
      const snapshot = attempts[0].snapshot
      const currentQuestion = questions?.find((item) => item.id === attempts[0].question_id)
      const historyLabel = questions ? !currentQuestion ? 'Câu hỏi đã gỡ' : currentQuestion.revision !== attempts[0].question_revision ? 'Phiên bản cũ' : '' : ''
      return <details className="video-answer-card" key={key}>
        <summary><span title={snapshot.prompt}>{snapshot.prompt}</span><small>{attempts.length} lần trả lời</small><ChevronDown size={18} /></summary>
        <div className="video-answer-card-content"><h4>{snapshot.prompt}</h4>{historyLabel && <span className="video-answer-result">{historyLabel}</span>}<p className="video-help-copy">{snapshot.kind === 'TEXT' ? 'Tự luận' : 'Trắc nghiệm'} · Phiên bản {attempts[0].question_revision}{snapshot.start_time != null ? ` · ${formatVideoTime(snapshot.start_time)}` : ''}</p>
          {[...attempts].reverse().map((answer, index) => <article key={answer.id}>
            <header><strong>Lần trả lời {index + 1}</strong><time dateTime={answer.created_at}>{new Date(answer.created_at).toLocaleString('vi-VN')}</time></header>
            {snapshot.kind === 'TEXT' ? <p>{answer.text}</p> : <ul>{(answer.snapshot.choices || []).map((choice) => <li key={choice.id} className={answer.selected_ids.includes(choice.id) ? 'is-selected' : ''}>{choice.text}{answer.selected_ids.includes(choice.id) && <small>Đã chọn</small>}</li>)}</ul>}
            <span className={`video-answer-result ${answer.is_correct === true ? 'is-correct' : answer.is_correct === false ? 'is-wrong' : ''}`}>{answer.is_correct === true ? 'Chính xác' : answer.is_correct === false ? 'Chưa chính xác' : 'Đã gửi tự luận'}</span>
          </article>)}
          {snapshot.hint && <details className="video-hint"><summary>Xem gợi ý</summary><p>{snapshot.hint}</p></details>}
        </div>
      </details>
    })}
  </section>
}
