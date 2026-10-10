import { useEffect, useId, useRef } from 'react'
import { createPortal } from 'react-dom'
import { Trash2 } from 'lucide-react'

export default function MaterialRemoveDialog({ title, pending, error, onCancel, onConfirm, headingText = 'Gỡ học liệu?', descriptionText, confirmText = 'Xác nhận gỡ', pendingText = 'Đang gỡ…' }) {
  const heading = useId()
  const description = useId()
  const layer = useRef(null)
  const dialog = useRef(null)
  const state = useRef({ pending, onCancel })
  useEffect(() => { state.current = { pending, onCancel } }, [pending, onCancel])
  useEffect(() => {
    const previous = document.activeElement
    const overflow = document.body.style.overflow
    const siblings = [...document.body.children].filter((element) => element !== layer.current)
    const inert = siblings.map((element) => element.inert)
    siblings.forEach((element) => { element.inert = true })
    document.body.style.overflow = 'hidden'
    dialog.current.querySelector('button').focus()
    function keydown(event) {
      if (event.key === 'Escape') {
        event.preventDefault()
        if (!state.current.pending) state.current.onCancel()
      }
      if (event.key !== 'Tab') return
      const buttons = [...dialog.current.querySelectorAll('button:not(:disabled)')]
      if (!buttons.length) { event.preventDefault(); return }
      if (event.shiftKey && document.activeElement === buttons[0]) { event.preventDefault(); buttons.at(-1).focus() }
      else if (!event.shiftKey && document.activeElement === buttons.at(-1)) { event.preventDefault(); buttons[0].focus() }
    }
    document.addEventListener('keydown', keydown)
    return () => {
      document.removeEventListener('keydown', keydown)
      siblings.forEach((element, index) => { element.inert = inert[index] })
      document.body.style.overflow = overflow
      if (previous?.isConnected) previous.focus()
    }
  }, [])
  return createPortal(<div ref={layer} className="material-remove-layer" onClick={(event) => { if (event.target === event.currentTarget && !pending) onCancel() }}>
    <section ref={dialog} className="material-remove-dialog" role="dialog" aria-modal="true" aria-labelledby={heading} aria-describedby={description} aria-busy={pending}>
      <div className="material-remove-icon"><Trash2 size={26} /></div>
      <h2 id={heading}>{headingText}</h2>
      <p id={description}>{descriptionText || <>Bạn muốn gỡ học liệu <strong>{title}</strong>? Học viên sẽ không còn truy cập được học liệu này.</>}</p>
      {error && <p className="error-banner" role="alert">{error}</p>}
      <div className="material-remove-actions">
        <button type="button" className="outline-button" disabled={pending} onClick={onCancel}>Hủy</button>
        <button type="button" className="material-danger-button" disabled={pending} onClick={onConfirm}>{pending ? pendingText : confirmText}</button>
      </div>
    </section>
  </div>, document.body)
}
