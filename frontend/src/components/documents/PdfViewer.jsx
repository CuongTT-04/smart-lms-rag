import { useEffect, useState } from 'react'
import PdfCanvas from './PdfCanvas'
import { materialPdf, documentStatus } from '../../services/document.service'

export default function PdfViewer({ document, onClose, onRename, onUnavailable, preferCurrent = false, annotatable = true, hideHeader = false, showFeedback = true, initialPage = 1, expectedVersionId, onReady }) {
  const [url,setUrl]=useState('')
  const [error,setError]=useState('')
  const [renaming, setRenaming] = useState(false)
  const [name, setName] = useState(document.title)
  const [saving, setSaving] = useState(false)
  const [renameError, setRenameError] = useState('')
  async function saveName(event) {
    event.preventDefault()
    if (saving || !name.trim()) return
    setSaving(true); setRenameError('')
    try { await onRename(name.trim()); setRenaming(false) }
    catch { setRenameError('Không thể đổi tên học liệu. Vui lòng thử lại.') }
    finally { setSaving(false) }
  }
  const version=preferCurrent ? document.version_id : (document.published_version_id || document.version_id)
  const revision=document.policy_revision || 1
  useEffect(()=>{
    const controller=new AbortController()
    let objectUrl, timer
    function unavailable(message) {
      if (objectUrl) { URL.revokeObjectURL(objectUrl); objectUrl = null }
      setUrl(''); setError(message)
      onUnavailable(message)
    }
    function valid(status) {
      return status.policy_revision===revision && status.material_policy===document.material_policy &&
        (status.published_version_id || null)===(document.published_version_id || null)
    }
    async function check() {
      try {
        const status=await documentStatus(document.document_id,version,controller.signal)
        if (controller.signal.aborted) return false
        if (!valid(status)) { unavailable('Học liệu hoặc chính sách đã thay đổi. Hãy làm mới danh sách.');return false }
        return true
      } catch (failure) {
        if (!controller.signal.aborted) unavailable([401,403,404].includes(failure.status)
          ? 'Học liệu không còn khả dụng. Hãy kiểm tra lại quyền truy cập.'
          : 'Chưa kiểm tra được học liệu do lỗi kết nối máy chủ. Vui lòng tải lại sau.')
        return false
      }
    }
    async function watch() {
      if (await check()) timer=setTimeout(watch,2000)
    }
    async function load() {
      try {
        if (expectedVersionId && version !== expectedVersionId) {
          onUnavailable('Nguồn trích dẫn đã thay đổi phiên bản.');return
        }
        const blob=await materialPdf(document.document_id,false,controller.signal,preferCurrent ? version : undefined,...(expectedVersionId ? [expectedVersionId] : []))
        if (controller.signal.aborted || !await check()) return
        objectUrl=URL.createObjectURL(blob);setError('');setUrl(objectUrl)
        timer=setTimeout(watch,2000)
      } catch (failure) {
        if (!controller.signal.aborted) setError([401,403,404].includes(failure.status)
          ? 'Không thể mở PDF. Học liệu không khả dụng hoặc bạn không có quyền.'
          : 'Không thể mở PDF lúc này. Vui lòng tải lại hoặc kiểm tra kết nối máy chủ.')
      }
    }
    load()
    return ()=>{ controller.abort();clearTimeout(timer);if (objectUrl) URL.revokeObjectURL(objectUrl) }
  },[document.document_id,document.material_policy,document.published_version_id,version,revision,onUnavailable,preferCurrent,expectedVersionId])
  return <section aria-label="Xem PDF" className="material-viewer">
    {!hideHeader && <div className="material-actions"><h4>{document.title}</h4>{onRename ? <button type="button" className="outline-button" onClick={() => { setName(document.title); setRenameError(''); setRenaming(true) }}>Đổi tên</button> : <button type="button" className="outline-button" onClick={onClose}>Đóng PDF</button>}</div>}
    {renaming && <form className="material-rename-form" onSubmit={saveName}>
      <label>Tên học liệu mới<input autoFocus value={name} maxLength={255} disabled={saving} onChange={(event) => setName(event.target.value)} /></label>
      <button type="submit" className="solid-button" disabled={saving || !name.trim()}>{saving ? 'Đang lưu…' : 'Lưu tên'}</button>
      <button type="button" className="outline-button" disabled={saving} onClick={() => setRenaming(false)}>Hủy</button>
      {renameError && <p role="alert">{renameError}</p>}
    </form>}
    {error ? <p role="alert">{error}</p> : url ? <PdfCanvas onReady={onReady} initialPage={initialPage} allowCopy={document.material_policy === 'PUBLIC_DOWNLOAD'} key={`${url}:${initialPage}`} url={url} title={document.title} annotatable={annotatable} showFeedback={showFeedback} documentId={document.document_id} versionId={version} /> : <p role="status">Đang mở PDF…</p>}
  </section>
}
