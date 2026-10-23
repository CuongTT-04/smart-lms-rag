import { useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

function CitationMarker({ citation }) {
  const id = useId()
  const [position, setPosition] = useState(null)
  const closing = useRef(null)
  const focused = useRef(false)
  const hovered = useRef(false)
  useEffect(() => () => clearTimeout(closing.current), [])
  function show(event) {
    clearTimeout(closing.current)
    const rect = event.currentTarget.getBoundingClientRect()
    const width = Math.min(340, window.innerWidth - 24)
    const below = window.innerHeight - rect.bottom > 240
    setPosition({ width, left: Math.max(12, Math.min(rect.left, window.innerWidth - width - 12)),
      ...(below ? { top: rect.bottom + 8 } : { bottom: window.innerHeight - rect.top + 8 }) })
  }
  function hide() {
    hovered.current = false
    closing.current = setTimeout(() => { if (!focused.current) setPosition(null) }, 150)
  }
  return <>
    <button type="button" className="ai-citation-marker" aria-label={`Trích dẫn [${citation.label}]`}
      aria-describedby={position ? id : undefined} onMouseEnter={(event) => { hovered.current = true; show(event) }} onMouseLeave={hide}
      onFocus={(event) => { focused.current = true; show(event) }} onBlur={() => { focused.current = false; if (!hovered.current) setPosition(null) }} onClick={show}
      onKeyDown={(event) => { if (event.key === 'Escape') setPosition(null) }}>[{citation.label}]</button>
    {position && createPortal(<div id={id} role="tooltip" className="ai-citation-tooltip" style={position}
      onMouseEnter={() => { hovered.current = true; clearTimeout(closing.current) }} onMouseLeave={hide}>
      <strong>{citation.document_title} — trang {citation.page_number}</strong>
      <blockquote>{citation.excerpt || 'Chưa có đoạn trích cho câu trả lời này. Bạn có thể mở nguồn bên dưới.'}</blockquote>
    </div>, document.body)}
  </>
}

export default function CitationText({ text, citations = [] }) {
  return text.split(/(\[\d+\])/g).map((part, index) => {
    const marker = /^\[(\d+)\]$/.exec(part)
    const citation = marker && citations.find((item) => item.label === Number(marker[1]))
    return citation ? <CitationMarker key={index} citation={citation} /> : part
  })
}
