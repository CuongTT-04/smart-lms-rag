import { useState } from 'react'
import { Eye, EyeOff, LockKeyhole } from 'lucide-react'

export default function AuthField({ name, label, value, onChange, error, hint, pending, password = false, icon: Icon, ...props }) {
  const [visible, setVisible] = useState(false)
  return <div className="form-field">
    <label htmlFor={name}>{label}</label>
    <div className={`input-wrap ${error ? 'input-invalid' : ''}`}>
      {password ? <LockKeyhole size={18} aria-hidden="true" /> : Icon ? <Icon size={18} aria-hidden="true" /> : null}
      <input {...props} id={name} name={name} value={value} onChange={onChange} disabled={pending}
        type={password ? visible ? 'text' : 'password' : props.type || 'text'}
        required={props.required ?? true} aria-invalid={Boolean(error)} aria-describedby={[hint && `${name}-hint`, error && `${name}-error`].filter(Boolean).join(' ') || undefined} />
      {password && <button className="icon-button password-toggle" type="button" disabled={pending} onClick={() => setVisible(!visible)}
        aria-label={`${visible ? 'Ẩn' : 'Hiện'} ${label.toLowerCase()}`} title={`${visible ? 'Ẩn' : 'Hiện'} ${label.toLowerCase()}`} aria-pressed={visible}>
        {visible ? <EyeOff size={18} /> : <Eye size={18} />}
      </button>}
    </div>
    {hint && <p className="password-hint" id={`${name}-hint`}>{hint}</p>}
    {error && <p className="field-error" id={`${name}-error`}>{error}</p>}
  </div>
}
