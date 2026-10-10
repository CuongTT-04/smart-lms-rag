import { useCallback, useEffect, useRef, useState } from 'react'
import { publishDocument, changeMaterialPolicy, removeDocument, replaceDocument, materialPdf } from '../../services/document.service'
import PdfViewer from './PdfViewer'
import FilePicker from '../FilePicker'
import MaterialRemoveDialog from './MaterialRemoveDialog'
import '../../documents.css'

export default function MaterialActions({ document,canManage=false,onUpdated,onRemoved,onView,downloadOnly=false }) {
  const [pending,setPending]=useState(false)
  const [error,setError]=useState('')
  const [confirmRemove,setConfirmRemove]=useState(false)
  const [file,setFile]=useState(null)
  const [view,setView]=useState(false)
  const operation=useRef(null)
  const locked=useRef(false)
  const live=useRef(true)
  useEffect(()=>{live.current=true;return ()=>{live.current=false}},[])
  // Effects in PdfViewer own and cancel its requests; action completions only update this document.
  const unavailable=useCallback((message)=>{setView(false);setError(message)},[])
  const protectedMaterial=(document.material_policy || 'PROTECTED')==='PROTECTED'
  const ready=['EXTRACTED','READY'].includes(document.extraction_status) && document.watermark_status==='READY'
  const currentPublished=document.is_published && (!document.published_version_id || document.published_version_id===document.version_id)
  const canDownload=canManage || (document.is_published && !protectedMaterial)
  async function act(task,removed=false) {
    if (locked.current) return
    locked.current=true
    setPending(true);setError('');setView(false)
    try {
      const result=await task()
      if (!live.current) return
      if (removed) onRemoved(document.document_id)
      else if (result) onUpdated(result)
    } catch (requestError) {
      if (!live.current) return
      if ([401,403,404].includes(requestError.status)) { setError('Học liệu không còn khả dụng hoặc bạn không có quyền.');onRemoved(document.document_id) }
      else setError(requestError.status===409 ? 'Dữ liệu đã thay đổi hoặc bản xem chưa sẵn sàng. Hãy làm mới danh sách.' : 'Không thể hoàn tất thao tác. Vui lòng thử lại.')
    } finally { locked.current=false; if (live.current) setPending(false) }
  }
  async function replace() {
    if (!file || !file.name.toLowerCase().endsWith('.pdf') || file.size>20*1024*1024) {setError('Chọn PDF tối đa 20 MiB.');return}
    if (!operation.current || operation.current.file!==file) operation.current={file,key:crypto.randomUUID()}
    await act(async()=>{
      const result=await replaceDocument(document.document_id,file,operation.current.key)
      if (live.current) {operation.current=null;setFile(null)}
      return result
    })
  }
  async function download() {
    if (pending) return
    setPending(true);setError('')
    let url
    try {
      const blob=await materialPdf(document.document_id,true,undefined,canManage ? document.version_id : undefined)
      if (!live.current) return
      url=URL.createObjectURL(blob)
      const link=window.document.createElement('a');link.href=url;link.download=document.file_name || 'hoc-lieu.pdf'
      window.document.body.append(link);link.click();link.remove()
    } catch {if (live.current) setError('Không thể tải PDF. Hãy làm mới để kiểm tra chính sách và quyền truy cập.')}
    finally { if (url) setTimeout(()=>URL.revokeObjectURL(url),1000);if (live.current) setPending(false) }
  }
  if (downloadOnly) return canDownload ? <div className="material-controls"><button type="button" className="outline-button" disabled={pending} onClick={download}>Tải PDF</button>{error && <p role="alert">{error}</p>}</div> : null
  return <div className="material-controls">
    <p>{document.is_published ? 'Đã công bố' : 'Chưa công bố'} · {protectedMaterial ? 'Bảo vệ: bản xem có watermark, không cho tải bản sạch' : 'Công khai học liệu: người có quyền khóa học được xem/tải bản sạch'}</p>
    <div className="material-actions">
      {(document.is_published || (canManage && ready)) && <button type="button" className="outline-button" disabled={pending} onClick={()=>onView ? onView() : setView(!view)}>Xem PDF</button>}
      {canDownload && <button type="button" className="outline-button" disabled={pending} onClick={download}>Tải PDF</button>}
      {canManage && <>
        <button type="button" className="outline-button" disabled={pending || (!currentPublished && !ready)} onClick={()=>act(()=>publishDocument(document.document_id,currentPublished ? null : document.version_id,!currentPublished))}>{currentPublished ? 'Thu hồi công bố' : 'Công bố phiên bản này'}</button>
        <button type="button" className="outline-button" disabled={pending} onClick={()=>act(()=>changeMaterialPolicy(document.document_id,protectedMaterial ? 'PUBLIC_DOWNLOAD' : 'PROTECTED',document.policy_revision || 1))}>{protectedMaterial ? 'Cho phép tải bản sạch' : 'Chuyển về bảo vệ'}</button>
        <button type="button" className="material-danger-button" disabled={pending} onClick={()=>{setError('');setConfirmRemove(true)}}>Gỡ học liệu</button>
      </>}
    </div>
    {canManage && <div className="material-replace"><FilePicker label={`PDF thay thế cho ${document.title}`} file={file} accept=".pdf,application/pdf" disabled={pending} onChange={(event)=>setFile(event.target.files[0] || null)} /><button type="button" className="outline-button" disabled={pending || !file} onClick={replace}>Thay bằng PDF này</button><p>Bản đang công bố được giữ đến khi bạn công bố phiên bản thay thế đã xử lý xong.</p></div>}
    {confirmRemove && <MaterialRemoveDialog title={document.title} pending={pending} error={error} onCancel={()=>{if (!locked.current) setConfirmRemove(false)}} onConfirm={()=>act(()=>removeDocument(document.document_id),true)} />}
    {error && !confirmRemove && <p role="alert">{error}</p>}
    {view && <PdfViewer key={`${document.policy_revision}:${document.published_version_id}`} document={document} showFeedback={!canManage} onClose={()=>setView(false)} onUnavailable={unavailable} />}
  </div>
}
