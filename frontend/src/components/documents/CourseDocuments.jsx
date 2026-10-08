import { useEffect, useRef, useState } from 'react'
import { listDocuments, uploadDocument, documentStatus, retryDocument, documentExtraction } from '../../services/document.service'

const LABELS = { NOT_STARTED: 'Chưa xử lý', QUEUED: 'Đang chờ xử lý', PROCESSING: 'Đang trích xuất', EXTRACTED: 'Đã trích xuất', FAILED: 'Xử lý thất bại', READY: 'Đã trích xuất' }
const ERRORS = { OCR_REQUIRED: 'PDF cần OCR. Hãy tải bản có lớp văn bản.', TEXT_LAYER_REQUIRED: 'PDF không có lớp văn bản phù hợp.', TIMEOUT: 'Xử lý vượt thời gian cho phép.', WORKER_INTERRUPTED: 'Worker bị gián đoạn. Bạn có thể thử xử lý lại.', SOURCE_CHANGED: 'File nguồn đã thay đổi.', PAGE_LIMIT: 'PDF vượt 100 trang.', SIZE_LIMIT: 'PDF vượt 20 MiB.', ENCRYPTED_PDF: 'PDF được mã hóa.', INVALID_PDF: 'PDF hỏng hoặc không đọc được.' }
function message(error) {
  if (error.status === 401) return 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.'
  if (error.status === 404 || error.status === 403) return 'Học liệu không còn khả dụng hoặc bạn không có quyền truy cập.'
  if (error.status === 413) return 'Tài liệu vượt 20 MiB.'
  if (error.status === 415) return 'Chỉ nhận tài liệu PDF.'
  return ERRORS[error.data?.error?.code] || 'Không thể hoàn tất yêu cầu. Vui lòng thử lại.'
}

export default function CourseDocuments({ courseId, canManage = false }) {
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(true)
  const [file, setFile] = useState(null)
  const [title, setTitle] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [inspection, setInspection] = useState(null)
  const operation = useRef(null)
  const retries = useRef(new Map())
  const input = useRef(null)
  const live = useRef(true)
  useEffect(() => { live.current = true; return () => { live.current = false } }, [])
  useEffect(() => {
    const controller = new AbortController()
    listDocuments(courseId, controller.signal)
      .then((rows) => { if (!controller.signal.aborted) setDocuments(rows) })
      .catch((requestError) => { if (!controller.signal.aborted) setError(message(requestError)) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [courseId])
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
    setDocuments((previous) => [{ title: name, ...previous.find((d) => d.document_id === result.document_id), ...result }, ...previous.filter((d) => d.document_id !== result.document_id)])
  }
  async function submit(event) {
    event.preventDefault()
    if (pending || loading) return
    if (!file || !file.name.toLowerCase().endsWith('.pdf')) { setError('Vui lòng chọn tài liệu PDF.'); return }
    if (file.size > 20 * 1024 * 1024) { setError('Tài liệu vượt 20 MiB.'); return }
    if (!operation.current || operation.current.file !== file || operation.current.title !== title) operation.current = { file, title, key: crypto.randomUUID() }
    setPending(true); setError('')
    try {
      const result = await uploadDocument(courseId, file, title, operation.current.key)
      if (!live.current) return
      merge(result, title || file.name); operation.current = null; setFile(null); setTitle('')
      if (input.current) input.current.value = ''
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
      const rows = await listDocuments(courseId)
      if (live.current) setDocuments(rows)
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
      if (live.current) setInspection({ title: document.title, pages: result.pages })
    } catch (requestError) {
      if (live.current) {
        setError(message(requestError))
        if ([401,403,404].includes(requestError.status)) setDocuments([])
      }
    } finally { if (live.current) setPending(false) }
  }
  return <section className="materials-panel" aria-label="Học liệu khóa học">
    <h2>Học liệu khóa học</h2><p>Tài liệu PDF được trích xuất theo trang. Học liệu mới mặc định có chính sách bảo vệ.</p>
    <button type="button" className="outline-button" disabled={pending || loading} onClick={refresh}>Làm mới danh sách</button>
    {canManage && <form className="materials-upload" onSubmit={submit}>
      <label>Tên học liệu<input value={title} maxLength={255} onChange={(e) => setTitle(e.target.value)} disabled={pending || loading} /></label>
      <label>Tài liệu PDF<input ref={input} type="file" accept=".pdf,application/pdf" onChange={(e) => setFile(e.target.files[0] || null)} disabled={pending || loading} /></label>
      <span>PDF có lớp văn bản · Tối đa 20 MiB và 100 trang</span>
      <button className="solid-button" type="submit" disabled={pending || loading}>{pending ? 'Đang gửi yêu cầu…' : 'Tải tài liệu lên'}</button>
    </form>}
    {error && <p className="error-banner" role="alert">{error}</p>}
    {loading ? <p role="status">Đang tải học liệu…</p> : documents.length === 0 && <p>Chưa có học liệu.</p>}
    <div className="materials-list">{documents.map((document) => <article key={document.document_id} className="material-row">
      <h3>{document.title}</h3><p>{document.file_name || ''}{document.page_count ? ` · ${document.page_count} trang` : ''}</p>
      <strong role="status">{LABELS[document.extraction_status] || 'Chưa xử lý'}</strong>
      {document.error_code && <p>{ERRORS[document.error_code] || 'Không thể trích xuất tài liệu.'}</p>}
      {canManage && document.extraction_status === 'FAILED' && <button className="outline-button" type="button" disabled={pending || loading} onClick={() => retry(document)}>Thử xử lý lại</button>}
      {canManage && ['EXTRACTED','READY'].includes(document.extraction_status) && <button className="outline-button" type="button" disabled={pending || loading} onClick={() => inspect(document)}>Kiểm tra trích xuất</button>}
    </article>)}</div>
    {inspection && <section aria-label="Kết quả trích xuất" className="material-row">
      <h3>{inspection.title} — Kết quả trích xuất</h3>
      <button type="button" className="outline-button" onClick={() => setInspection(null)}>Đóng kết quả</button>
      {inspection.pages.map((page) => <article key={page.page_number}><h4>Trang PDF {page.page_number}</h4><p style={{ whiteSpace:'pre-wrap', overflowWrap:'anywhere' }}>{page.text || 'Trang không có văn bản.'}</p></article>)}
    </section>}
  </section>
}
