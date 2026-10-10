import { useCallback, useEffect, useRef, useState } from 'react'
import '../../documents.css'
import MaterialActions from './MaterialActions'
import PdfViewer from './PdfViewer'
import FilePicker from '../FilePicker'
import { FileText } from 'lucide-react'
import { listDocuments, uploadDocument, documentStatus, retryDocument, documentExtraction, renameDocument } from '../../services/document.service'

const LABELS = { NOT_STARTED: 'Chưa xử lý', QUEUED: 'Đang chờ xử lý', PROCESSING: 'Đang trích xuất', EXTRACTED: 'Đã trích xuất', FAILED: 'Xử lý thất bại', READY: 'Đã trích xuất' }
const ERRORS = { OCR_REQUIRED: 'PDF cần OCR. Hãy tải bản có lớp văn bản.', TEXT_LAYER_REQUIRED: 'PDF không có lớp văn bản phù hợp.', TIMEOUT: 'Xử lý vượt thời gian cho phép.', WORKER_INTERRUPTED: 'Worker bị gián đoạn. Bạn có thể thử xử lý lại.', SOURCE_CHANGED: 'File nguồn đã thay đổi.', PAGE_LIMIT: 'PDF vượt 100 trang.', SIZE_LIMIT: 'PDF vượt 20 MiB.', ENCRYPTED_PDF: 'PDF được mã hóa.', INVALID_PDF: 'PDF hỏng hoặc không đọc được.' }
function message(error) {
  if (error.status === 401) return 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.'
  if (error.status === 404 || error.status === 403) return 'Học liệu không còn khả dụng hoặc bạn không có quyền truy cập.'
  if (error.status === 413) return 'Tài liệu vượt 20 MiB.'
  if (error.status === 415) return 'Chỉ nhận tài liệu PDF.'
  return ERRORS[error.data?.error?.code] || 'Không thể hoàn tất yêu cầu. Vui lòng thử lại.'
}

