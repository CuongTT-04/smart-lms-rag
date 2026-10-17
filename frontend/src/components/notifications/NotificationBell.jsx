import { useContext, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Bell, Check, CheckCheck, ChevronLeft, ChevronRight, RefreshCw, X } from 'lucide-react'
import NotificationContext from './NotificationContext'
import { listNotifications } from '../../services/notification.service'

export default function NotificationBell() {
  const notices = useContext(NotificationContext)
  const [shown, setShown] = useState(false)
  const [full, setFull] = useState(false)
  const [unread, setUnread] = useState(false)
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [failure, setFailure] = useState('')
  const [revision, setRevision] = useState(0)
  const root = useRef(null)
  const panel = useRef(null)
  const trigger = useRef(null)
  const inbox = notices?.inbox

  useEffect(() => {
    if (!shown) return
    const controller = new AbortController()
    Promise.resolve().then(() => {
      if (!controller.signal.aborted) { setLoading(true); setFailure('') }
      return listNotifications(page, unread, controller.signal)
    }).then((result) => { if (!controller.signal.aborted) setData(result) })
      .catch(() => { if (!controller.signal.aborted) setFailure('Không tải được thông báo. Hãy thử lại.') })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [shown, page, unread, revision, inbox])

  useEffect(() => {
    if (!shown) return
    panel.current?.focus()
    function outside(event) {
      if (!root.current?.contains(event.target) && !panel.current?.contains(event.target)) setShown(false)
    }
    function keyboard(event) {
      if (event.key === 'Escape') { setShown(false); trigger.current?.focus() }
      if (event.key === 'Tab' && panel.current) {
        const buttons = [...panel.current.querySelectorAll('button:not(:disabled)')]
        const first = buttons[0], last = buttons.at(-1)
        if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) { event.preventDefault(); last?.focus() }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
      }
    }
    document.addEventListener('pointerdown', outside); document.addEventListener('keydown', keyboard)
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', keyboard) }
  }, [shown, full])

  if (!notices) return null
  async function mark(id) {
    try { await notices.read(id); setRevision((v) => v + 1) } catch { setFailure('Chưa đánh dấu được thông báo. Hãy thử lại.') }
  }
  const content = <section ref={panel} className={`notification-panel ${full ? 'notification-full' : ''}`} role="dialog" aria-label="Danh sách thông báo" aria-modal={full || undefined} tabIndex={-1}>
    <header><div><h2>Thông báo</h2><small>{notices.online ? 'Đang cập nhật realtime' : 'Lịch sử đã lưu · đang kết nối lại'}</small></div><button className="icon-button" aria-label="Đóng danh sách thông báo" onClick={() => { setShown(false); trigger.current?.focus() }}><X size={19} /></button></header>
    <nav aria-label="Lọc thông báo"><button className={!unread ? 'active' : ''} onClick={() => { setUnread(false); setPage(1) }}>Tất cả</button><button className={unread ? 'active' : ''} onClick={() => { setUnread(true); setPage(1) }}>Chưa đọc</button><button onClick={() => mark()}><CheckCheck size={16} />Đọc tất cả</button></nav>
    {(failure || notices.error) && <p role="alert" className="notification-error">{failure || notices.error}<button className="icon-button" aria-label="Tải lại thông báo" onClick={() => { setRevision((v) => v + 1); notices.refresh().catch(() => {}) }}><RefreshCw size={16} /></button></p>}
    <div className="notification-items" aria-busy={loading}>{loading && !data ? <p>Đang tải thông báo...</p> : !data?.results.length ? <p className="notification-empty">{unread ? 'Bạn đã đọc tất cả thông báo.' : 'Chưa có thông báo.'}</p> : data.results.map((item) => <article key={item.id} className={item.read_at ? '' : 'unread'}><button className="notification-item" onClick={async () => { if (await notices.open(item)) setShown(false) }}><strong>{item.title}</strong>{item.actor_name && <small>{item.actor_name}</small>}{item.body && <span>{item.body}</span>}<time dateTime={item.created_at}>{new Date(item.created_at).toLocaleString('vi-VN')}</time></button>{!item.read_at && <button className="notification-read icon-button" title="Đánh dấu đã đọc" aria-label={`Đánh dấu đã đọc: ${item.title}`} onClick={() => mark(item.id)}><Check size={17} /></button>}</article>)}</div>
    <footer>{full ? <><button className="icon-button" aria-label="Trang thông báo trước" disabled={page === 1 || loading} onClick={() => setPage((v) => v - 1)}><ChevronLeft size={18} /></button><span>Trang {page}</span><button className="icon-button" aria-label="Trang thông báo sau" disabled={!data?.next || loading} onClick={() => setPage((v) => v + 1)}><ChevronRight size={18} /></button></> : <button onClick={() => { setFull(true); setPage(1) }}>Xem tất cả thông báo</button>}</footer>
  </section>
  return <div className="notification-bell" ref={root}><button ref={trigger} className="icon-button notification-trigger" aria-label="Thông báo" aria-expanded={shown} onClick={() => { setShown((value) => !value); setFull(false); setPage(1); notices.refresh().catch(() => {}) }}><Bell size={22} />{inbox.unread_count > 0 && <span className="notification-badge" aria-label={`${inbox.unread_count} thông báo chưa đọc`}>{inbox.unread_count > 99 ? '99+' : inbox.unread_count}</span>}</button>{shown && (full ? createPortal(<div className="notification-overlay">{content}</div>, document.body) : content)}</div>
}

