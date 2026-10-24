import { useId, useRef, useState } from 'react'
import { CircleHelp, Plus, Sparkles, Trash2 } from 'lucide-react'
import CustomSelect from '../CustomSelect'
import { courseErrorMessage } from '../../services/course.service'
import VideoDialog from './VideoDialog'
import { formatVideoTime, parseVideoTime } from './videoTime'

function TimeHelp({ text }) {
  return <span className="video-time-help" tabIndex={0} aria-label={text}><CircleHelp size={15} /><span role="tooltip">{text}</span></span>
}
export default function VideoQuestionDialog({ question, startTime = 0, duration, onSave, onClose }) {
  const prefix = useId()
  const [kind, setKind] = useState(question?.kind || 'MCQ')
  const [prompt, setPrompt] = useState(question?.prompt || '')
  const [choices, setChoices] = useState(question?.choices?.length ? question.choices : [{ id: crypto.randomUUID(), text: '' }, { id: crypto.randomUUID(), text: '' }])
  const [correct, setCorrect] = useState(question?.correct_ids || [])
  const [multiple, setMultiple] = useState(question?.multiple ?? (question?.correct_ids?.length > 1))
  const [hint, setHint] = useState(question?.hint || '')
  const [start, setStart] = useState(formatVideoTime(question?.start_time ?? startTime))
  const [rewind, setRewind] = useState(question?.rewind_time == null ? '' : formatVideoTime(question.rewind_time))
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const lock = useRef(false)
  async function submit(event) {
    event.preventDefault()
    if (lock.current) return
    const time = parseVideoTime(start)
    const back = kind === 'MCQ' && rewind.trim() ? parseVideoTime(rewind) : null
    if (time == null || time > duration || (kind === 'MCQ' && rewind.trim() && (back == null || back >= time))) { setError('Kiểm tra mốc bắt đầu trong video và mốc quay lại trước mốc bắt đầu.'); return }
    if (kind === 'MCQ' && (!correct.length || choices.some((choice) => !choice.text.trim()))) { setError('Nhập các lựa chọn và đánh dấu ít nhất một đáp án đúng.'); return }
    lock.current = true; setSaving(true); setError('')
    try {
      await onSave({ kind, multiple: kind === 'MCQ' && multiple, prompt: prompt.trim(), hint: hint.trim(), start_time: time, rewind_time: back, choices: kind === 'MCQ' ? choices.map((choice) => ({ ...choice, text: choice.text.trim() })) : [], correct_ids: kind === 'MCQ' ? correct : [] })
    } catch (err) { setError(courseErrorMessage(err)) }
    finally { lock.current = false; setSaving(false) }
  }
  return <VideoDialog title={question ? 'Chỉnh sửa câu hỏi' : 'Tạo câu hỏi theo mốc'} pending={saving} onClose={onClose}><form onSubmit={submit} className="video-form">
    {error && <div role="alert" className="error-banner">{error}</div>}
    <label htmlFor={`${prefix}-kind`}>Loại câu hỏi</label><CustomSelect id={`${prefix}-kind`} aria-label="Loại câu hỏi" value={kind} disabled={saving} onChange={(event) => setKind(event.target.value)}><option value="MCQ">Trắc nghiệm</option><option value="TEXT">Tự luận</option></CustomSelect>
    <label htmlFor={`${prefix}-prompt`}>Nội dung câu hỏi</label><textarea id={`${prefix}-prompt`} rows={3} maxLength={2000} required value={prompt} disabled={saving} onChange={(event) => setPrompt(event.target.value)} />
    {kind === 'MCQ' && <><label htmlFor={`${prefix}-selection`}>Kiểu trắc nghiệm</label><CustomSelect id={`${prefix}-selection`} aria-label="Kiểu trắc nghiệm" value={multiple ? 'MULTIPLE' : 'SINGLE'} disabled={saving} onChange={(event) => { const next = event.target.value === 'MULTIPLE'; setMultiple(next); if (!next) setCorrect((ids) => ids.slice(0, 1)) }}><option value="SINGLE">Một đáp án</option><option value="MULTIPLE">Nhiều đáp án</option></CustomSelect></>}
    {kind === 'MCQ' && <fieldset className="video-choice-editor"><legend>Lựa chọn và đáp án đúng</legend><p>{multiple ? 'Đánh dấu các đáp án đúng.' : 'Chọn đúng một đáp án.'}</p>{choices.map((choice, index) => <div key={choice.id}><input type={multiple ? 'checkbox' : 'radio'} name={`${prefix}-correct`} aria-label={`Đáp án đúng ${index + 1}`} disabled={saving} checked={correct.includes(choice.id)} onChange={(event) => setCorrect((ids) => multiple ? event.target.checked ? [...ids, choice.id] : ids.filter((id) => id !== choice.id) : [choice.id])} /><input aria-label={`Lựa chọn ${index + 1}`} value={choice.text} maxLength={500} required disabled={saving} onChange={(event) => setChoices((items) => items.map((item) => item.id === choice.id ? { ...item, text: event.target.value } : item))} /><button type="button" className="icon-button" aria-label={`Xóa lựa chọn ${index + 1}`} disabled={saving || choices.length <= 2} onClick={() => { setChoices((items) => items.filter((item) => item.id !== choice.id)); setCorrect((ids) => ids.filter((id) => id !== choice.id)) }}><Trash2 size={16} /></button></div>)}<button type="button" className="text-button" disabled={saving || choices.length >= 10} onClick={() => setChoices((items) => [...items, { id: crypto.randomUUID(), text: '' }])}><Plus size={16} />Thêm lựa chọn</button></fieldset>}
    <div className="video-hint-label"><label htmlFor={`${prefix}-hint`}>Gợi ý <small>(Tùy chọn)</small></label><span title="Chức năng AI sẽ được cấu hình sau"><button type="button" className="outline-button" disabled><Sparkles size={16} />Tạo gợi ý bằng AI</button></span></div><textarea id={`${prefix}-hint`} rows={2} maxLength={2000} value={hint} disabled={saving} onChange={(event) => setHint(event.target.value)} placeholder="Nhập gợi ý để học viên tự tìm hướng trả lời..." /><small className="video-help-copy">AI chưa được kết nối. Bạn có thể nhập gợi ý thủ công.</small>
    <div className="video-time-fields"><div><label htmlFor={`${prefix}-start`}>Mốc bắt đầu <TimeHelp text="Video tạm dừng tại thời điểm này để học viên trả lời câu hỏi." /></label><input id={`${prefix}-start`} value={start} required disabled={saving} onChange={(event) => setStart(event.target.value)} placeholder="mm:ss" /></div>{kind === 'MCQ' && <div><label htmlFor={`${prefix}-rewind`}>Mốc quay lại <TimeHelp text="Nếu trả lời sai, video quay lại mốc này để học viên xem kiến thức rồi thử lại. Có thể để trống." /></label><input id={`${prefix}-rewind`} value={rewind} disabled={saving} onChange={(event) => setRewind(event.target.value)} placeholder="Tùy chọn · mm:ss" /></div>}</div>
    <div className="video-dialog-actions"><button type="button" className="outline-button" disabled={saving} onClick={onClose}>Hủy</button><button type="submit" className="solid-button" disabled={saving || !prompt.trim()}>{saving ? 'Đang lưu...' : question ? 'Lưu thay đổi' : 'Tạo câu hỏi'}</button></div>
  </form></VideoDialog>
}