export default function CourseDocuments({ courseId, sessionId, canManage = false, workspace = false, selectedDocumentId, draftId, onDraftUploaded, onDocumentsChanged, refreshToken = 0 }) {
  const [documents, setDocuments] = useState([])
  const [loadedScope, setLoadedScope] = useState(null)
  const scope = `${courseId}:${sessionId || ''}:${refreshToken}`
  const loading = loadedScope !== scope
  const [forms, setForms] = useState({})
  const formKey = workspace ? draftId : 'course'
  const { file = null, title = '' } = forms[formKey] || {}
  function updateForm(values) { setForms((previous) => ({ ...previous, [formKey]: { ...previous[formKey], ...values } })) }
  const ordered = useCallback((rows) => workspace ? [...rows].reverse() : rows, [workspace])
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [inspection, setInspection] = useState(null)
  const [closedPreviewKey, setClosedPreviewKey] = useState(null)
  const operations = useRef(new Map())
  const retries = useRef(new Map())
  const input = useRef(null)
  const live = useRef(true)
  useEffect(() => { live.current = true; return () => { live.current = false } }, [])
  useEffect(() => {
    const controller = new AbortController()
    listDocuments(courseId, controller.signal, sessionId)
      .then((rows) => { if (!controller.signal.aborted) setDocuments(ordered(rows)) })
      .catch((requestError) => { if (!controller.signal.aborted) setError(message(requestError)) })
      .finally(() => { if (!controller.signal.aborted) setLoadedScope(scope) })
    return () => controller.abort()
  }, [courseId, sessionId, refreshToken, scope, ordered])
  useEffect(() => { onDocumentsChanged?.(documents) }, [documents, onDocumentsChanged])
  const currentDocument = draftId ? undefined : documents.find((document) => document.document_id === selectedDocumentId) || (selectedDocumentId ? undefined : documents[0])
  const currentReady = currentDocument && ['EXTRACTED', 'READY'].includes(currentDocument.extraction_status) && currentDocument.watermark_status === 'READY'
  const previewAvailable = currentDocument && (workspace ? currentReady : (currentDocument.is_published || currentReady))
  const previewKey = currentDocument ? `${currentDocument.document_id}:${currentDocument.version_id}:${currentDocument.policy_revision}:${currentDocument.published_version_id}` : ''
  const previewClosed = closedPreviewKey === previewKey
  const unavailablePreview = useCallback((text) => { setClosedPreviewKey(previewKey); setError(text) }, [previewKey])
  const visibleInspection = !workspace || inspection?.documentId === currentDocument?.document_id ? inspection : null
  const active = documents.filter((d) => ['QUEUED', 'PROCESSING'].includes(d.extraction_status)).map((d) => `${d.document_id}:${d.version_id}`).join(',')
  useEffect(() => {
    if (!active) return
    const controller = new AbortController()
    let timer
    async function poll() {
      const results = await Promise.allSettled(active.split(',').map(async (scope) => {
        const [id, version] = scope.split(':')
        return { id, status: await documentStatus(id, version, controller.signal) }
      }))
      if (controller.signal.aborted) return
      const statuses = new Map()
      let revoked = false
      for (const result of results) {
        if (result.status === 'fulfilled' && result.value.status) statuses.set(result.value.id, result.value.status)
        else if (result.status === 'rejected') {
          if ([401, 403, 404].includes(result.reason.status)) revoked = true
          setError(message(result.reason))
        }
      }
      if (revoked) { setDocuments([]); setInspection(null); return }
      setDocuments((previous) => previous.map((d) => {
        const status = statuses.get(d.document_id)
        return status?.version_id === d.version_id ? { ...d, ...status } : d
      }))
      timer = setTimeout(poll, 2000)
    }
    timer = setTimeout(poll, 2000)
    return () => { controller.abort(); clearTimeout(timer) }
  }, [active])
  function merge(result, name) {
    setDocuments((previous) => {
      const old = previous.find((d) => d.document_id === result.document_id)
      const row = { title: name, ...old, ...result }
      if (workspace) return old ? previous.map((d) => d.document_id === row.document_id ? row : d) : [...previous, row]
      return [row, ...previous.filter((d) => d.document_id !== row.document_id)]
    })
  }
  async function submit(event) {
    event.preventDefault()
    if (pending || loading || (workspace && !draftId)) return
    if (!file || !file.name.toLowerCase().endsWith('.pdf')) { setError('Vui lòng chọn tài liệu PDF.'); return }
    if (file.size > 20 * 1024 * 1024) { setError('Tài liệu vượt 20 MiB.'); return }
    const submittedKey = formKey
    const saved = operations.current.get(submittedKey)
    const operation = saved?.file === file && saved?.title === title ? saved : { file, title, key: crypto.randomUUID() }
    operations.current.set(submittedKey, operation)
    setPending(true); setError('')
    try {
      const result = await uploadDocument(courseId, file, title, operation.key, sessionId)
      if (!live.current) return
      const name = title || file.name
      merge(result, name); operations.current.delete(submittedKey)
      setForms((previous) => { const next = { ...previous }; delete next[submittedKey]; return next })
      if (workspace) onDraftUploaded?.(submittedKey, result)
      else if (input.current) input.current.value = ''
    } catch (requestError) { if (live.current) setError(message(requestError)) }
    finally { if (live.current) setPending(false) }
  }
  async function retry(document) {
    if (pending || loading) return
    if (!retries.current.has(document.version_id)) retries.current.set(document.version_id, crypto.randomUUID())
    setPending(true); setError('')
    try {
      const result = await retryDocument(document.document_id, document.version_id, retries.current.get(document.version_id))
      if (!live.current) return
      merge({ ...result, error_code: '' }, document.title); retries.current.delete(document.version_id)
    } catch (requestError) { if (live.current) setError(message(requestError)) }
    finally { if (live.current) setPending(false) }
  }
  async function refresh() {
    if (pending || loading) return
    setPending(true); setError(''); setInspection(null)
    try {
      const rows = await listDocuments(courseId, undefined, sessionId)
      if (live.current) setDocuments(ordered(rows))
    } catch (requestError) {
      if (live.current) {
        setError(message(requestError))
        if ([401,403,404].includes(requestError.status)) setDocuments([])
      }
    } finally { if (live.current) setPending(false) }
  }
  async function inspect(document) {
    if (pending || loading) return
    setPending(true); setError(''); setInspection(null)
    try {
      const result = await documentExtraction(document.document_id, document.version_id)
      if (live.current) setInspection({ documentId: document.document_id, title: document.title, pages: result.pages })
    } catch (requestError) {
      if (live.current) {
        setError(message(requestError))
        if ([401,403,404].includes(requestError.status)) setDocuments([])
      }
    } finally { if (live.current) setPending(false) }
  }
  async function rename(title) {
    const id = currentDocument.document_id
    const result = await renameDocument(id, title)
    if (!live.current) return
    merge(result, title)
    setInspection((previous) => previous?.documentId === id ? { ...previous, title: result.title } : previous)
  }
  return <section className={`materials-panel ${workspace ? 'session-materials-panel' : ''}`} aria-label={sessionId ? 'Học liệu buổi học' : 'Học liệu khóa học'}>
    {!(workspace && !canManage) && <><h2>{sessionId ? 'Học liệu buổi học' : 'Học liệu khóa học'}</h2><p>Tài liệu PDF được trích xuất theo trang. Học liệu mới mặc định có chính sách bảo vệ.</p>
    <button type="button" className="outline-button" disabled={pending || loading} onClick={refresh}>Làm mới danh sách</button></>}
    {canManage && (!workspace || draftId) && <form key={formKey} className="materials-upload" onSubmit={submit}>
      <label>Tên học liệu<input value={title} maxLength={255} onChange={(e) => updateForm({ title: e.target.value })} disabled={pending || loading} /></label>
      <FilePicker label="Tài liệu PDF" inputRef={input} file={file} accept=".pdf,application/pdf" onChange={(e) => updateForm({ file: e.target.files[0] || null })} disabled={pending || loading} />
      {file && <span className="material-selected-file">Đã chọn: {file.name}</span>}
      <span>PDF có lớp văn bản · Tối đa 20 MiB và 100 trang</span>
      <button className="solid-button" type="submit" disabled={pending || loading}>{pending ? 'Đang gửi yêu cầu…' : 'Tải tài liệu lên'}</button>
    </form>}
    {error && <p className="error-banner" role="alert">{error}</p>}
    {loading ? <p role="status">Đang tải học liệu…</p> : !canManage && documents.length === 0 && <p>Chưa có học liệu.</p>}
    {workspace && !draftId && <div className="session-pdf-preview" aria-label="Bản xem trước tài liệu">{previewAvailable && !previewClosed ? <PdfViewer key={previewKey} document={currentDocument} preferCurrent={canManage} annotatable showFeedback={!canManage} hideHeader={!canManage} onRename={canManage ? rename : undefined} onClose={() => setClosedPreviewKey(previewKey)} onUnavailable={unavailablePreview} /> : <div className="session-pdf-empty"><FileText size={44} /><h3>{canManage ? 'Bản xem trước tài liệu' : 'Học liệu chưa sẵn sàng'}</h3><p>{!canManage ? 'Vui lòng tải lại hoặc liên hệ với giáo viên' : currentDocument ? 'Nhấn Xem PDF khi bản xem đã sẵn sàng.' : 'Tải PDF lên để xem tài liệu tại đây.'}</p></div>}</div>}
    {workspace && !canManage && !loading && currentDocument && <MaterialActions key={previewKey} document={currentDocument} downloadOnly />}
    {!(workspace && !canManage) && <div className="materials-list">{(workspace ? documents.filter((document) => document.document_id === currentDocument?.document_id) : documents).map((document) => <article key={document.document_id} className="material-row">
      <h3>{document.title}</h3><p>{document.file_name || ''}{document.page_count ? ` · ${document.page_count} trang` : ''}</p>
      <div className="material-status-line"><strong role="status">{LABELS[document.extraction_status] || 'Chưa xử lý'}</strong>{canManage && ['EXTRACTED','READY'].includes(document.extraction_status) && <button className="outline-button" type="button" disabled={pending || loading} onClick={() => inspect(document)}>Kiểm tra trích xuất</button>}</div>
      {document.error_code && <p>{ERRORS[document.error_code] || 'Không thể trích xuất tài liệu.'}</p>}
      {canManage && document.extraction_status === 'FAILED' && <button className="outline-button" type="button" disabled={pending || loading} onClick={() => retry(document)}>Thử xử lý lại</button>}
      {canManage && ['EXTRACTED','READY'].includes(document.extraction_status) && document.watermark_status!=='READY' && <button className="outline-button" type="button" disabled={pending || loading} onClick={()=>retry(document)}>Tạo lại bản xem</button>}
      <MaterialActions document={document} onView={workspace ? () => setClosedPreviewKey(null) : undefined} canManage={canManage} onUpdated={(result)=>{setInspection(null);merge(result,document.title)}} onRemoved={(id)=>{setInspection(null);setDocuments((previous)=>previous.filter((row)=>row.document_id!==id))}} />
    </article>)}</div>}
    {visibleInspection && <section aria-label="Kết quả trích xuất" className="material-row extraction-result">
      <h3>{visibleInspection.title} — Kết quả trích xuất</h3>
      <button type="button" className="outline-button" onClick={() => setInspection(null)}>Đóng kết quả</button>
      <div className="extraction-scroll" tabIndex={0} aria-label="Văn bản trích xuất theo trang">{visibleInspection.pages.map((page) => <article key={page.page_number}><h4>Trang PDF {page.page_number}</h4><p style={{ whiteSpace:'pre-wrap', overflowWrap:'anywhere' }}>{page.text || 'Trang không có văn bản.'}</p></article>)}</div>
    </section>}
  </section>
}
