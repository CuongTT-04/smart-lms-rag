import { useEffect, useState } from 'react'
import PdfCanvas from './PdfCanvas'
import { materialPdf, documentStatus } from '../../services/document.service'

export default function PdfViewer({ document, onClose, onRename, onUnavailable, preferCurrent = false }) {
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
    function valid(status) {
      return status.policy_revision===revision && status.material_policy===document.material_policy &&
        (status.published_version_id || null)===(document.published_version_id || null)
    }
    async function check() {
      try {
        const status=await documentStatus(document.document_id,version,controller.signal)
        if (controller.signal.aborted) return false
        if (!valid(status)) { onUnavailable('Học liệu hoặc chính sách đã thay đổi. Hãy làm mới danh sách.');return false }
        return true
      } catch {
        if (!controller.signal.aborted) onUnavailable('Học liệu không còn khả dụng. Hãy kiểm tra lại quyền truy cập.')
        return false
      }
    }
    async function watch() {
      if (await check()) timer=setTimeout(watch,2000)
    }
    async function load() {
      try {
        const blob=await materialPdf(document.document_id,false,controller.signal,preferCurrent ? version : undefined)
        if (controller.signal.aborted || !await check()) return
        objectUrl=URL.createObjectURL(blob);setError('');setUrl(objectUrl)
        timer=setTimeout(watch,2000)
      } catch {
        if (!controller.signal.aborted) setError('Không thể mở PDF. Bản xem có thể chưa sẵn sàng hoặc bạn đã mất quyền.')
      }
    }
    load()
    return ()=>{ controller.abort();clearTimeout(timer);if (objectUrl) URL.revokeObjectURL(objectUrl) }
  },[document.document_id,document.material_policy,document.published_version_id,version,revision,onUnavailable,preferCurrent])
  return <section aria-label="Xem PDF" className="material-viewer">
    <div className="material-actions"><h4>{document.title}</h4>{onRename ? <button type="button" className="outline-button" onClick={() => { setName(document.title); setRenameError(''); setRenaming(true) }}>Đổi tên</button> : <button type="button" className="outline-button" onClick={onClose}>Đóng PDF</button>}</div>
    {renaming && <form className="material-rename-form" onSubmit={saveName}>
      <label>Tên học liệu mới<input autoFocus value={name} maxLength={255} disabled={saving} onChange={(event) => setName(event.target.value)} /></label>
      <button type="submit" className="solid-button" disabled={saving || !name.trim()}>{saving ? 'Đang lưu…' : 'Lưu tên'}</button>
      <button type="button" className="outline-button" disabled={saving} onClick={() => setRenaming(false)}>Hủy</button>
      {renameError && <p role="alert">{renameError}</p>}
    </form>}
    {error ? <p role="alert">{error}</p> : url ? <PdfCanvas key={url} url={url} title={document.title} /> : <p role="status">Đang mở PDF…</p>}
  </section>
}
