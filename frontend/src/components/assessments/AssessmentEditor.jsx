import { useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import VideoDialog from '../videos/VideoDialog'
import { correctIds } from './assessmentUtils'
import { courseErrorMessage } from '../../services/course.service'

const blankQuestion = () => ({ id: crypto.randomUUID(), prompt: '', choices: [{ id: 'a', text: '' }, { id: 'b', text: '' }], multiple: false, correct_ids: ['a'], hint: '' })
function localInput(date) {
  const value = date ? new Date(date) : new Date(Date.now() + 7 * 86400000)
  return new Date(value - value.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}
export default function AssessmentEditor({ value, onSave, onClose }) {
  const [form, setForm] = useState(() => ({ title: '', description: '', mode: 'PRACTICE', kind: 'QUIZ', duration_seconds: 1800, hint: '', ...value, questions: value?.questions?.map((q) => { return { id: q.id, prompt: q.prompt, choices: q.choices, hint: q.hint || '', multiple: Boolean(q.multiple), correct_ids: correctIds(q) } }) || [blankQuestion()], due_at: localInput(value?.due_at) }))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const change = (key, v) => setForm((old) => ({ ...old, [key]: v }))
  const question = (index, key, v) => change('questions', form.questions.map((q, i) => i === index ? { ...q, [key]: v } : q))
  return <VideoDialog title={value ? 'Chỉnh sửa bài tập' : 'Tạo bài tập'} pending={busy} onClose={onClose}><form className="assessment-form" onSubmit={async (event) => {
    event.preventDefault(); if (busy) return; setBusy(true); setError('')
    try {
      const { title, description, mode, kind, duration_seconds, hint, questions, due_at } = form
      if (kind === 'QUIZ' && questions.some((q) => !q.correct_ids.length || (!q.multiple && q.correct_ids.length !== 1))) { setError('Chọn đáp án đúng cho từng câu hỏi.'); return }
      await onSave({ title: title.trim(), description, mode, kind, duration_seconds: Number(duration_seconds), hint, questions: kind === 'QUIZ' ? questions : [], due_at: new Date(due_at).toISOString() })
    } catch (err) { setError(courseErrorMessage(err)) } finally { setBusy(false) }
  }}>
    {error && <p className="error-banner" role="alert">{error}</p>}
    <label>Tên bài tập<input required maxLength={255} value={form.title} disabled={busy} onChange={(e) => change('title', e.target.value)} /></label>
    <label>Đề bài / hướng dẫn<textarea rows={4} maxLength={10000} value={form.description} disabled={busy} onChange={(e) => change('description', e.target.value)} /></label>
    <div className="assessment-form-grid"><label>Loại bài<select value={form.kind} disabled={busy} onChange={(e) => { change('kind', e.target.value); if (e.target.value === 'QUIZ' && !form.questions.length) change('questions', [blankQuestion()]) }}><option value="QUIZ">Quiz trắc nghiệm</option><option value="TEXT">Tự luận / nộp file</option></select></label>
    <label>Chế độ<select value={form.mode} disabled={busy} onChange={(e) => change('mode', e.target.value)}><option value="PRACTICE">Ôn tập</option><option value="TEST">Kiểm tra</option></select></label>
    <label>Hạn nộp<input type="datetime-local" required value={form.due_at} disabled={busy} onChange={(e) => change('due_at', e.target.value)} /></label>
    {form.kind === 'QUIZ' && <label>Thời lượng (phút)<input type="number" min={1} max={240} required value={form.duration_seconds / 60} disabled={busy} onChange={(e) => change('duration_seconds', e.target.value * 60)} /></label>}</div>
    <p className="assessment-policy">{form.mode === 'TEST' ? 'Một lượt làm/nộp. Bắt buộc toàn màn hình, ghi nhận chuyển tab và thoát toàn màn hình. Giáo viên quyết định xử lý. Không hỗ trợ AI.' : 'Có thể làm lại hoặc chỉnh sửa và nộp lại trước hạn. Không giám sát chuyển tab. Cho phép gợi ý ôn tập.'}</p>
    {form.mode === 'PRACTICE' && <label>Gợi ý ôn tập (tùy chọn)<textarea rows={2} maxLength={5000} value={form.hint} disabled={busy} onChange={(e) => change('hint', e.target.value)} /></label>}
    {form.kind === 'QUIZ' && <div className="assessment-question-editor">{form.questions.map((q, i) => <fieldset key={q.id} disabled={busy}><legend>Câu {i + 1}</legend><label>Nội dung câu hỏi<textarea required maxLength={3000} rows={2} value={q.prompt} onChange={(e) => question(i, 'prompt', e.target.value)} /></label>
      <label>Kiểu trắc nghiệm<select aria-label={`Kiểu trắc nghiệm câu ${i+1}`} value={q.multiple ? 'MULTIPLE' : 'SINGLE'} onChange={(e) => { const multiple = e.target.value === 'MULTIPLE'; change('questions', form.questions.map((item, index) => index === i ? { ...item, multiple, correct_ids: multiple ? item.correct_ids : item.correct_ids.slice(0, 1) } : item)) }}><option value="SINGLE">Một đáp án</option><option value="MULTIPLE">Nhiều đáp án</option></select></label><p className="assessment-muted">{q.multiple ? 'Chọn các ô vuông để đánh dấu đáp án đúng.' : 'Chọn một nút tròn để đánh dấu đáp án đúng.'}</p>
      {q.choices.map((c) => <div key={c.id} className="assessment-choice-edit"><input type={q.multiple ? 'checkbox' : 'radio'} name={`correct-${q.id}`} aria-label={`Đáp án đúng câu ${i+1}: ${c.id.toUpperCase()}`} checked={q.correct_ids.includes(c.id)} onChange={(e) => question(i, 'correct_ids', q.multiple ? e.target.checked ? [...q.correct_ids, c.id] : q.correct_ids.filter((id) => id !== c.id) : [c.id])} /><input required maxLength={1000} aria-label={`Lựa chọn ${c.id.toUpperCase()} câu ${i+1}`} value={c.text} onChange={(e) => question(i, 'choices', q.choices.map((item) => item.id === c.id ? { ...item, text: e.target.value } : item))} />{q.choices.length > 2 && <button className="icon-button" type="button" aria-label={`Xóa lựa chọn ${c.id}`} onClick={() => { const choices = q.choices.filter((item) => item.id !== c.id); change('questions', form.questions.map((item, index) => index === i ? { ...q, choices, correct_ids: q.correct_ids.filter((id) => id !== c.id) } : item)) }}><Trash2 size={15} /></button>}</div>)}
      <div className="assessment-actions"><button className="outline-button" type="button" disabled={q.choices.length >= 8} onClick={() => question(i, 'choices', [...q.choices, { id: crypto.randomUUID(), text: '' }])}>Thêm lựa chọn</button><button className="outline-button" type="button" disabled={form.questions.length === 1} onClick={() => change('questions', form.questions.filter((_, index) => index !== i))}>Xóa câu hỏi</button></div>
      {form.mode === 'PRACTICE' && <label>Gợi ý câu hỏi<input maxLength={2000} value={q.hint} onChange={(e) => question(i, 'hint', e.target.value)} /></label>}
    </fieldset>)}<button type="button" className="outline-button" disabled={busy || form.questions.length >= 100} onClick={() => change('questions', [...form.questions, blankQuestion()])}><Plus size={17} />Thêm câu hỏi</button></div>}
    <div className="video-dialog-actions"><button type="button" className="outline-button" disabled={busy} onClick={onClose}>Hủy</button><button type="submit" className="solid-button" disabled={busy}>{busy ? 'Đang lưu...' : 'Lưu bài tập'}</button></div>
  </form></VideoDialog>
}
