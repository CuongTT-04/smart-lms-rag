import { useEffect, useId, useState } from 'react'
import { Check, ChevronDown, LoaderCircle, School } from 'lucide-react'
import { listInstitutions } from '../services/institution.service'
import './institution-combobox.css'

const OTHER = { id: null, name: 'Chưa có trường trong danh sách', other: true }

export default function InstitutionCombobox({ value, onChange, error, disabled = false }) {
  const id = useId()
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [rows, setRows] = useState([])
  const [state, setState] = useState('idle')
  const [cursor, setCursor] = useState(-1)
  const [retry, setRetry] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const options = [...rows, OTHER]

  useEffect(() => {
    if (open && cursor >= 0) document.getElementById(`${id}-option-${cursor}`)?.scrollIntoView?.({ block: 'nearest' })
  }, [cursor, id, open])

  useEffect(() => {
    if (!open || disabled) return
    const controller = new AbortController()
    let active = true
    const timer = setTimeout(() => {
      listInstitutions(query, controller.signal).then(result => {
        if (!active) return
        setRows(result.results)
        setHasMore(Boolean(result.has_more))
        setState('ready')
      }).catch(() => {
        if (active) setState('error')
      })
    }, 300)
    return () => { active = false; clearTimeout(timer); controller.abort() }
  }, [query, open, disabled, retry])

  function start() {
    setRows([]); setState('loading'); setCursor(-1); setOpen(true)
  }

  function choose(option) {
    onChange(option); setOpen(false); setCursor(-1)
  }

  function keyDown(event) {
    if (event.key === 'Escape') { setOpen(false); return }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      if (!open) { start(); return }
      setCursor(previous => event.key === 'ArrowDown' ? (previous + 1) % options.length : (previous <= 0 ? options.length - 1 : previous - 1))
    } else if (event.key === 'Enter' && open) {
      event.preventDefault()
      if (cursor >= 0 && options[cursor]) choose(options[cursor])
    }
  }

  return <div className="form-field institution-picker" onBlur={event => {
    if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false)
  }}>
    <label htmlFor={id}>Trường đang công tác</label>
    <div className={`input-wrap ${error ? 'input-invalid' : ''}`}>
      <School size={18} aria-hidden="true" />
      <input id={id} name="institution_id" role="combobox" autoComplete="off" maxLength={100}
        aria-expanded={open} aria-controls={`${id}-options`} aria-autocomplete="list"
        aria-activedescendant={open && cursor >= 0 ? `${id}-option-${cursor}` : undefined}
        aria-invalid={Boolean(error)} aria-describedby={error ? `${id}-error` : undefined}
        placeholder="Tìm tên trường hoặc viết tắt" disabled={disabled}
        value={value ? value.name : query} onFocus={start} onKeyDown={keyDown}
        onChange={event => { setQuery(event.target.value); onChange(null); start() }} />
      {open && state === 'loading' ? <LoaderCircle size={18} className="spin" aria-hidden="true" /> : <ChevronDown size={18} aria-hidden="true" />}
    </div>
    {open && <div className="institution-results">
      <div className="institution-state" role="status" aria-live="polite">
        {state === 'loading' && 'Đang tìm trường…'}
        {state === 'error' && <>Không tải được danh sách. <button type="button" onClick={() => { setState('loading'); setRetry(n => n + 1) }}>Thử lại</button></>}
        {state === 'ready' && !rows.length && 'Không tìm thấy trường phù hợp.'}
        {state === 'ready' && hasMore && 'Nhập tên cụ thể hơn để tìm đúng trường.'}
      </div>
      <ul id={`${id}-options`} role="listbox" aria-label="Danh sách trường">
        {options.map((option, index) => <li key={option.id || 'other'} role="option"
          id={`${id}-option-${index}`} aria-selected={cursor === index}
          className={cursor === index ? 'institution-option active' : 'institution-option'}
          onPointerDown={event => event.preventDefault()} onClick={() => choose(option)}>
          <span><span className="institution-name">{option.name}</span>
            {!option.other && <small>{[option.campus || option.province, option.aliases?.join(', ')].filter(Boolean).join(' · ')}</small>}</span>
          {value && value.id === option.id && Boolean(value.other) === Boolean(option.other) && <Check size={16} aria-hidden="true" />}
        </li>)}
      </ul>
    </div>}
    {error && <p className="field-error" id={`${id}-error`}>{error}</p>}
  </div>
}
