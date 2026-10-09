import { useEffect, useId, useRef } from 'react'
import { FileCheck2, Upload } from 'lucide-react'
import '../file-picker.css'

export default function FilePicker({ label, accept, file, onChange, disabled = false, inputRef, id }) {
  const generatedId = useId()
  const localRef = useRef(null)
  const ref = inputRef || localRef
  useEffect(() => { if (!file && ref.current) ref.current.value = '' }, [file, ref])
  return <div className="file-picker-field">
    <label htmlFor={id || generatedId}>{label}</label>
    <div className={`file-picker ${disabled ? 'is-disabled' : ''} ${file ? 'has-file' : ''}`}>
      <span className="file-picker-icon" aria-hidden="true">{file ? <FileCheck2 size={22} /> : <Upload size={22} />}</span>
      <span className="file-picker-copy"><strong>{file?.name || 'Chưa chọn tệp'}</strong><small>{file ? 'Nhấn để chọn tệp khác' : 'Chọn tệp từ thiết bị của bạn'}</small></span>
      <span className="file-picker-action" aria-hidden="true">{file ? 'Đổi tệp' : 'Chọn tệp'}</span>
      <input ref={ref} id={id || generatedId} aria-label={label} type="file" accept={accept} disabled={disabled} onChange={onChange} />
    </div>
  </div>
}
