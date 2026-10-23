import { useCallback, useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { documentStatus } from '../../services/document.service'
import PdfViewer from '../documents/PdfViewer'
import './assistant.css'

export default function CitationViewer({ citation, onClose }) {
  const [row, setRow] = useState(null)
  const [error, setError] = useState('')
  const close = useRef(null)
  useEffect(() => {
    const previous = document.activeElement
    close.current?.focus()
    const controller = new AbortController()
    documentStatus(citation.document_id, citation.version_id, controller.signal).then((status) => {
      if (controller.signal.aborted) return
      if (status.published_version_id !== citation.version_id || status.version_id !== citation.version_id ||
        !Number.isInteger(citation.page_number) || citation.page_number < 1 || citation.page_number > status.page_count) {
        setError('Nguồn trích dẫn không còn khả dụng hoặc đã thay đổi phiên bản.');return
      }
      setRow({ ...status, document_id: citation.document_id, title: citation.document_title })
    }).catch(() => { if (!controller.signal.aborted) setError('Nguồn trích dẫn không còn khả dụng hoặc bạn đã mất quyền truy cập.') })
    return () => { controller.abort(); previous?.focus() }
  }, [citation])
  const unavailable = useCallback((text) => { setError(text); setRow(null) }, [])
  function trap(event) {
    if (event.key === 'Escape') { event.stopPropagation(); onClose(); return }
    if (event.key !== 'Tab') return
    const buttons = [...event.currentTarget.querySelectorAll('button:not(:disabled),input:not(:disabled),textarea:not(:disabled),select:not(:disabled),[tabindex="0"]')]
    const first=buttons[0], last=buttons.at(-1)
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
  }
  return <div className="ai-citation-backdrop"><section className="ai-citation-dialog" role="dialog" aria-modal="true" aria-label={`Nguồn: ${citation.document_title}`} onKeyDown={trap}>
    <header><h2>{citation.document_title} — trang {citation.page_number}</h2><button ref={close} type="button" className="icon-button" aria-label="Đóng nguồn trích dẫn" onClick={onClose}><X size={20} /></button></header>
    {error ? <p role="alert" className="error-banner">{error}</p> : row ? <PdfViewer document={row} initialPage={citation.page_number} expectedVersionId={citation.version_id} onUnavailable={unavailable} onClose={onClose} /> : <p role="status">Đang kiểm tra nguồn trích dẫn…</p>}
  </section></div>
}
