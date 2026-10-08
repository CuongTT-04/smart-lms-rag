import { Children, isValidElement, useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Check, ChevronDown } from 'lucide-react'

export default function CustomSelect({ children, value, onChange, disabled = false, id, name, 'aria-label': label }) {
  const generatedId = useId()
  const controlId = id || `select-${generatedId}`
  const listId = `${controlId}-options`
  const options = Children.toArray(children).filter(isValidElement).map((child) => ({ value: child.props.value, label: child.props.children, disabled: !!child.props.disabled }))
  const selected = options.findIndex((option) => option.value === value)
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const [position, setPosition] = useState({})
  const trigger = useRef(null)
  const popup = useRef(null)
  const typed = useRef({ text: '', time: 0 })
  const expanded = open && !disabled

  function measure() {
    const rect = trigger.current.getBoundingClientRect()
    const width = Math.min(Math.max(rect.width, 180), window.innerWidth - 24)
    const below = window.innerHeight - rect.bottom - 16
    const above = rect.top - 16
    const desired = Math.min(320, options.length * 44 + 12)
    const flip = below < desired && above > below
    const maxHeight = Math.max(44, Math.min(320, flip ? above : below))
    setPosition({ width, left: Math.max(12, Math.min(rect.left, window.innerWidth - width - 12)), top: flip ? Math.max(12, rect.top - Math.min(desired, maxHeight) - 6) : rect.bottom + 6, maxHeight })
  }
  function show(index = selected) {
    if (disabled) return
    const next = index >= 0 && !options[index]?.disabled ? index : options.findIndex((option) => !option.disabled)
    setActive(next); measure(); setOpen(true); typed.current = { text: '', time: 0 }
  }
  function choose(index) {
    const option = options[index]
    if (!option || option.disabled) return
    onChange?.({ target: { value: option.value, name } })
    setOpen(false); trigger.current?.focus()
  }
  useEffect(() => {
    if (!expanded) return
    const outside = (event) => {
      if (!trigger.current?.contains(event.target) && !popup.current?.contains(event.target)) setOpen(false)
    }
    // Portalling keeps menus clear of scrolling panels and clipped containers.
    const reposition = (event) => {
      if (!(event.target instanceof Node) || !popup.current?.contains(event.target)) measure()
    }
    document.addEventListener('pointerdown', outside)
    window.addEventListener('resize', reposition)
    window.addEventListener('scroll', reposition, true)
    return () => {
      document.removeEventListener('pointerdown', outside)
      window.removeEventListener('resize', reposition)
      window.removeEventListener('scroll', reposition, true)
    }
  })
  useEffect(() => {
    if (expanded && active >= 0) document.getElementById(`${listId}-${active}`)?.scrollIntoView?.({ block: 'nearest' })
  }, [expanded, active, listId])

  function keyDown(event) {
    if (event.key === 'Tab') { setOpen(false); return }
    if (event.key === 'Escape') { if (expanded) { event.preventDefault(); event.stopPropagation(); setOpen(false) } return }
    if (['Enter', ' '].includes(event.key)) {
      event.preventDefault()
      if (expanded) choose(active)
      else show()
      return
    }
    const enabled = options.map((option, index) => !option.disabled ? index : -1).filter((index) => index >= 0)
    if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
      event.preventDefault()
      if (!expanded) { show(event.key === 'Home' ? enabled[0] : event.key === 'End' ? enabled.at(-1) : selected); return }
      const cursor = enabled.indexOf(active)
      const next = event.key === 'Home' ? enabled[0] : event.key === 'End' ? enabled.at(-1) : enabled[Math.max(0, Math.min(enabled.length - 1, cursor + (event.key === 'ArrowDown' ? 1 : -1)))]
      setActive(next ?? -1); return
    }
    if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
      event.preventDefault()
      const now = Date.now()
      const text = (now - typed.current.time < 700 ? typed.current.text : '') + event.key.toLocaleLowerCase('vi')
      typed.current = { text, time: now }
      const index = options.findIndex((option) => !option.disabled && String(option.label).toLocaleLowerCase('vi').startsWith(text))
      if (index >= 0) { if (!expanded) { measure(); setOpen(true) } setActive(index) }
    }
  }
  return <>
    <button ref={trigger} id={controlId} type="button" role="combobox" className="custom-select-trigger" aria-label={label} aria-expanded={expanded} aria-haspopup="listbox" aria-controls={expanded ? listId : undefined} aria-activedescendant={expanded && active >= 0 ? `${listId}-${active}` : undefined} disabled={disabled} onClick={() => expanded ? setOpen(false) : show()} onKeyDown={keyDown} onBlur={(event) => { if (!popup.current?.contains(event.relatedTarget)) setOpen(false) }}><span>{options[selected]?.label ?? 'Chọn một giá trị'}</span><ChevronDown size={17} aria-hidden="true" /></button>
    {name && <input type="hidden" name={name} value={value} disabled={disabled} />}
    {expanded && createPortal(<div ref={popup} className="custom-select-popup" style={position}><ul id={listId} role="listbox" aria-label={label}>{options.map((option, index) => <li key={option.value} id={`${listId}-${index}`} role="option" aria-selected={option.value === value} aria-disabled={option.disabled || undefined} className={active === index ? 'is-active' : ''} onPointerMove={() => { if (!option.disabled) setActive(index) }} onMouseDown={(event) => event.preventDefault()} onClick={() => choose(index)}><span>{option.label}</span>{option.value === value && <Check size={17} aria-hidden="true" />}</li>)}</ul></div>, document.body)}
  </>
}
