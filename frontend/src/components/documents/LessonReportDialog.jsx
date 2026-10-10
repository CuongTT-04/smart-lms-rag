import { useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Flag } from 'lucide-react'

export default function LessonReportDialog({ onCancel, onSubmit }) {
  const heading = useId()
  const dialog = useRef(null), layer = useRef(null), cancel = useRef(onCancel), lock = useRef(false)
  const [reason, setReason] = useState(''), [opinion, setOpinion] = useState('')
  const [pending, setPending] = useState(false), [error, setError] = useState('')
  useEffect(() => { cancel.current = onCancel }, [onCancel])
  useEffect(() => {
    const previous = document.activeElement, overflow = document.body.style.overflow
    const siblings = [...document.body.children].filter((node) => node !== layer.current)
    const inert = siblings.map((node) => node.inert)
    siblings.forEach((node) => { node.inert = true })
    document.body.style.overflow = 'hidden'
    dialog.current.querySelector('input').focus()
    function keydown(event) {
      if (event.key === 'Escape') { event.preventDefault(); if (!lock.current) cancel.current(); return }
      if (event.key !== 'Tab') return
      const nodes = [...dialog.current.querySelectorAll('input, textarea, button')].filter((node) => !node.disabled)
      if (!nodes.length) { event.preventDefault(); return }
      if (event.shiftKey && document.activeElement === nodes[0]) { event.preventDefault(); nodes.at(-1).focus() }
      else if (!event.shiftKey && document.activeElement === nodes.at(-1)) { event.preventDefault(); nodes[0].focus() }
    }
    document.addEventListener('keydown', keydown)
    return () => { document.removeEventListener('keydown', keydown); siblings.forEach((node, i) => { node.inert = inert[i] }); document.body.style.overflow = overflow; if (previous?.isConnected) previous.focus() }
  }, [])
  async function send(event) {
    event.preventDefault()
    if (lock.current || !reason.trim()) return
    lock.current = true; setPending(true); setError('')
    try { await onSubmit({ reason: reason.trim(), opinion: opinion.trim() }) }
    catch { setError('Không thể gửi báo cáo. Vui lòng thử lại.'); lock.current = false; setPending(false) }
  }
  return createPortal(<div ref={layer} className="material-remove-layer" onClick={(event) => { if (event.target === event.currentTarget && !lock.current) onCancel() }}>
    <section ref={dialog} className="material-remove-dialog lesson-report-dialog" role="dialog" aria-modal="true" aria-labelledby={heading} aria-busy={pending}>
      <div className="lesson-report-icon"><Flag size={26} /></div><h2 id={heading}>Báo cáo bài học</h2>
      <form onSubmit={send}>
        <label>Lý do<input value={reason} maxLength={300} required disabled={pending} onChange={(event) => setReason(event.target.value)} /></label>
        <label>Ý kiến của bạn<textarea value={opinion} maxLength={3000} disabled={pending} onChange={(event) => setOpinion(event.target.value)} /></label>
        {error && <p className="error-banner" role="alert">{error}</p>}
        <div className="material-remove-actions"><button type="submit" className="solid-button" disabled={pending || !reason.trim()}>{pending ? 'Đang gửi…' : 'Gửi'}</button><button type="button" className="outline-button" disabled={pending} onClick={onCancel}>Hủy</button></div>
      </form>
    </section>
  </div>, document.body)
}
