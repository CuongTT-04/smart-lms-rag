import { useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import CustomSelect from '../CustomSelect'
import { getVideoResponses } from '../../services/video.service'
import { courseErrorMessage } from '../../services/course.service'
import { formatVideoTime } from './videoTime'

export default function VideoResponses({ path, videoId }) {
  const [data, setData] = useState(null)
  const [revision, setRevision] = useState(0)
  const [filter, setFilter] = useState('ALL')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    const controller = new AbortController()
    getVideoResponses(path, videoId, controller.signal).then((result) => { if (!controller.signal.aborted) setData(result) })
      .catch((err) => { if (!controller.signal.aborted) setError(courseErrorMessage(err)) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [path, videoId, revision])
  return <section className="video-responses" aria-label="Quản lý câu trả lời video"><div className="video-panel-heading"><h3>Câu trả lời của học viên</h3><button type="button" className="icon-button" aria-label="Làm mới câu trả lời" disabled={loading} onClick={() => { setLoading(true); setError(''); setRevision((value) => value + 1) }}><RefreshCw size={18} /></button></div>
    {error && <div className="error-banner" role="alert">{error}</div>}
    {loading && <p role="status">Đang tải câu trả lời...</p>}
    {data && <><div className="video-response-stats">{data.questions.map((question) => <article key={question.id}><span>{formatVideoTime(question.start_time)} · {question.kind === 'MCQ' ? 'Trắc nghiệm' : 'Tự luận'}</span><strong>{question.prompt}</strong><p>{question.answered_students}/{data.student_count} học viên đã trả lời · {question.attempt_count} lượt thử{question.kind === 'MCQ' ? ` · ${question.correct_students} học viên trả lời đúng` : ''}</p></article>)}</div>
      <CustomSelect aria-label="Lọc câu hỏi" value={filter} onChange={(event) => setFilter(event.target.value)}><option value="ALL">Tất cả câu hỏi</option>{data.questions.map((question) => <option key={question.id} value={question.id}>{formatVideoTime(question.start_time)} · {question.prompt.slice(0, 60)}</option>)}</CustomSelect>
      <div className="video-answer-list">{data.results.filter((answer) => filter === 'ALL' || answer.question_id === filter).map((answer) => <article key={answer.id}><header><strong>{answer.student_name}</strong><time dateTime={answer.created_at}>{new Date(answer.created_at).toLocaleString('vi-VN')}</time></header><p className="video-answer-prompt">{answer.snapshot.prompt} <small>· Phiên bản {answer.question_revision}</small></p>{answer.snapshot.kind === 'TEXT' ? <p>{answer.text}</p> : <><p>Đã chọn: {answer.selected_ids.map((id) => answer.snapshot.choices.find((choice) => choice.id === id)?.text || id).join('; ')}</p><span className={`video-answer-result ${answer.is_correct ? 'is-correct' : 'is-wrong'}`}>{answer.is_correct ? 'Chính xác' : 'Chưa chính xác'}</span></>}</article>)}{!data.results.length && <p className="video-help-copy">Chưa có câu trả lời. Câu trả lời sẽ được lưu tại đây khi học viên gửi.</p>}</div>
    </>}
  </section>
}
