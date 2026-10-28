import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { ArrowLeft, BookOpen, Check, ChevronRight, ClipboardList, FileText, LoaderCircle, Menu, Pencil, Plus, Video, X } from 'lucide-react'
import CourseDocuments from './documents/CourseDocuments'
import SessionAssistant from './ai/SessionAssistant'
import AyoAvatar from './ai/AyoAvatar'
import CitationViewer from './ai/CitationViewer'
import { courseErrorMessage, updateClassroomSession } from '../services/course.service'
import '../session-workspace.css'
import { useHistoryState } from '../hooks/useHistoryState'
import NotificationBell from './notifications/NotificationBell'
import { listSessionVideos, videoPath } from '../services/video.service'
import SessionVideos from './videos/SessionVideos'
import { formatVideoTime } from './videos/videoTime'
import { assessmentPath, listAssessments } from '../services/assessment.service'
import SessionAssessments from './assessments/SessionAssessments'

function SidebarSection({ open, children }) {
  return <div className={`session-sidebar-section ${open ? 'is-open' : ''}`} aria-hidden={!open} inert={!open}><div className="session-section-content">{children}</div></div>
}

export default function SessionWorkspace({ course, room, session, onBack, onSaved, canManage = true }) {
  const [title, setTitle] = useState(session.title)
  const [draft, setDraft] = useState(session.title)
  const [renaming, setRenaming] = useState(false)
  const [rows, setRows] = useState([])
  const [selectedId, setSelectedId] = useHistoryState(`session.${session.id}.document`, null)
  const [cards, setCards] = useState([])
  const [sidebar, setSidebar] = useState(() => window.innerWidth > 650)
  const [section, setSection] = useHistoryState(`session.${session.id}.section`, 'materials')
  const [assessmentId, setAssessmentId] = useHistoryState(`session.${session.id}.assessment`, null)
  const [assessments, setAssessments] = useState([])
  const [assessmentError, setAssessmentError] = useState('')
  const [creatingAssessment, setCreatingAssessment] = useState(false)
  const [activeTest, setActiveTest] = useState(false)
  const [videoId, setVideoId] = useHistoryState(`session.${session.id}.video`, null)
  const [expanded, setExpanded] = useState(() => ({ materials: true, videos: section === 'videos', assignments: section === 'assignments' }))
  const [videos, setVideos] = useState([])
  const [uploadingVideo, setUploadingVideo] = useState(false)
  const [videosError, setVideosError] = useState('')
  const videosPath = videoPath(course.id, room.id, session.id)
  const assessmentsPath = assessmentPath(course.id, room.id, session.id)
  const testSelected = activeTest || (!canManage && section === 'assignments' && (assessments.find((a) => a.id === assessmentId) || assessments[0])?.mode === 'TEST')
  const refreshAssessments = useCallback(async (signal) => {
    try { const items = await listAssessments(assessmentsPath, signal); if (!signal?.aborted) { setAssessments(items); setAssessmentError('') } }
    catch (err) { if (!signal?.aborted) setAssessmentError(courseErrorMessage(err)) }
  }, [assessmentsPath])
  useEffect(() => {
    if (section !== 'assignments') return
    const controller = new AbortController()
    Promise.resolve().then(() => refreshAssessments(controller.signal))
    return () => controller.abort()
  }, [section, refreshAssessments])
  const refreshVideos = useCallback(async (signal) => {
    try { const items = await listSessionVideos(videosPath, signal); if (!signal?.aborted) { setVideos(items); setVideosError('') } }
    catch (err) { if (!signal?.aborted) setVideosError(courseErrorMessage(err)) }
  }, [videosPath])
  useEffect(() => {
    if (section !== 'videos') return
    const controller = new AbortController()
    Promise.resolve().then(() => refreshVideos(controller.signal))
    return () => controller.abort()
  }, [section, refreshVideos])
  const [assistant, setAssistant] = useState(false)
  const [assistantActions, setAssistantActions] = useState(null)
  const [citation, setCitation] = useState(null)
  const [exercise, setExercise] = useState(null)
  const currentAssessment = assessments.find((item) => item.id === assessmentId) || assessments[0]
  const currentExercise = section === 'assignments' && currentAssessment?.mode === 'PRACTICE' && currentAssessment.id === exercise?.assessment_id ? exercise : null
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
    const opening = !expanded[name]
    setExpanded((previous) => ({ ...previous, [name]: opening }))
    if (opening) setSection(name)
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
      <div className="session-topbar-actions"><NotificationBell /><button ref={aiTrigger} className="outline-button" type="button" disabled={testSelected} title={testSelected ? 'Không hỗ trợ AI trong chế độ Kiểm tra' : undefined} aria-expanded={assistant && !testSelected} aria-controls="session-assistant" onClick={() => setAssistant((open) => !open)}><AyoAvatar size={23} />Trợ lý Ayo</button>{canManage && <button type="button" className="solid-button" title="Hoàn tất tạo buổi học" disabled={pending || !isDraft} onClick={createSession}>{pending ? <LoaderCircle className="spin" size={18} /> : <Check size={18} />}{isDraft ? 'Tạo buổi học' : 'Đã tạo buổi học'}</button>}</div>
    </header>
    <div className={`session-layout ${sidebar ? '' : 'sidebar-hidden'}`}>
      <div className="session-sidebar-slot" inert={!sidebar} aria-hidden={!sidebar}><nav id="session-content-navigation" className="session-content-sidebar" aria-label="Nội dung buổi học">
        <div className="session-sidebar-heading"><strong>NỘI DUNG BUỔI HỌC</strong><button type="button" className="session-icon-button" aria-label="Đóng thanh nội dung" title="Đóng thanh nội dung" onClick={() => { setSidebar(false); menuTrigger.current?.focus() }}><X size={18} /></button></div>
        <div className="session-sidebar-body">
        <button type="button" className="session-category" aria-expanded={expanded.materials} onClick={() => toggleCategory('materials')}><BookOpen size={20} />Bài học<ChevronRight className="session-category-chevron" size={18} /></button>
        <SidebarSection open={expanded.materials}><div className="session-material-navigation">{cards.length ? cards.map((card) => {
          const name = card.draft ? 'Học liệu chưa đặt tên' : rows.find((row) => row.document_id === card.id)?.title
          return <button type="button" key={card.id} title={name} className={section === 'materials' && selectedCard?.id === card.id ? 'active' : ''} aria-current={section === 'materials' && selectedCard?.id === card.id ? 'page' : undefined} onClick={() => { setSelectedId(card.id); setSection('materials') }}><FileText size={18} /><span>{name}</span></button>
        }) : <p>Chưa có học liệu</p>}{canManage && <button type="button" className="session-add-material" title="Thêm học liệu" onClick={addMaterial}><Plus size={20} />Thêm học liệu</button>}</div></SidebarSection>
        <button type="button" className="session-category" aria-expanded={expanded.videos} onClick={() => toggleCategory('videos')}><Video size={20} />Video<ChevronRight className="session-category-chevron" size={18} /></button>
        <SidebarSection open={expanded.videos}><div className="session-material-navigation">{videos.map((item) => <button type="button" key={item.id} title={item.title} className={(videoId || videos[0]?.id) === item.id && section === 'videos' ? 'active' : ''} aria-current={(videoId || videos[0]?.id) === item.id && section === 'videos' ? 'page' : undefined} onClick={() => { setVideoId(item.id); setSection('videos') }}><Video size={18} /><span>{item.title}</span><small>{formatVideoTime(item.duration)}{canManage && !item.is_published ? ' · Bản nháp' : ''}</small></button>)}{!videos.length && <p>Chưa có video</p>}{canManage && <button type="button" className="session-add-material" title="Thêm video" onClick={() => { setSection('videos'); setUploadingVideo(true) }}><Plus size={20} />Thêm video</button>}</div></SidebarSection>
        <button type="button" className="session-category" aria-expanded={expanded.assignments} onClick={() => toggleCategory('assignments')}><ClipboardList size={20} />Bài tập<ChevronRight className="session-category-chevron" size={18} /></button>
        <SidebarSection open={expanded.assignments}><div className="session-material-navigation">{assessments.map((item) => <button key={item.id} type="button" title={item.title} className={section === 'assignments' && (assessmentId || assessments[0]?.id) === item.id ? 'active' : ''} aria-current={section === 'assignments' && (assessmentId || assessments[0]?.id) === item.id ? 'page' : undefined} onClick={() => { setAssessmentId(item.id); setSection('assignments') }}><ClipboardList size={18} /><span>{item.title}</span><small>{item.mode === 'TEST' ? 'Kiểm tra' : 'Ôn tập'}</small></button>)}{!assessments.length && <p>Chưa có bài tập</p>}{canManage && <button className="session-add-material" type="button" title="Thêm bài tập" onClick={() => { setSection('assignments'); setCreatingAssessment(true) }}><Plus size={20} />Thêm bài tập</button>}</div></SidebarSection>
        </div>
        <div className="session-sidebar-context"><span>{room.name}</span><small>{course.title}</small></div>
      </nav></div>
      <div ref={content} className="session-main-content">
        {error && <div className="error-banner" role="alert">{error}</div>}
        <div hidden={section !== 'materials'}><CourseDocuments courseId={course.id} sessionId={session.id} canManage={canManage} workspace selectedDocumentId={active?.document_id} draftId={draftId} onDraftUploaded={uploaded} onDocumentsChanged={receiveDocuments} /></div>
        {section === 'videos' && <SessionVideos path={videosPath} rows={videos} selectedId={videoId} canManage={canManage} listError={videosError} onRefresh={refreshVideos} onSelect={setVideoId} uploading={uploadingVideo} onUploadingChange={setUploadingVideo} />}
        {section === 'assignments' && <SessionAssessments path={assessmentsPath} rows={assessments} selectedId={assessmentId} canManage={canManage} onSelect={setAssessmentId} onRefresh={refreshAssessments} listError={assessmentError} creating={creatingAssessment} onCreatingChange={setCreatingAssessment} onTestActive={setActiveTest} onRequestAssistance={(value) => { setExercise(value); setAssistant(true) }} />}
      </div>
    </div>
    <aside id="session-assistant" className={`class-assistant-panel session-assistant-panel ${assistant && !testSelected ? 'is-open' : 'is-closed'}`} aria-hidden={!assistant || testSelected} inert={!assistant || testSelected} aria-label="Trợ lý Ayo — Bạn đồng hành học tập">
      <div className="class-assistant-heading">
        <span><AyoAvatar size={38} /><strong>Trợ lý Ayo</strong></span>
        <div className="session-assistant-heading-actions">
          <div ref={setAssistantActions} />
          <button type="button" className="icon-button" aria-label="Đóng ayo" onClick={() => { setAssistant(false); aiTrigger.current?.focus() }}><X size={20} /></button>
        </div>
      </div>
      <div className="class-assistant-scope"><BookOpen size={17} /><span title={active?.title || 'Chưa chọn học liệu'}>{active?.title || 'Chưa chọn học liệu'}</span></div>{!testSelected && <SessionAssistant visible={assistant} toolbarTarget={assistantActions} documentId={active?.document_id} documentVersion={active?.published_version_id || active?.version_id} requireDocument scope={{course_id:course.id,classroom_id:room.id,session_id:session.id}} exercise={currentExercise} onOpenCitation={setCitation} />}
    </aside>
    {citation && <CitationViewer key={`${citation.document_id}:${citation.version_id}:${citation.page_number}`} citation={citation} onClose={() => setCitation(null)} />}
  </section>, document.body)
}
