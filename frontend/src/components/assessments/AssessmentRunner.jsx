import { useEffect, useRef, useState } from 'react'
import { CheckCircle2, Download, Expand, Save, Send, Sparkles } from 'lucide-react'
import VideoDialog from '../videos/VideoDialog'
import FilePicker from '../FilePicker'
import { assessmentWrite, downloadAssessmentFile, getAssessment, saveAssessmentDraft } from '../../services/assessment.service'
import { courseErrorMessage } from '../../services/course.service'

import { dateLabel, correctIds, answerIds } from './assessmentUtils'
const remainingLabel = (seconds) => `${Math.floor(Math.max(0, seconds)/60).toString().padStart(2, '0')}:${Math.max(0, seconds % 60).toString().padStart(2, '0')}`

export default function AssessmentRunner({ path, info, onRefresh, onTestActive }) {
  const [attempt, setAttempt] = useState(null)
  const [answers, setAnswers] = useState({})
  const [text, setText] = useState('')
  const [file, setFile] = useState(null)
  const [removeFile, setRemoveFile] = useState(false)
  const [version, setVersion] = useState(0)
  const [busy, setBusy] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [confirm, setConfirm] = useState(false)
  const [hint, setHint] = useState(null)
  const [now, setNow] = useState(() => Date.now())
  const [fullscreen, setFullscreen] = useState(Boolean(document.fullscreenElement))
  const root = useRef(null)
  const current = useRef(null)
  const values = useRef({ answers: {}, text: '', file: null, removeFile: false, version: 0 })
  const savedVersion = useRef(0)
  const chain = useRef(Promise.resolve())
  const mounted = useRef(true)
  const startId = useRef(null)
  const [serverOffset, setServerOffset] = useState(() => new Date(info.server_now).getTime() - Date.now())
  const offset = useRef(serverOffset)
  const [savedCount, setSavedCount] = useState(0)
  const attemptPath = (id) => `${path}attempts/${id}/`
  const editable = attempt?.status === 'DRAFT'
  const test = info.mode === 'TEST'
  const expired = now + serverOffset >= new Date(attempt?.expires_at || info.due_at).getTime()

  function accept(data, hydrate = false) {
    current.current = data
    if (!mounted.current) return
    offset.current = new Date(data.server_now).getTime() - Date.now(); setServerOffset(offset.current); setNow(Date.now())
    setAttempt(data)
    if (hydrate) {
      setAnswers(data.answers); setText(data.text); setFile(null); setRemoveFile(false)
      values.current = { answers: data.answers, text: data.text, file: null, removeFile: false, version: 0 }
      savedVersion.current = 0; setVersion(0); setSavedCount(0)
    }
    if (data.status === 'SUBMITTED') {
      if (test && document.fullscreenElement && document.fullscreenElement === root.current) {
        document.exitFullscreen?.().catch(() => {
          if (mounted.current) setError('Bài đã nộp thành công. Bạn có thể nhấn Esc để thoát toàn màn hình.')
        })
      }
      onTestActive?.(false)
      setNotice(data.auto_submitted ? 'Đã hết thời gian. Hệ thống đã chốt câu trả lời được lưu.' : 'Đã nộp bài thành công.')
      onRefresh?.()
    }
  }
  function edit(change) {
    values.current = { ...values.current, ...change, version: values.current.version + 1 }
    setVersion(values.current.version)
    if ('answers' in change) setAnswers(change.answers)
    if ('text' in change) setText(change.text)
    if ('file' in change) setFile(change.file)
    if ('removeFile' in change) setRemoveFile(change.removeFile)
  }
  function persist() {
    const snapshot = { ...values.current }
    const run = chain.current.catch(() => {}).then(async () => {
      const active = current.current
      if (!active || active.status !== 'DRAFT' || snapshot.version <= savedVersion.current) return active
      if (mounted.current) setSaving(true)
      const payload = { revision: active.revision, ...(info.kind === 'QUIZ' ? { answers: snapshot.answers } : { text: snapshot.text, remove_file: snapshot.removeFile, ...(snapshot.file ? { file: snapshot.file } : {}) }) }
      try {
        const result = await saveAssessmentDraft(attemptPath(active.id), payload)
        savedVersion.current = snapshot.version
        if (mounted.current) setSavedCount(snapshot.version)
        accept(result)
        if (snapshot.version === values.current.version && snapshot.file) { values.current.file = null; if (mounted.current) setFile(null) }
        if (mounted.current) setError('')
        return result
      } finally { if (mounted.current) setSaving(false) }
    })
    chain.current = run
    return run
  }
  async function start() {
    if (busy) return
    setBusy(true); setError('')
    try {
      if (test && !document.fullscreenElement) {
        if (!root.current.requestFullscreen) throw new Error('Trình duyệt không hỗ trợ toàn màn hình. Hãy dùng trình duyệt khác để làm bài kiểm tra.')
        await root.current.requestFullscreen()
      }
      if (!startId.current) startId.current = crypto.randomUUID()
      const data = await assessmentWrite(`${path}start/`, 'POST', { request_id: startId.current, fullscreen: Boolean(document.fullscreenElement) })
      accept(data, true); onTestActive?.(test && data.status === 'DRAFT')
    } catch (err) { setError(err instanceof Error && !('status' in err) ? err.message : courseErrorMessage(err)) } finally { setBusy(false) }
  }
  async function submit() {
    if (busy) return
    setBusy(true); setError('')
    try {
      await persist()
      const active = current.current
      const data = await assessmentWrite(`${attemptPath(active.id)}submit/`, 'POST', { revision: active.revision, confirmed: true })
      accept(data); setConfirm(false)
    } catch (err) { setError(courseErrorMessage(err)) } finally { setBusy(false) }
  }
  useEffect(() => {
    mounted.current = true
    return () => { persist().catch(() => {}); mounted.current = false; onTestActive?.(false) }
    // Save current refs on leaving, not each render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  useEffect(() => {
    if (!version || !editable) return
    const timer = setTimeout(() => persist().catch((err) => { if (mounted.current) setError(courseErrorMessage(err)) }), 800)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version, editable])
  useEffect(() => {
    if (!editable) return
    let loading = false
    async function poll() {
      setNow(Date.now())
      const active = current.current
      if (!active || active.status !== 'DRAFT' || loading) return
      if (Date.now() + offset.current < new Date(active.expires_at).getTime()) return
      if (info.kind !== 'QUIZ') return
      loading = true
      try { await chain.current.catch(() => {}); accept(await getAssessment(attemptPath(active.id))) }
      catch (err) { if (mounted.current) setError(courseErrorMessage(err)) }
      finally { loading = false }
    }
    const timer = setInterval(poll, 1000)
    return () => clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editable, attempt?.id])
  useEffect(() => {
    function flush() { persist().catch(() => {}) }
    function protectUnsaved(event) {
      if (current.current?.status === 'DRAFT' && values.current.version > savedVersion.current) {
        flush()
        event.preventDefault()
        event.returnValue = ''
      }
    }
    function warn(kind) {
      const active = current.current
      if (!test || !active || active.status !== 'DRAFT') return
      setNotice(kind === 'TAB_HIDDEN' ? 'Bạn đã chuyển tab hoặc ẩn trang. Sự kiện được ghi lại để giáo viên xem xét.' : 'Bạn đã thoát toàn màn hình. Sự kiện được ghi lại để giáo viên xem xét.')
      assessmentWrite(`${attemptPath(active.id)}events/`, 'POST', { event_id: crypto.randomUUID(), kind }).catch(() => { if (mounted.current) setError('Không ghi được log vi phạm. Kiểm tra kết nối và tải lại bài.') })
    }
    function visibility() { if (document.visibilityState === 'hidden') { flush(); warn('TAB_HIDDEN') } }
    function screen() { const enabled = Boolean(document.fullscreenElement); setFullscreen(enabled); if (!enabled) warn('FULLSCREEN_EXIT') }
    document.addEventListener('visibilitychange', visibility)
    document.addEventListener('fullscreenchange', screen)
    window.addEventListener('pagehide', flush)
    window.addEventListener('beforeunload', protectUnsaved)
    return () => { document.removeEventListener('visibilitychange', visibility); document.removeEventListener('fullscreenchange', screen); window.removeEventListener('pagehide', flush); window.removeEventListener('beforeunload', protectUnsaved) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [test, path])
  useEffect(() => { if (!notice) return; const timer = setTimeout(() => setNotice(''), 5000); return () => clearTimeout(timer) }, [notice])
  const hasTestSubmission = test && info.attempts?.some((a) => a.status === 'SUBMITTED')
  const seconds = Math.ceil((new Date(attempt?.expires_at).getTime() - now - serverOffset)/1000)
  const deadlinePassed = now + serverOffset >= new Date(info.due_at).getTime()
  return <section className="assessment-runner" ref={root} aria-label="Làm bài tập">
    <header className="assessment-fullscreen-task"><div className="assessment-heading"><h2>{info.title}</h2><button type="button" className="outline-button" onClick={() => document.exitFullscreen?.().catch(() => setError('Không thể thoát toàn màn hình.'))}>Thoát toàn màn hình</button></div>{info.description && <p className="assessment-prewrap">{info.description}</p>}<p>Hạn nộp: {dateLabel(info.due_at)}</p></header>
    {error && <div className="error-banner" role="alert">{error}{attempt && <button type="button" className="outline-button" onClick={async () => { try { await chain.current.catch(() => {}); accept(await getAssessment(attemptPath(attempt.id)), true); setError('') } catch (err) { setError(courseErrorMessage(err)) } }}>Tải bản đã lưu</button>}</div>}
    {notice && <p className="assessment-notice" role="status">{notice}</p>}
    {!attempt ? <div className="assessment-start"><p>{test ? 'Bạn chỉ có một lượt làm/nộp. Cần vào toàn màn hình; chuyển tab hoặc thoát toàn màn hình sẽ được cảnh báo và ghi log cho giáo viên.' : 'Bạn có thể làm lại và chỉnh sửa trước hạn. Mỗi lượt nộp được lưu trong lịch sử.'}</p><button type="button" className="solid-button" disabled={busy || deadlinePassed || hasTestSubmission} onClick={start}>{test && <Expand size={18} />}{info.attempts?.some((a) => a.status === 'DRAFT') ? 'Tiếp tục bài làm' : hasTestSubmission ? 'Đã nộp bài kiểm tra' : 'Bắt đầu làm bài'}</button>{deadlinePassed && <p className="assessment-muted">Đã hết hạn nhận bài.</p>}</div> : <>
      <div className="assessment-attempt-heading"><strong>Lượt {attempt.number} · {editable ? 'Đang làm' : 'Đã nộp'}</strong>{editable && info.kind === 'QUIZ' && <time className={seconds < 60 ? 'assessment-time is-low' : 'assessment-time'}>Còn {remainingLabel(seconds)}</time>}{editable && <span className="assessment-muted">{saving ? 'Đang lưu...' : version > savedCount ? 'Có thay đổi chưa lưu' : 'Đã lưu bản nháp'}</span>}</div>
      {editable && test && !fullscreen && <div className="assessment-notice">Hãy trở lại toàn màn hình để tiếp tục đúng quy định.<button type="button" className="outline-button" onClick={() => root.current.requestFullscreen?.().catch(() => setError('Không thể mở toàn màn hình.'))}><Expand size={16} />Toàn màn hình</button></div>}
      {info.kind === 'QUIZ' ? <div className="assessment-questions">{(attempt.questions || info.questions).map((q, index) => <fieldset key={q.id} disabled={!editable || busy || expired}><legend>Câu {index + 1}</legend><small className="assessment-muted">{q.multiple ? 'Chọn các đáp án đúng' : 'Chọn một đáp án đúng'}</small><p className="assessment-prewrap">{q.prompt}</p>{q.choices.map((c) => <label key={c.id} className={`assessment-choice ${!editable && correctIds(q).includes(c.id) ? 'is-correct' : ''}`}><input type={q.multiple ? 'checkbox' : 'radio'} name={`${attempt.id}-${q.id}`} checked={answerIds((editable ? answers : attempt.answers)[q.id]).includes(c.id)} onChange={(event) => { const selected = answerIds(values.current.answers[q.id]); edit({ answers: { ...values.current.answers, [q.id]: q.multiple ? event.target.checked ? [...selected, c.id] : selected.filter((id) => id !== c.id) : c.id } }) }} />{c.text}{!editable && correctIds(q).includes(c.id) && <CheckCircle2 size={16} />}</label>)}{!test && q.hint && <details className="assessment-hint"><summary>Gợi ý</summary><p>{q.hint}</p></details>}</fieldset>)}</div> : <div className="assessment-text-work"><label>Bài làm tự luận<textarea rows={10} maxLength={50000} value={editable ? text : attempt.text} disabled={!editable || busy || expired || Boolean(file || (attempt.file_name && !removeFile))} placeholder="Nhập bài làm hoặc chọn một tệp bên dưới..." onChange={(e) => edit({ text: e.target.value })} /></label>
      {editable && <FilePicker label="Tệp bài làm (PDF, PNG, JPEG · tối đa 20 MiB)" file={file || (attempt.file_name && !removeFile ? { name: attempt.file_name } : null)} accept=".pdf,.png,.jpg,.jpeg" disabled={busy || expired || Boolean(text.trim())} onChange={(e) => { const next = e.target.files[0]; if (next && next.size > 20*1024*1024) { setError('Tệp tối đa 20 MiB.'); e.target.value = ''; return } edit({ file: next || null, removeFile: false }) }} />}
      {(file || attempt.file_name) && !removeFile && <div className="assessment-actions">{!editable && <span>{attempt.file_name}</span>}{editable ? <button type="button" className="outline-button" disabled={busy} onClick={() => edit({ file: null, removeFile: true })}>Bỏ tệp</button> : <button type="button" className="outline-button" onClick={() => downloadAssessmentFile(`${attemptPath(attempt.id)}file/`, attempt.file_name).catch((err) => setError(courseErrorMessage(err)))}><Download size={16} />Tải bài nộp</button>}</div>}</div>}
      {editable ? <div className="assessment-actions"><button type="button" className="outline-button" disabled={busy || expired} onClick={() => persist().then(() => setNotice('Đã lưu bản nháp.')).catch((err) => setError(courseErrorMessage(err)))}><Save size={17} />Lưu bản nháp</button><button type="button" className="solid-button" disabled={busy || expired} onClick={() => test ? setConfirm(true) : submit()}><Send size={17} />{busy ? 'Đang nộp...' : 'Nộp bài'}</button></div> : <div className="assessment-result"><strong>{attempt.score == null ? 'Đang chờ chấm hoặc công bố kết quả' : `Điểm: ${attempt.score}/10`}</strong>{attempt.feedback && <p className="assessment-prewrap">{attempt.feedback}</p>}<p>Nộp lúc {dateLabel(attempt.submitted_at)}</p>{!test && !deadlinePassed && <button className="outline-button" type="button" onClick={() => { setAttempt(null); current.current = null; startId.current = crypto.randomUUID() }}>Làm lại / chỉnh sửa bài</button>}</div>}
    </>}
    {!test && <aside className="assessment-assistance"><h3><Sparkles size={18} />Hỗ trợ ôn tập</h3>{info.hint && <p className="assessment-prewrap">{info.hint}</p>}<button type="button" className="outline-button" onClick={async () => { try { const data = await assessmentWrite(`${path}assistance/`, 'POST', {}); setHint(data.message) } catch (err) { setError(courseErrorMessage(err)) } }}>Trợ giúp AI</button>{hint && <p role="status">{hint}</p>}</aside>}
    {!editable && <div className="assessment-history"><h3>Lịch sử bài làm</h3>{!info.attempts?.length && <p className="assessment-muted">Chưa có lượt làm.</p>}{info.attempts?.map((a) => <button type="button" className="assessment-history-row" key={a.id} onClick={async () => { try { const data = await getAssessment(attemptPath(a.id)); if (data.status === 'DRAFT') { await start(); return } accept(data, true) } catch (err) { setError(courseErrorMessage(err)) } }}><span>Lượt {a.number} · {a.status === 'DRAFT' ? 'Đang làm' : dateLabel(a.submitted_at)}</span><strong>{a.score == null ? 'Chưa có điểm công bố' : `${a.score}/10`}</strong></button>)}</div>}
    {confirm && <VideoDialog title="Xác nhận nộp bài kiểm tra" pending={busy} onClose={() => setConfirm(false)}><p>Bạn chỉ được nộp chính thức một lần. Sau khi nộp, bạn không thể chỉnh sửa hoặc nộp lại bài này.</p>{error && <p role="alert" className="error-banner">{error}</p>}<div className="video-dialog-actions"><button type="button" className="outline-button" disabled={busy} onClick={() => setConfirm(false)}>Hủy</button><button type="button" className="solid-button" disabled={busy} onClick={submit}>Xác nhận nộp</button></div></VideoDialog>}
  </section>
}
