import VideoDialog from './VideoDialog'
import { formatVideoTime } from './videoTime'

export default function VideoCheckpointDialog({ question, choices, setChoices, text, setText, busy, notice, error, onSubmit, onReview }) {
  return <VideoDialog title="Câu hỏi tại mốc video" pending={busy} onClose={onReview}>
    <section className="video-checkpoint video-checkpoint-modal">
      <div className="video-checkpoint-heading"><span>{formatVideoTime(question.start_time)}</span><strong>{question.kind === 'MCQ' ? question.multiple ? 'Chọn các đáp án đúng' : 'Chọn một đáp án đúng' : 'Câu hỏi tự luận'}</strong></div>
      <h3>{question.prompt}</h3>
      {notice && <p className="video-notice" role="status">{notice}</p>}
      {error && <p className="error-banner" role="alert">{error}</p>}
      <form onSubmit={onSubmit}>
        {question.kind === 'MCQ' ? <fieldset disabled={busy} className="video-student-choices"><legend className="sr-only">Câu trả lời</legend>{question.choices.map((choice) => <label key={choice.id}><input type={question.multiple ? 'checkbox' : 'radio'} name={`answer-${question.id}`} checked={choices.includes(choice.id)} onChange={(event) => setChoices((previous) => question.multiple ? event.target.checked ? [...previous, choice.id] : previous.filter((id) => id !== choice.id) : [choice.id])} />{choice.text}</label>)}</fieldset> : <><label htmlFor={`video-answer-${question.id}`}>Câu trả lời của bạn</label><textarea id={`video-answer-${question.id}`} maxLength={5000} rows={4} required disabled={busy} value={text} onChange={(event) => setText(event.target.value)} /></>}
        {question.hint && <details className="video-hint"><summary>Xem gợi ý</summary><p>{question.hint}</p></details>}
        <div className="video-dialog-actions"><button type="button" className="outline-button" disabled={busy} onClick={onReview}>Xem lại kiến thức</button><button type="submit" className="solid-button" disabled={busy || (question.kind === 'MCQ' ? !choices.length : !text.trim())}>{busy ? 'Đang gửi...' : 'Gửi câu trả lời'}</button></div>
      </form>
    </section>
  </VideoDialog>
}
