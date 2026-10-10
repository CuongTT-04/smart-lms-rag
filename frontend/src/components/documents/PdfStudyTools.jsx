import { useEffect, useRef, useState } from 'react'
import { Eraser, Flag, Hand, Highlighter, Maximize2, MousePointer2, NotebookPen, PenLine, ThumbsDown, ThumbsUp, Trash2, Type, Undo2 } from 'lucide-react'
import { readStudyNotes, writeStudyNotes } from '../../services/document.service'
import MaterialRemoveDialog from './MaterialRemoveDialog'
import LessonReportDialog from './LessonReportDialog'

export default function PdfStudyTools({ enabled, children, ...props }) {
  return enabled ? <StudyTools {...props}>{children}</StudyTools> : children({ toolbar: null, overlay: null, notes: null, tool: 'pointer' })
}
function StudyTools({ documentId, versionId, pageNumber, ratio = 1, ready, readerRef, showFeedback = true, children }) {
  const [value, setValue] = useState({ items: [], notes: '' })
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [tool, setTool] = useState('pointer')
  const [stroke, setStroke] = useState(null)
  const [textPosition, setTextPosition] = useState(null)
  const [text, setText] = useState('')
  const [notesOpen, setNotesOpen] = useState(false)
  const [confirm, setConfirm] = useState(false)
  const [reportOpen, setReportOpen] = useState(false)
  const [historySize, setHistorySize] = useState(0)
  const history = useRef([]), current = useRef(value), live = useRef(false), drawing = useRef(null), editNumber = useRef(0), overlayRef = useRef(null)
  useEffect(() => {
    live.current = true
    const controller = new AbortController()
    readStudyNotes(documentId, versionId, controller.signal).then((saved) => {
      if (!controller.signal.aborted) { current.current = saved; setValue(saved); setLoaded(true) }
    }).catch(() => { if (!controller.signal.aborted) setError('Không thể tải ghi chú. Hãy mở lại học liệu.') })
    return () => { live.current = false; controller.abort() }
  }, [documentId, versionId])
  function persist(next) {
    const number = ++editNumber.current
    setSaving(true); setError('')
    writeStudyNotes(documentId, versionId, next).then(() => {
      if (live.current && number === editNumber.current) setSaving(false)
    }).catch((failure) => {
      if (live.current && number === editNumber.current) {
        setSaving(false)
        if (failure.status === 409) { setLoaded(false); setError('Phiên làm việc đã thay đổi. Hãy mở lại học liệu.') }
        else setError('Chưa lưu được thay đổi. Vui lòng thử lại.')
      }
    })
  }
  function change(next, remember = true) {
    if (remember) { history.current = [...history.current.slice(-49), current.current]; setHistorySize(history.current.length) }
    current.current = next; setValue(next); persist(next)
  }
  function undo() {
    if (!history.current.length) return
    const previous = history.current.pop()
    setHistorySize(history.current.length); change({ ...previous, ...(current.current.feedback ? { feedback: current.current.feedback } : {}) }, false)
  }
  async function report(reportValue) {
    const next = { ...current.current, feedback: { vote: current.current.feedback?.vote || 'none', report: reportValue } }
    await writeStudyNotes(documentId, versionId, next)
    if (live.current) { current.current = next; setValue(next); setReportOpen(false) }
  }
  function vote(choice) {
    const feedback = current.current.feedback || { vote: 'none' }
    change({ ...current.current, feedback: { ...feedback, vote: feedback.vote === choice ? 'none' : choice } }, false)
  }
  function point(event) {
    const bounds = overlayRef.current.getBoundingClientRect()
    return [Math.min(1, Math.max(0, (event.clientX - bounds.left) / bounds.width)), Math.min(1, Math.max(0, (event.clientY - bounds.top) / bounds.height))]
  }
  function start(event) {
    if (!loaded || !ready || ['pointer', 'hand'].includes(tool) || event.button !== 0) return
    event.preventDefault()
    const [x, y] = point(event)
    if (tool === 'text') { setText(''); setTextPosition({ x, y, page: pageNumber }); return }
    if (tool === 'eraser') {
      const id = event.target.dataset.annotationId
      if (id) change({ ...current.current, items: current.current.items.filter((item) => item.id !== id) })
      return
    }
    event.currentTarget.setPointerCapture?.(event.pointerId)
    drawing.current = { id: crypto.randomUUID(), page: pageNumber, kind: tool, points: [[x, y]] }; setStroke(drawing.current)
  }
  function move(event) {
    if (!drawing.current || drawing.current.points.length >= 2000) return
    drawing.current = { ...drawing.current, points: [...drawing.current.points, point(event)] }; setStroke(drawing.current)
  }
  function finish() {
    if (!drawing.current) return
    if (drawing.current.points.length === 1) drawing.current.points.push(drawing.current.points[0])
    change({ ...current.current, items: [...current.current.items, drawing.current] }); drawing.current = null; setStroke(null)
  }
  async function fullscreen() {
    try { if (document.fullscreenElement) await document.exitFullscreen(); else await readerRef.current?.requestFullscreen() }
    catch { setError('Trình duyệt chưa cho phép mở toàn màn hình.') }
  }
  const disabled = !loaded || !ready
  const controls = [['pointer', 'Con trỏ', MousePointer2], ['hand', 'Bàn tay', Hand], ['pen', 'Bút viết tay', PenLine], ['highlight', 'Tô highlight', Highlighter], ['eraser', 'Tẩy', Eraser], ['text', 'Viết text', Type]]
  const toolbar = <div className="pdf-study-toolbar" role="toolbar" aria-label="Công cụ học tập">
    {controls.map(([id, label, Icon]) => <button type="button" className={`icon-button ${tool === id ? 'is-active' : ''}`} key={id} aria-label={label} title={label} aria-pressed={tool === id} disabled={disabled} onClick={() => { setTool(id); drawing.current = null; setStroke(null) }}><Icon size={18} /></button>)}
    <button type="button" className="icon-button" aria-label="Undo" title="Hoàn tác" disabled={disabled || !historySize} onClick={undo}><Undo2 size={18} /></button>
    <button type="button" className="icon-button pdf-study-clear" aria-label="Xóa toàn bộ" title="Xóa toàn bộ nét vẽ và text" disabled={disabled || !value.items.length} onClick={async () => { if (document.fullscreenElement) await document.exitFullscreen(); setConfirm(true) }}><Trash2 size={18} /></button>
    <button type="button" className="icon-button" aria-label="Toàn màn hình" title="Bật/tắt toàn màn hình" disabled={disabled} onClick={fullscreen}><Maximize2 size={18} /></button>
    <button type="button" className={`icon-button ${notesOpen ? 'is-active' : ''}`} aria-label="Ghi chú" title="Ghi chú" disabled={!loaded} aria-expanded={notesOpen} onClick={() => setNotesOpen(!notesOpen)}><NotebookPen size={18} /></button>
  </div>
  const height = ratio * 1000
  const overlay = <svg ref={overlayRef} className={`pdf-study-overlay tool-${tool}`} aria-label="Lớp ghi chú trên tài liệu" viewBox={`0 0 1000 ${height}`} preserveAspectRatio="none" style={{ pointerEvents: ['pointer', 'hand'].includes(tool) || disabled ? 'none' : 'auto' }} onPointerDown={start} onPointerMove={move} onPointerUp={finish} onPointerCancel={() => { drawing.current = null; setStroke(null) }}>
    {[...value.items.filter((item) => item.page === pageNumber), ...(stroke?.page === pageNumber ? [stroke] : [])].map((item) => item.kind === 'text' ? <text key={item.id} data-annotation-id={item.id} x={item.x * 1000} y={item.y * height} fill="#234e3c" fontSize="30" dominantBaseline="hanging">{item.text}</text> : <g key={item.id}>
      <polyline data-annotation-id={item.id} points={item.points.map(([x, y]) => `${x * 1000},${y * height}`).join(' ')} fill="none" stroke={item.kind === 'highlight' ? '#f6d34d' : '#234e3c'} strokeOpacity={item.kind === 'highlight' ? '.4' : '1'} strokeWidth={item.kind === 'highlight' ? 28 : 4} strokeLinecap="round" strokeLinejoin="round" />
      {tool === 'eraser' && <polyline data-annotation-id={item.id} points={item.points.map(([x, y]) => `${x * 1000},${y * height}`).join(' ')} fill="none" stroke="transparent" strokeWidth="30" />}
    </g>)}
  </svg>
  const notes = <>
    {showFeedback && <div className="pdf-study-feedback" aria-busy={saving}><strong>Nội dung này có hữu ích không?</strong><button type="button" className={`icon-button ${value.feedback?.vote === 'like' ? 'is-active' : ''}`} aria-label="Like" title="Hữu ích" aria-pressed={value.feedback?.vote === 'like'} disabled={!loaded} onClick={() => vote('like')}><ThumbsUp size={20} /></button><button type="button" className={`icon-button ${value.feedback?.vote === 'dislike' ? 'is-active' : ''}`} aria-label="Unlike" title="Không hữu ích" aria-pressed={value.feedback?.vote === 'dislike'} disabled={!loaded} onClick={() => vote('dislike')}><ThumbsDown size={20} /></button><button type="button" className={`icon-button ${value.feedback?.report ? 'is-active' : ''}`} aria-label="Báo cáo bài học" title="Báo cáo bài học" disabled={!loaded} onClick={async () => { if (document.fullscreenElement) await document.exitFullscreen(); setReportOpen(true) }}><Flag size={20} /></button></div>}
    {error && <div className="pdf-study-status" role="alert">{error}{loaded && <button type="button" className="text-button" onClick={() => persist(current.current)}>Thử lưu lại</button>}</div>}
    {reportOpen && <LessonReportDialog onCancel={() => setReportOpen(false)} onSubmit={report} />}
    {notesOpen && <section className="pdf-study-notes"><label>Ghi chú của tôi<textarea disabled={!loaded} value={value.notes} maxLength={20000} placeholder="Viết ghi chú cho học liệu này..." onChange={(event) => change({ ...current.current, notes: event.target.value })} /></label></section>}
    {textPosition && <div className="pdf-study-text-editor"><form onSubmit={(event) => { event.preventDefault(); if (!text.trim()) return; change({ ...current.current, items: [...current.current.items, { id: crypto.randomUUID(), kind: 'text', ...textPosition, text: text.trim() }] }); setTextPosition(null) }}><label>Text trên tài liệu<input autoFocus maxLength={2000} value={text} onChange={(event) => setText(event.target.value)} /></label><button className="solid-button" type="submit" disabled={!text.trim()}>Thêm text</button><button className="outline-button" type="button" onClick={() => setTextPosition(null)}>Hủy</button></form></div>}
    {confirm && <MaterialRemoveDialog title="nét vẽ và text" headingText="Xóa toàn bộ?" descriptionText="Xóa toàn bộ nét vẽ, highlight và text trên các trang của học liệu này? Ghi chú trong sổ vẫn được giữ." confirmText="Xác nhận xóa" pendingText="Đang xóa…" pending={false} onCancel={() => setConfirm(false)} onConfirm={() => { change({ ...current.current, items: [] }); setConfirm(false) }} />}
  </>
  return children({ toolbar, overlay, notes, tool })
}
