import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { ArrowLeft, BookOpen, Bot, Check, ChevronDown, ChevronRight, ClipboardList, FileText, LoaderCircle, Menu, Pencil, Plus, Sparkles, Video, X } from 'lucide-react'
import CourseDocuments from './documents/CourseDocuments'
import { courseErrorMessage, updateClassroomSession } from '../services/course.service'
import '../session-workspace.css'

export default function SessionWorkspace({ course, room, session, onBack, onSaved, canManage = true }) {
  const [title, setTitle] = useState(session.title)
  const [draft, setDraft] = useState(session.title)
  const [renaming, setRenaming] = useState(false)
  const [rows, setRows] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [cards, setCards] = useState([])
  const [expanded, setExpanded] = useState({ materials: true, videos: false, assignments: false })
  const [sidebar, setSidebar] = useState(() => window.innerWidth > 650)
  const [section, setSection] = useState('materials')
  const [assistant, setAssistant] = useState(false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [isDraft, setIsDraft] = useState(session.is_draft !== false)
  const menuTrigger = useRef(null)
  const aiTrigger = useRef(null)
  const content = useRef(null)
  const lock = useRef(false)
  const selectedCard = cards.find((card) => card.id === selectedId) || cards[0]
  const active = rows.find((row) => row.document_id === selectedCard?.id)
  const draftId = selectedCard?.draft ? selectedCard.id : undefined
  const receiveDocuments = useCallback((documents) => {
    setRows(documents)
    setCards((previous) => {
      const ids = new Set(documents.map((row) => row.document_id))
      const retained = previous.filter((card) => card.draft || ids.has(card.id))
      return [...retained, ...documents.filter((row) => !retained.some((card) => card.id === row.document_id)).map((row) => ({ id: row.document_id }))]
    })
  }, [])
  function uploaded(id, result) {
    setCards((previous) => previous.filter((card) => card.id !== result.document_id).map((card) => card.id === id ? { id: result.document_id } : card))
    setSelectedId((current) => current === id ? result.document_id : current)
  }
  function toggleCategory(name) {
    setExpanded((previous) => ({ ...previous, [name]: !previous[name] }))
    setSection(name)
  }
  useEffect(() => {
    const previous = document.body.style.overflow
    const appRoot = document.getElementById('root')
    const previousInert = appRoot?.inert
    if (appRoot) appRoot.inert = true
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = previous; if (appRoot) appRoot.inert = previousInert }
  }, [])
  async function saveTitle(event) {
    event.preventDefault()
    if (lock.current) return
    lock.current = true; setPending(true); setError('')
    try {
      const updated = await updateClassroomSession(course.id, room.id, session.id, { title: draft.trim() })
      setTitle(updated.title); setRenaming(false); onSaved?.(updated)
    } catch (err) { setError(courseErrorMessage(err)) }
    finally { lock.current = false; setPending(false) }
  }
  async function createSession() {
    if (lock.current || !isDraft) return
    lock.current = true; setPending(true); setError('')
    try {
      const updated = await updateClassroomSession(course.id, room.id, session.id, { is_draft: false })
      setIsDraft(updated.is_draft); onSaved?.(updated)
    }
    catch (err) { setError(courseErrorMessage(err)) }
    finally { lock.current = false; setPending(false) }
  }
  function addMaterial() {
    const id = `draft-${crypto.randomUUID()}`
    setCards((previous) => [...previous, { id, draft: true }])
    setSelectedId(id); setSection('materials')
    setExpanded((previous) => ({ ...previous, materials: true }))
    content.current?.scrollTo?.({ top: 0 })
  }
  return createPortal(<section className="session-workspace" aria-label="Chi tiết buổi học">
    <header className="session-topbar">
      <div className="session-topbar-title"><button type="button" className="session-icon-button" aria-label="Các buổi học" title="Quay lại các buổi học" onClick={onBack}><ArrowLeft size={21} /></button><button type="button" ref={menuTrigger} className="session-icon-button" aria-expanded={sidebar} aria-controls="session-content-navigation" aria-label="Ẩn hiện nội dung buổi học" title="Ẩn/hiện thanh nội dung" onClick={() => setSidebar(!sidebar)}><Menu size={21} /></button>{renaming ? <form className="session-name-form" onSubmit={saveTitle}><input autoFocus aria-label="Tên buổi học" value={draft} maxLength={255} disabled={pending} onChange={(event) => setDraft(event.target.value)} /><button className="session-icon-button" type="submit" disabled={pending} aria-label="Lưu tên buổi học"><Check size={20} /></button><button type="button" className="session-icon-button" aria-label="Hủy đổi tên" disabled={pending} onClick={() => setRenaming(false)}><X size={20} /></button></form> : <><h1>{title || 'Buổi học chưa đặt tên'}</h1>{canManage && isDraft && <span className="session-draft-tag">Bản nháp</span>}{canManage && <button type="button" className="session-icon-button" aria-label="Đổi tên buổi học" title="Đổi tên buổi học" onClick={() => { setDraft(title); setRenaming(true) }}><Pencil size={18} /></button>}</>}</div>
      <div className="session-topbar-actions"><button ref={aiTrigger} className="outline-button" type="button" aria-expanded={assistant} aria-controls="session-assistant" onClick={() => setAssistant((open) => !open)}><Sparkles size={18} />Trợ lý AI</button>{canManage && <button type="button" className="solid-button" title="Hoàn tất tạo buổi học" disabled={pending || !isDraft} onClick={createSession}>{pending ? <LoaderCircle className="spin" size={18} /> : <Check size={18} />}{isDraft ? 'Tạo buổi học' : 'Đã tạo buổi học'}</button>}</div>
    </header>
    <div className={`session-layout ${sidebar ? '' : 'sidebar-hidden'}`}>
      <div className="session-sidebar-slot" inert={!sidebar} aria-hidden={!sidebar}><nav id="session-content-navigation" className="session-content-sidebar" aria-label="Nội dung buổi học">
        <div className="session-sidebar-heading"><strong>NỘI DUNG BUỔI HỌC</strong><button type="button" className="session-icon-button" aria-label="Đóng thanh nội dung" title="Đóng thanh nội dung" onClick={() => { setSidebar(false); menuTrigger.current?.focus() }}><X size={18} /></button></div>
        <button type="button" className="session-category" aria-expanded={expanded.materials} onClick={() => toggleCategory('materials')}><BookOpen size={20} />Bài học{expanded.materials ? <ChevronDown size={18} /> : <ChevronRight size={18} />}</button>
        {expanded.materials && <div className="session-material-navigation">{cards.length ? cards.map((card) => {
          const name = card.draft ? 'Học liệu chưa đặt tên' : rows.find((row) => row.document_id === card.id)?.title
          return <button type="button" key={card.id} title={name} className={selectedCard?.id === card.id ? 'active' : ''} aria-current={selectedCard?.id === card.id ? 'page' : undefined} onClick={() => { setSelectedId(card.id); setSection('materials') }}><FileText size={18} /><span>{name}</span></button>
        }) : <p>Chưa có học liệu</p>}{canManage && <button type="button" className="session-add-material" title="Thêm học liệu" onClick={addMaterial}><Plus size={20} />Thêm học liệu</button>}</div>}
        <button type="button" className="session-category" aria-expanded={expanded.videos} onClick={() => toggleCategory('videos')}><Video size={20} />Video{expanded.videos ? <ChevronDown size={18} /> : <ChevronRight size={18} />}</button>
        {expanded.videos && <div className="session-material-navigation"><p>Chưa có video</p></div>}
        <button type="button" className="session-category" aria-expanded={expanded.assignments} onClick={() => toggleCategory('assignments')}><ClipboardList size={20} />Bài tập{expanded.assignments ? <ChevronDown size={18} /> : <ChevronRight size={18} />}</button>
        {expanded.assignments && <div className="session-material-navigation"><p>Chưa có bài tập</p></div>}
        <div className="session-sidebar-context"><span>{room.name}</span><small>{course.title}</small></div>
      </nav></div>
      <div ref={content} className="session-main-content">
        {error && <div className="error-banner" role="alert">{error}</div>}
        <div hidden={section !== 'materials'}><CourseDocuments courseId={course.id} sessionId={session.id} canManage={canManage} workspace selectedDocumentId={active?.document_id} draftId={draftId} onDraftUploaded={uploaded} onDocumentsChanged={receiveDocuments} /></div>
        {section !== 'materials' && <section className="session-content-placeholder">{section === 'videos' ? <Video size={38} /> : <ClipboardList size={38} />}<h2>{section === 'videos' ? 'Video buổi học' : 'Bài tập buổi học'}</h2><p>{section === 'videos' ? 'Chức năng video sẽ được bổ sung ở bước tiếp theo.' : 'Chức năng bài tập sẽ được bổ sung ở bước tiếp theo.'}</p></section>}
      </div>
    </div>
    <aside id="session-assistant" className={`class-assistant-panel session-assistant-panel ${assistant ? 'is-open' : 'is-closed'}`} aria-hidden={!assistant} inert={!assistant} aria-label="Trợ lý AI của buổi học"><div className="class-assistant-heading"><span><Bot size={24} /><strong>Trợ lý học tập</strong></span><button type="button" className="icon-button" aria-label="Đóng trợ lý AI" onClick={() => { setAssistant(false); aiTrigger.current?.focus() }}><X size={20} /></button></div><div className="class-assistant-scope"><BookOpen size={17} />{title || 'Buổi học chưa đặt tên'}</div><div className="class-assistant-empty"><Sparkles size={36} /><h3>Học cùng trợ lý của buổi học</h3><p>Hỏi đáp học liệu, nhận gợi ý và tóm tắt nội dung.</p><div className="class-assistant-state">Trợ lý AI chưa được kết nối.</div></div><div className="class-assistant-compose"><input aria-label="Câu hỏi cho trợ lý" placeholder="Trợ lý chưa sẵn sàng" disabled /><button type="button" className="solid-button" disabled>Gửi</button></div></aside>
  </section>, document.body)
}
