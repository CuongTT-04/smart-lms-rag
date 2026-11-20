import { useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { advanceSummaryTask, chatErrorMessage, getSummaryTask, sendChat } from '../../services/ai.service'
import ChatAnswer from './ChatAnswer'

export default function DocumentSummary({ scope, documentId, onClose, onOpenCitation }) {
  const [start, setStart] = useState('1')
  const [end, setEnd] = useState('')
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [progress, setProgress] = useState(null)
  const request = useRef(null)
  const running = useRef(false)
  const task = useRef(null)
  useEffect(() => () => request.current?.abort(), [])
  async function summarize(event) {
    event.preventDefault()
    if (running.current) return
    running.current = true
    const controller = new AbortController()
    request.current = controller
    setBusy(true); setError(''); setResult(null); setProgress(null)
    try {
      const payload = { ...scope, document_ids: [documentId], mode: 'summary',
        question: 'Tóm tắt nội dung học liệu theo phạm vi trang.', page_start: Number(start),
        ...(end ? { page_end: Number(end) } : {}) }
      const key = JSON.stringify(payload)
      if (task.current?.key !== key) task.current = { key, requestId: crypto.randomUUID(), id: null }
      let data = task.current.id ? await getSummaryTask(task.current.id, { signal: controller.signal }) :
        await sendChat({ ...payload, summary_request_id: task.current.requestId }, { signal: controller.signal })
      if (!data.id) throw { data: { code: 'GENERATION_CONFIG_MISMATCH' } }
      task.current.id = data.id
      while (!controller.signal.aborted && ['PENDING', 'PROCESSING'].includes(data.status)) {
        setProgress(data.progress)
        const previousSteps = data.progress.steps
        data = await advanceSummaryTask(data.id, { signal: controller.signal })
        if (['PENDING', 'PROCESSING'].includes(data.status) && data.progress.steps === previousSteps) {
          await new Promise((resolve, reject) => {
            const abort = () => { clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')) }
            const timer = setTimeout(() => { controller.signal.removeEventListener('abort', abort); resolve() }, 2000)
            controller.signal.addEventListener('abort', abort, { once: true })
            if (controller.signal.aborted) abort()
          })
        }
      }
      if (controller.signal.aborted) return
      if (data.status === 'FAILED') {
        task.current = null
        throw { data: data.error }
      }
      if (data.status !== 'COMPLETED' || data.result?.coverage?.method !== 'coherent_summary_v1') {
        throw { data: { code: 'SUMMARY_GENERATION_FAILED' } }
      }
      setResult(data.result)
    } catch (failure) {
      if (!controller.signal.aborted) {
        const disconnected = task.current?.id && [0, 502, 504].includes(failure.status)
        setError(disconnected
          ? 'Kết nối bị gián đoạn. Tiến độ đã được lưu; bấm Tóm tắt để tiếp tục.'
          : chatErrorMessage(failure))
      }
    } finally {
      if (!controller.signal.aborted) { running.current = false; setBusy(false) }
    }
  }
  return <section className="ai-document-summary" aria-label="Tóm tắt nội dung học liệu">
    <header><strong>Tóm tắt nội dung</strong><button type="button" className="icon-button" aria-label="Đóng tóm tắt" title="Đóng tóm tắt" onClick={onClose}><X size={16} /></button></header>
    <form onSubmit={summarize}>
      <label>Từ trang PDF<input autoFocus type="number" min="1" step="1" required value={start} disabled={busy} onChange={event => setStart(event.target.value)} /></label>
      <label>Đến trang PDF<input type="number" min={start || 1} step="1" placeholder="Cuối tài liệu" value={end} disabled={busy} onChange={event => setEnd(event.target.value)} /></label>
      <button type="submit" disabled={busy}>{busy ? 'Đang đọc…' : 'Tóm tắt'}</button>
    </form>
    {error && <p role="alert" className="error-banner">{error}</p>}
    {busy && progress && <p role="status">{progress.phase === 'map' ? `Đang đọc học liệu · ${progress.blocks_read}/${progress.blocks_total} phần` : 'Đang tổng hợp nội dung…'}</p>}
    {result && <div className="ai-summary-result">
      <p>Trang PDF {result.coverage.page_start}–{result.coverage.page_end} / {result.coverage.document_pages} · {result.coverage.chunks_scanned} đoạn đã đọc · {result.coverage.whole_document ? 'Toàn tài liệu' : 'Phạm vi đã chọn'}</p>
      <ChatAnswer result={result} animate={false} sourceLabel="Nguồn trong phạm vi tóm tắt" onOpenCitation={onOpenCitation} />
    </div>}
  </section>
}
