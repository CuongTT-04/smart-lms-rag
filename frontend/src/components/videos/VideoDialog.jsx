import { useEffect, useId, useRef } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'

export default function VideoDialog({ title, pending, onClose, children, className = '' }) {
  const label = useId()
  const box = useRef(null)
  const close = useRef({ pending, onClose })
  useEffect(() => { close.current = { pending, onClose } }, [pending, onClose])
  useEffect(() => {
    const previous = document.activeElement
    box.current?.querySelector('input,textarea,button')?.focus()
    function key(event) {
      if (event.key === 'Escape' && !close.current.pending) close.current.onClose()
      if (event.key !== 'Tab') return
      const controls = [...box.current.querySelectorAll('button:not(:disabled), input:not(:disabled),textarea:not(:disabled),[tabindex="0"]')].filter((element) => element.getClientRects().length)
      if (!controls.length) return
      if (event.shiftKey && document.activeElement === controls[0]) { event.preventDefault(); controls.at(-1).focus() }
      else if (!event.shiftKey && document.activeElement === controls.at(-1)) { event.preventDefault(); controls[0].focus() }
    }
    document.addEventListener('keydown', key)
    return () => { document.removeEventListener('keydown', key); if (previous?.isConnected) previous.focus() }
  }, [])
  return createPortal(<div className="video-dialog-layer" onClick={(event) => { if (event.target === event.currentTarget && !pending) onClose() }}><section className={`video-dialog ${className}`} role="dialog" aria-modal="true" aria-labelledby={label} ref={box}><header><h2 id={label}>{title}</h2><button type="button" className="icon-button" aria-label="Đóng hộp thoại" disabled={pending} onClick={onClose}><X size={20} /></button></header>{children}</section></div>, document.fullscreenElement || document.body)
}
