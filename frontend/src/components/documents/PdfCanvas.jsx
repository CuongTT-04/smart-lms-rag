import { useEffect, useRef, useState } from 'react'
import { ChevronLeft, ChevronRight, Maximize, ZoomIn, ZoomOut } from 'lucide-react'
import { getDocument, GlobalWorkerOptions, TextLayer } from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import PdfStudyTools from './PdfStudyTools'

// Use a fresh cache key after correcting the module MIME type in Docker.
GlobalWorkerOptions.workerSrc = `${workerUrl}?module=2`

export default function PdfCanvas({ url, title, annotatable = false, documentId, versionId, showFeedback = true, allowCopy = false }) {
  const [pdf, setPdf] = useState(null)
  const [pageNumber, setPageNumber] = useState(1)
  const [zoom, setZoom] = useState(null)
  const [scale, setScale] = useState(1)
  const [size, setSize] = useState({ width: 0, height: 0 })
  const [error, setError] = useState('')
  const [rendering, setRendering] = useState(true)
  const canvas = useRef(null)
  const viewport = useRef(null)
  const reader = useRef(null)
  const textLayer = useRef(null)
  const pan = useRef(null)
  const [dragging, setDragging] = useState(false)
  const [pageRatio, setPageRatio] = useState(1)
  useEffect(() => {
    let live = true
    const task = getDocument({ url, isEvalSupported: false })
    task.promise.then((document) => { if (live) setPdf(document) })
      .catch(() => { if (live) setError('Không thể hiển thị tài liệu PDF. Hãy đóng và mở lại bản xem.') })
    return () => { live = false; void task.destroy() }
  }, [url])
  useEffect(() => {
    const observer = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect
      setSize({ width, height })
    })
    observer.observe(viewport.current)
    return () => observer.disconnect()
  }, [])
  useEffect(() => {
    if (allowCopy) return
    function blockCopy(event) {
      const selection = window.getSelection()
      if (!selection?.rangeCount || selection.isCollapsed || !textLayer.current) return
      for (let i = 0; i < selection.rangeCount; i++) {
        if (selection.getRangeAt(i).intersectsNode(textLayer.current)) {
          event.preventDefault()
          event.clipboardData?.setData('text/plain', '')
          return
        }
      }
    }
    document.addEventListener('copy', blockCopy, true)
    document.addEventListener('cut', blockCopy, true)
    return () => { document.removeEventListener('copy', blockCopy, true); document.removeEventListener('cut', blockCopy, true) }
  }, [allowCopy])
  function startPan(event, tool) {
    if (tool !== 'hand' || event.button !== 0 || rendering || error) return
    event.preventDefault()
    window.getSelection()?.removeAllRanges()
    event.currentTarget.setPointerCapture?.(event.pointerId)
    pan.current = { x: event.clientX, y: event.clientY, left: event.currentTarget.scrollLeft, top: event.currentTarget.scrollTop }
    setDragging(true)
  }
  function movePan(event) {
    if (!pan.current) return
    event.currentTarget.scrollLeft = pan.current.left - (event.clientX - pan.current.x)
    event.currentTarget.scrollTop = pan.current.top - (event.clientY - pan.current.y)
  }
  function endPan() { pan.current = null; setDragging(false) }
  useEffect(() => {
    const target = viewport.current
    function wheelZoom(event) {
      if (!pdf || error || !event.deltaY) return
      // A native non-passive listener prevents scrolling the surrounding page.
      event.preventDefault()
      const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? target.clientHeight : 1
      const delta = Math.max(-100, Math.min(100, event.deltaY * unit))
      setZoom((previous) => Math.min(4, Math.max(0.05, (previous ?? scale) * Math.exp(-delta * 0.002))))
    }
    target.addEventListener('wheel', wheelZoom, { passive: false })
    return () => target.removeEventListener('wheel', wheelZoom)
  }, [pdf, error, scale])
  useEffect(() => {
    if (!pdf || size.width <= 0 || size.height <= 0) return
    let live = true, task, textTask
    pdf.getPage(pageNumber).then(async (page) => {
      if (!live) return
      setRendering(true)
      textLayer.current.replaceChildren()
      const original = page.getViewport({ scale: 1 })
      const fit = Math.max(0.05, Math.min((size.width - 32) / original.width, (size.height - 32) / original.height))
      const nextScale = zoom ?? fit
      const scaled = page.getViewport({ scale: nextScale })
      const outputScale = Math.min(window.devicePixelRatio || 1, 2)
      const target = canvas.current
      const context = target.getContext('2d')
      target.width = Math.ceil(scaled.width * outputScale)
      target.height = Math.ceil(scaled.height * outputScale)
      target.style.width = `${scaled.width}px`
      target.style.height = `${scaled.height}px`
      setScale(nextScale)
      setPageRatio(original.height / original.width)
      task = page.render({ canvas: target, canvasContext: context, viewport: scaled, transform: outputScale === 1 ? null : [outputScale, 0, 0, outputScale, 0, 0] })
      await task.promise
      if (!live) return
      // The transparent text layer shares the canvas viewport, so selection follows zoom/rotation.
      textLayer.current.style.setProperty('--total-scale-factor', scaled.scale ?? nextScale)
      const content = await page.getTextContent()
      if (!live) return
      textTask = new TextLayer({ textContentSource: content, container: textLayer.current, viewport: scaled })
      await textTask.render()
      if (live) { setRendering(false); setError('') }
    }).catch((failure) => {
      if (live && failure.name !== 'RenderingCancelledException') setError('Không thể hiển thị trang PDF. Hãy thử mở lại tài liệu.')
    })
    return () => { live = false; task?.cancel(); textTask?.cancel() }
  }, [pdf, pageNumber, size.width, size.height, zoom])
  return <PdfStudyTools showFeedback={showFeedback} enabled={annotatable} documentId={documentId} versionId={versionId} pageNumber={pageNumber} ratio={pageRatio} ready={!!pdf && !rendering && !error} readerRef={reader}>{({ toolbar, overlay, notes, tool }) => <div ref={reader} className="pdf-canvas-reader">
    <div className="pdf-reader-toolbar" aria-label="Điều khiển tài liệu PDF">
      <div className="pdf-reader-zoom"><button type="button" className="icon-button" title="Thu nhỏ" aria-label="Thu nhỏ tài liệu" disabled={!pdf || scale <= 0.1} onClick={() => setZoom(Math.max(0.1, scale / 1.2))}><ZoomOut size={20} /></button><input type="range" aria-label="Thu phóng tài liệu" aria-valuetext={`${Math.round(scale * 100)}%`} min="0.05" max="4" step="0.01" value={Math.min(4, Math.max(0.05, scale))} disabled={!pdf} onChange={(event) => setZoom(Number(event.target.value))} /><button type="button" className="icon-button" title="Phóng to" aria-label="Phóng to tài liệu" disabled={!pdf || scale >= 4} onClick={() => setZoom(Math.min(4, scale * 1.2))}><ZoomIn size={20} /></button><button type="button" className={`outline-button ${zoom === null ? 'is-fit-page' : ''}`} disabled={!pdf} onClick={() => setZoom(null)}><Maximize size={17} />Mặc định</button></div>
      {toolbar}
      <div className="pdf-reader-pagination"><button type="button" className="icon-button" title="Trang trước" aria-label="Trang trước" disabled={!pdf || pageNumber <= 1} onClick={() => setPageNumber((n) => n - 1)}><ChevronLeft size={20} /></button><span aria-label="Trang PDF hiện tại">{pageNumber} / {pdf?.numPages || '—'}</span><button type="button" className="icon-button" title="Trang sau" aria-label="Trang sau" disabled={!pdf || pageNumber >= pdf.numPages} onClick={() => setPageNumber((n) => n + 1)}><ChevronRight size={20} /></button></div>
    </div>
    <div ref={viewport} className={`pdf-reader-viewport tool-${tool} ${dragging ? 'is-dragging' : ''}`} onPointerDown={(event) => startPan(event, tool)} onPointerMove={movePan} onPointerUp={endPan} onPointerCancel={endPan} onLostPointerCapture={endPan} tabIndex={0} aria-label={`PDF ${title}`}>
      {error && <p role="alert" className="pdf-render-message">{error}</p>}
      {!error && rendering && <p role="status" className="pdf-render-message">Đang hiển thị trang...</p>}
      <div className="pdf-page-stage"><div className="pdf-annotated-page"><canvas ref={canvas} role="img" aria-label={`Trang ${pageNumber} của ${title}`} style={{ visibility: rendering || error ? 'hidden' : 'visible' }} /><div ref={textLayer} className="pdf-selection-layer" aria-label="Văn bản PDF" style={{ visibility: rendering || error ? 'hidden' : 'visible', pointerEvents: tool === 'pointer' ? 'auto' : 'none' }} onContextMenu={(event) => { if (!allowCopy) event.preventDefault() }} onDragStart={(event) => { if (!allowCopy) event.preventDefault() }} />{!rendering && !error && overlay}</div></div>
    </div>
    {notes}
  </div>}</PdfStudyTools>
}
