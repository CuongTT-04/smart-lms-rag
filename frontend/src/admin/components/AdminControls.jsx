import { useContext, useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { AlertCircle, ChevronLeft, ChevronRight, Eye, EyeOff, LoaderCircle, RefreshCw, X } from 'lucide-react'
import CustomSelect from '../../components/CustomSelect'
import { adminError } from '../services/admin.service'
import { FormValidationContext } from '../hooks/form-validation'
import { passwordError } from '../../utils/password'

export function ValidatedForm({ children, onSubmit, validate, ...props }) {
  const [errors, setErrors] = useState({})
  function submit(event) {
    event.preventDefault()
    const form = event.currentTarget
    const next = {}
    for (const input of form.querySelectorAll('input,textarea')) {
      if (input.disabled || input.type === 'hidden' || input.type === 'file') continue
      const label = input.labels?.[0]?.textContent?.trim().toLocaleLowerCase('vi') || 'thông tin'
      if (input.required && !input.value.trim()) next[input.id] = `Vui lòng nhập ${label}.`
      else if (input.value && input.type === 'email' && input.validity.typeMismatch) next[input.id] = 'Vui lòng nhập email hợp lệ.'
      else if (input.value && input.type === 'url' && input.validity.typeMismatch) next[input.id] = 'Vui lòng nhập đường dẫn hợp lệ.'
      else if (input.value && input.dataset.httpsOnly && !/^https:\/\//i.test(input.value)) next[input.id] = 'Vui lòng nhập đường dẫn nguồn bắt đầu bằng https://.'
      else if (input.value && input.autocomplete === 'new-password' && passwordError(input.value)) next[input.id] = passwordError(input.value)
    }
    setErrors(next)
    const extraValid = validate?.(form) !== false
    if (Object.keys(next).length || !extraValid) {
      const first = Object.keys(next)[0]
      if (first) [...form.querySelectorAll('input,textarea')].find(input => input.id === first)?.focus()
      return
    }
    onSubmit?.(event)
  }
  return <FormValidationContext.Provider value={errors}><form {...props} noValidate onSubmit={submit} onChange={event => {
    const id = event.target.id
    if (id) setErrors(old => { const next = { ...old }; delete next[id]; return next })
  }}>{children}</form></FormValidationContext.Provider>
}

export function SelectField({ label, value, onChange, options, disabled }) {
  const id = useId()
  return <div className="adm-field"><label htmlFor={id}>{label}</label><CustomSelect id={id} value={value} onChange={event => onChange(event.target.value)} disabled={disabled} aria-label={label}>{options.map(([key, text]) => <option key={key} value={key}>{text}</option>)}</CustomSelect></div>
}
export function Field({ label, ...props }) {
  const id = useId()
  const errors = useContext(FormValidationContext)
  const [visible, setVisible] = useState(false)
  const password = props.type === 'password'
  const error = errors[id]
  return <div className="adm-field"><label htmlFor={id}>{label}</label><div className={password ? 'adm-password-input' : 'adm-input-control'}><input id={id} {...props} type={password && visible ? 'text' : props.type} aria-invalid={Boolean(error)} aria-describedby={error ? `${id}-error` : undefined} />{password && <button type="button" className="adm-password-toggle" disabled={props.disabled} aria-label={`${visible ? 'Ẩn' : 'Hiện'} ${label.toLocaleLowerCase('vi')}`} aria-pressed={visible} title={`${visible ? 'Ẩn' : 'Hiện'} mật khẩu`} onClick={() => setVisible(value => !value)}>{visible ? <EyeOff size={18} aria-hidden="true" /> : <Eye size={18} aria-hidden="true" />}</button>}</div>{error && <p className="field-error" id={`${id}-error`}>{error}</p>}</div>
}
export function Status({ children, tone = '' }) { return <span className={`adm-status ${tone}`}>{children}</span> }
export function Feedback({ resource, empty = false, children }) {
  if (resource.loading) return <div className="adm-state" role="status"><LoaderCircle className="spin" size={22} /> Đang tải dữ liệu…</div>
  if (resource.error) return <div className="adm-state" role="alert"><AlertCircle size={25} /><p>{adminError(resource.error)}</p><button className="secondary-button" onClick={resource.refresh}><RefreshCw size={16} /> Thử lại</button></div>
  if (empty) return <div className="adm-state"><p>Chưa có kết quả phù hợp.</p><small>Thử thay đổi hoặc xóa bộ lọc.</small></div>
  return children
}
export function Pagination({ offset, count, onChange, size = 20 }) {
  return <div className="adm-pagination"><span>{count ? `${offset + 1}–${Math.min(offset + size, count)} / ${count} kết quả` : '0 kết quả'}</span><div><button aria-label="Trang trước" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - size))}><ChevronLeft size={18} /></button><button aria-label="Trang sau" disabled={offset + size >= count} onClick={() => onChange(offset + size)}><ChevronRight size={18} /></button></div></div>
}
export function Modal({ title, children, onClose, busy = false, wide = false }) {
  const ref = useRef(null)
  const titleId = useId()
  useEffect(() => {
    const prior = document.activeElement
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    ref.current?.querySelector('input, button, textarea')?.focus()
    return () => { document.body.style.overflow = overflow; prior?.focus?.() }
  }, [])
  function keyboard(event) {
    if (event.key === 'Escape') { event.stopPropagation(); if (!busy) onClose() }
    if (event.key !== 'Tab') return
    const nodes = [...ref.current.querySelectorAll('button:not(:disabled), input:not(:disabled), textarea:not(:disabled), a[href]')]
    const first = nodes[0], last = nodes.at(-1)
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
  }
  return createPortal(<div className="adm-modal-backdrop" onKeyDown={keyboard}><section ref={ref} className={`adm-modal ${wide ? 'wide' : ''}`} role="dialog" aria-modal="true" aria-labelledby={titleId}><header><h2 id={titleId}>{title}</h2><button type="button" aria-label="Đóng hộp thoại" disabled={busy} onClick={onClose}><X size={20} /></button></header>{children}</section></div>, document.body)
}
