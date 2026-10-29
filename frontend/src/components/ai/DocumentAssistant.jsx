import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { ArrowUp, History, MessageSquarePlus, X } from 'lucide-react'
import { listConversations, createConversation, getConversation, sendChat, chatErrorMessage } from '../../services/ai.service'
import ChatAnswer from './ChatAnswer'
import ChatUserMessage from './ChatUserMessage'

function restoreTurns(rows) {
  return rows.map(row => ({ id: row.id, position: row.position, question: row.question, createdAt: row.created_at,
    pending: row.status === 'PENDING', result: row.result, error: row.error ? chatErrorMessage({data: row.error}) : null, restored: true }))
}

function mergeTurns(previous, incoming) {
  const rows = new Map(previous.map(row => [row.id, row]))
  incoming.forEach(row => rows.set(row.id, row))
  return [...rows.values()].sort((a, b) => (a.position || 0) - (b.position || 0))
}

export default function DocumentAssistant({ scope, documentId, visible = true, onOpenCitation, toolbarTarget }) {
  const selectorKey = JSON.stringify({ ...scope, document_id: documentId })
  const selector = useMemo(() => JSON.parse(selectorKey), [selectorKey])
  const [conversation, setConversation] = useState(null)
  const [turns, setTurns] = useState([])
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [reload, setReload] = useState(0)
  const [olderBefore, setOlderBefore] = useState(null)
  const [olderLoading, setOlderLoading] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [historyClosing, setHistoryClosing] = useState(false)
  const historyId = useId()
  const [sessions, setSessions] = useState([])
  const [nextCursor, setNextCursor] = useState(null)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState('')
  const initialized = useRef(false)
  const generation = useRef(0)
  const active = useRef(null)
  const olderRequest = useRef(null)
  const historyRequest = useRef(null)
  const currentConversation = useRef(null)
  const input = useRef(null)
  const historyTrigger = useRef(null)
  const historyAnchor = useRef(null)
  const thread = useRef(null)
  const content = useRef(null)
  const pinned = useRef(true)

  function closeHistory(restoreFocus = false) {
    setHistoryClosing(historyOpen); setHistoryOpen(false)
    if (restoreFocus) historyTrigger.current?.focus()
  }

  useEffect(() => {
    if (!historyClosing) return
    const timer = setTimeout(() => setHistoryClosing(false), 180)
    return () => clearTimeout(timer)
  }, [historyClosing])

  useEffect(() => {
    if (!historyOpen || !visible) return
    const outside = event => {
      if (!historyAnchor.current?.contains(event.target)) { setHistoryClosing(true); setHistoryOpen(false) }
    }
    const escape = event => {
      if (event.key === 'Escape') {
        event.preventDefault(); setHistoryClosing(true); setHistoryOpen(false); historyTrigger.current?.focus()
      }
    }
    document.addEventListener('pointerdown', outside)
    document.addEventListener('keydown', escape)
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape) }
  }, [historyOpen, visible])

  useEffect(() => () => { active.current?.abort(); olderRequest.current?.abort(); historyRequest.current?.abort() }, [])
  useEffect(() => {
    if (!visible || initialized.current) return
    const controller = new AbortController()
    const epoch = ++generation.current
    active.current = controller
    const valid = () => !controller.signal.aborted && generation.current === epoch
    Promise.resolve().then(async () => {
      try {
        const list = await listConversations(selector, { signal: controller.signal })
        if (!valid()) return
        setSessions(list.results); setNextCursor(list.next_cursor)
        if (list.results[0]) {
          const detail = await getConversation(list.results[0].id, { signal: controller.signal })
          if (!valid()) return
          currentConversation.current = detail.id
          setConversation(detail); setTurns(restoreTurns(detail.turns)); setOlderBefore(detail.next_before)
        }
        if (valid()) { initialized.current = true; setLoadError('') }
      } catch (error) {
        if (valid()) { initialized.current = true; setLoadError(chatErrorMessage(error)) }
      } finally { if (valid()) setLoading(false) }
    })
    return () => controller.abort()
  }, [selector, visible, reload])

  useEffect(() => {
    const scroll = () => { if (pinned.current && thread.current) thread.current.scrollTop = thread.current.scrollHeight }
    scroll()
    if (!window.ResizeObserver || !content.current) return
    const observer = new ResizeObserver(scroll)
    observer.observe(content.current)
    return () => observer.disconnect()
  }, [turns])

  useEffect(() => {
    if (!historyOpen) return
    const controller = new AbortController()
    historyRequest.current?.abort(); historyRequest.current = controller
    Promise.resolve().then(async () => {
      if (controller.signal.aborted) return
      setHistoryLoading(true); setHistoryError('')
      try {
        const list = await listConversations(selector, { signal: controller.signal })
        if (!controller.signal.aborted) { setSessions(list.results); setNextCursor(list.next_cursor) }
      } catch (error) { if (!controller.signal.aborted) setHistoryError(chatErrorMessage(error)) }
      finally { if (!controller.signal.aborted) setHistoryLoading(false) }
    })
    return () => controller.abort()
  }, [historyOpen, selector])

  useEffect(() => {
    if (!conversation?.id || busy || !visible || !turns.some(turn => turn.pending)) return
    const controller = new AbortController()
    const epoch = generation.current
    const timer = setInterval(async () => {
      try {
        const detail = await getConversation(conversation.id, { signal: controller.signal })
        if (!controller.signal.aborted && generation.current === epoch) setTurns(previous => mergeTurns(previous, restoreTurns(detail.turns)))
      } catch (error) {
        if (!controller.signal.aborted && generation.current === epoch) { setTurns([]); setLoadError(chatErrorMessage(error)) }
      }
    }, 2500)
    return () => { clearInterval(timer); controller.abort() }
  }, [conversation?.id, busy, visible, turns])

  function newChat() {
    active.current?.abort(); olderRequest.current?.abort(); ++generation.current
    initialized.current = true; currentConversation.current = null; pinned.current = true
    setConversation(null); setTurns([]); setQuestion(''); setBusy(false); setLoading(false)
    setLoadError(''); closeHistory(); setOlderBefore(null); setOlderLoading(false)
    if (input.current) { input.current.style.height = '24px'; input.current.focus() }
  }

  async function selectConversation(id) {
    active.current?.abort(); olderRequest.current?.abort()
    const controller = new AbortController(), epoch = ++generation.current
    active.current = controller; currentConversation.current = id; initialized.current = true
    closeHistory(); setTurns([]); setQuestion(''); setBusy(false); setLoading(true); setLoadError(''); setOlderLoading(false)
    pinned.current = true
    try {
      const detail = await getConversation(id, { signal: controller.signal })
      if (!controller.signal.aborted && generation.current === epoch) {
        setConversation(detail); setTurns(restoreTurns(detail.turns)); setOlderBefore(detail.next_before)
      }
    } catch (error) { if (!controller.signal.aborted && generation.current === epoch) setLoadError(chatErrorMessage(error)) }
    finally { if (!controller.signal.aborted && generation.current === epoch) setLoading(false) }
  }

  async function moreHistory() {
    const controller = new AbortController()
    historyRequest.current?.abort(); historyRequest.current = controller
    setHistoryLoading(true)
    try {
      const list = await listConversations(selector, { signal: controller.signal, cursor: nextCursor })
      if (!controller.signal.aborted) { setSessions(previous => [...previous, ...list.results.filter(row => !previous.some(p => p.id === row.id))]); setNextCursor(list.next_cursor) }
    } catch (error) { if (!controller.signal.aborted) setHistoryError(chatErrorMessage(error)) }
    finally { if (!controller.signal.aborted) setHistoryLoading(false) }
  }

  async function olderTurns() {
    const controller = new AbortController(), epoch = generation.current
    olderRequest.current?.abort(); olderRequest.current = controller; setOlderLoading(true)
    try {
      const detail = await getConversation(conversation.id, { signal: controller.signal, before: olderBefore })
      if (!controller.signal.aborted && epoch === generation.current) {
        pinned.current = false; setTurns(previous => mergeTurns(previous, restoreTurns(detail.turns))); setOlderBefore(detail.next_before)
      }
    } catch (error) { if (!controller.signal.aborted && epoch === generation.current) { setTurns([]); setLoadError(chatErrorMessage(error)) } }
    finally { if (!controller.signal.aborted && epoch === generation.current) setOlderLoading(false) }
  }

  async function submit(event, retryTurn = null) {
    event.preventDefault()
    if (busy || loading || loadError || (!retryTurn && (!question.trim() || turns.some(turn => turn.uncertain)))) return
    const text = retryTurn?.question || question.trim(), messageId = retryTurn?.clientMessageId || crypto.randomUUID()
    olderRequest.current?.abort(); setOlderLoading(false)
    const controller = new AbortController(), epoch = ++generation.current
    active.current?.abort(); active.current = controller
    const valid = () => !controller.signal.aborted && generation.current === epoch
    pinned.current = true; setQuestion(''); setBusy(true)
    setTurns(previous => retryTurn ? previous.map(turn => turn.id === retryTurn.id ?
      { ...turn, pending: true, uncertain: false, error: null } : turn) :
      [...previous, { id: messageId, clientMessageId: messageId, position: Math.max(0, ...previous.map(turn => turn.position || 0))+1,
        question: text, createdAt: new Date().toISOString(), pending: true, restored: false }])
    if (input.current) input.current.style.height = '24px'
    try {
      let id = currentConversation.current
      if (!id) {
        const created = await createConversation(selector, { signal: controller.signal })
        if (!valid()) return
        id = created.id; currentConversation.current = id; setConversation(created)
      }
      const data = await sendChat({ ...scope, document_ids: [documentId], conversation_id: id,
        client_message_id: messageId, question: text, mode: 'qa' }, { signal: controller.signal })
      if (valid()) setTurns(previous => previous.map(turn => turn.clientMessageId === messageId ?
        { ...turn, id: data.turn_id || turn.id, pending: data.status === 'PENDING', result: data.status === 'PENDING' ? null : data } : turn))
    } catch (error) {
      const uncertain = !error.status || (error.status >= 500 && !error.data?.code)
      if (valid()) setTurns(previous => previous.map(turn => turn.clientMessageId === messageId ?
        { ...turn, pending: false, uncertain, error: uncertain ? 'Kết nối bị gián đoạn. Kiểm tra lại để nhận kết quả của lượt hỏi này.' : chatErrorMessage(error) } : turn))
    } finally { if (valid()) setBusy(false) }
  }

  function resizeInput() {
    if (input.current) { input.current.style.height = 'auto'; input.current.style.height = `${Math.min(120, Math.max(24, input.current.scrollHeight - 8))}px` }
  }

  const historyPopover = (historyOpen || historyClosing) && <section id={historyId} role="dialog" aria-modal="false" aria-label="Lịch sử chat"
    className={`ai-chat-history ${historyOpen ? 'is-open' : 'is-closing'}`} aria-hidden={!historyOpen} inert={!historyOpen}
    onAnimationEnd={event => { if (event.target === event.currentTarget && !historyOpen) setHistoryClosing(false) }}>
      <header><strong>Các phiên của học liệu</strong><button className="icon-button" type="button" aria-label="Đóng lịch sử" onClick={() => closeHistory(true)}><X size={16} /></button></header>
      <div className="ai-chat-history-body">
      {historyLoading && <p role="status">Đang tải lịch sử…</p>}
      {historyError && <p role="alert">{historyError}</p>}
      {!historyLoading && !sessions.length && !historyError && <p>Chưa có phiên chat nào.</p>}
      <div className="ai-chat-session-list">{sessions.map(item => <button key={item.id} type="button" title={item.title} aria-label={`Mở phiên ${item.title}`} aria-current={conversation?.id === item.id ? 'true' : undefined} onClick={() => selectConversation(item.id)}>
        <span>{item.title}</span>{item.updated_at && <small>{new Date(item.updated_at).toLocaleString('vi-VN')}</small>}
      </button>)}</div>
      {nextCursor && <button className="ai-chat-retry" type="button" disabled={historyLoading} onClick={moreHistory}>Xem thêm phiên</button>}
      </div>
    </section>

  const toolbar = <div className="ai-chat-toolbar" role="group" aria-label="Thao tác hội thoại">
    <button className="ai-chat-tool" type="button" aria-label="Chat mới" title="Chat mới" onClick={newChat}><MessageSquarePlus size={18} /></button>
    <div className="ai-chat-history-anchor" ref={historyAnchor}>
      <button className="ai-chat-tool" type="button" aria-label="Lịch sử" title="Lịch sử" ref={historyTrigger} aria-haspopup="dialog" aria-controls={historyId} aria-expanded={historyOpen}
        onClick={() => { if (historyOpen) closeHistory(); else { setHistoryClosing(false); setHistoryOpen(true) } }}><History size={18} /></button>
      {historyPopover}
    </div>
  </div>

  return <div className="ai-chat-content">
    {toolbarTarget ? createPortal(toolbar, toolbarTarget) : toolbar}
    {loading && <p className="ai-chat-empty" role="status">Đang tải hội thoại…</p>}
    {loadError && <div><p className="error-banner" role="alert">{loadError}</p><button className="ai-chat-retry" type="button" onClick={() => {
      active.current?.abort(); initialized.current = false; setLoadError(''); setLoading(true); setReload(value => value+1)
    }}>Tải lại hội thoại</button></div>}
    <div className="ai-chat-result" ref={thread} aria-label="Hội thoại với ayo" onScroll={() => {
      const box = thread.current; pinned.current = box.scrollHeight-box.scrollTop-box.clientHeight < 60
    }}>
      {olderBefore && !loading && <button className="ai-chat-retry" type="button" disabled={olderLoading} onClick={olderTurns}>{olderLoading ? 'Đang tải…' : 'Xem các lượt trước'}</button>}
      <div ref={content} className="ai-chat-thread">{turns.map(turn => <section className="ai-chat-turn" key={turn.id}>
        <ChatUserMessage question={turn.question} createdAt={turn.createdAt} />
        {turn.pending && <div className="ai-thinking" role="status"><span className="ai-thinking-dots" aria-hidden="true"><i /><i /><i /></span>Đang suy nghĩ…</div>}
        {turn.error && <div><p className="error-banner" role="alert">{turn.error}</p><button className="ai-chat-retry" type="button" disabled={busy} onClick={event => {
          if (turn.uncertain) submit(event, turn)
          else { setQuestion(turn.question); input.current?.focus() }
        }}>{turn.uncertain ? 'Kiểm tra lại lượt hỏi' : 'Soạn lại câu hỏi'}</button></div>}
        {turn.result && <ChatAnswer result={turn.result} onOpenCitation={onOpenCitation} active={visible} animate={!turn.restored} />}
      </section>)}</div>
      {!loading && !loadError && !turns.length && <p className="ai-chat-empty">Bắt đầu cuộc trò chuyện về học liệu này.</p>}
    </div>
    <form className="ai-chat-compose" onSubmit={submit}>
      <textarea ref={input} aria-label="Câu hỏi cho ayo" rows={1} maxLength={8000} placeholder="Hỏi ayo…" disabled={busy || loading || !!loadError || turns.some(turn => turn.uncertain)} value={question}
        onChange={event => { setQuestion(event.target.value); resizeInput() }} onKeyDown={event => {
          if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); submit(event) }
        }} />
      <button className="ai-chat-send" type="submit" aria-label="Gửi câu hỏi" title="Gửi câu hỏi" disabled={busy || loading || !!loadError || turns.some(turn => turn.uncertain) || !question.trim()}><ArrowUp size={19} /></button>
    </form>
    <p className="ai-chat-disclaimer">ayo có thể sai — hãy đối chiếu với học liệu.</p>
  </div>
}
