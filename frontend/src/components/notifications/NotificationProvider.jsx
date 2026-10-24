import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import NotificationContext from './NotificationContext'
import { listNotifications, notificationTicket, notificationTarget, readAllNotifications, readNotification } from '../../services/notification.service'
import { openNotificationTarget } from './notificationNavigation'
import './notifications.css'
import { useHistoryState } from '../../hooks/useHistoryState'
import VideoDialog from '../videos/VideoDialog'

const CourseDocuments = lazy(() => import('../documents/CourseDocuments'))

export default function NotificationProvider({ user, children }) {
  const [inbox, setInbox] = useState({ results: [], unread_count: 0, count: 0 })
  const [error, setError] = useState('')
  const [online, setOnline] = useState(false)
  const [toasts, setToasts] = useState([])
  const [detail, setDetail] = useState(null)
  const [documentTarget, setDocumentTarget] = useHistoryState('notifications.document', null)
  const active = useRef(null)
  const inflight = useRef(0)
  const refresh = useCallback(async (signal, freshId) => {
    const run = active.current
    const request = ++inflight.current
    const data = await listNotifications(1, false, signal)
    if (!run || run.signal.aborted || active.current !== run || request !== inflight.current) return
    setInbox(data); setError('')
    const item = freshId && data.results.find((row) => row.id === freshId)
    if (item) setToasts((rows) => rows.some((row) => row.id === item.id) ? rows : [...rows, { ...item, until: Date.now() + 5000 }].slice(-3))
    return data
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    active.current = controller
    let socket, timer, poll, tries = 0
    const safeRefresh = (id) => refresh(controller.signal, id).catch(() => { if (!controller.signal.aborted) setError('Không tải được thông báo. Hãy thử lại.') })
    async function connect() {
      if (controller.signal.aborted) return
      try {
        const { ticket } = await notificationTicket(controller.signal)
        if (controller.signal.aborted) return
        const base = new URL(import.meta.env.VITE_API_BASE_URL || '/api', window.location.href)
        base.protocol = base.protocol === 'https:' ? 'wss:' : 'ws:'
        base.pathname = '/ws/notifications/'; base.search = new URLSearchParams({ ticket }).toString()
        socket = new WebSocket(base)
        socket.onopen = () => { if (!controller.signal.aborted) { tries = 0; setOnline(true); safeRefresh() } }
        socket.onmessage = (event) => {
          if (controller.signal.aborted) return
          try {
            const data = JSON.parse(event.data)
            if (data.type === 'notifications.changed') safeRefresh(data.reason === 'created' ? data.notification_id : null)
          } catch { /* Invalid messages carry no application state. */ }
        }
        socket.onclose = retry
        socket.onerror = () => socket.close()
      } catch { retry() }
    }
    function retry() {
      if (controller.signal.aborted) return
      setOnline(false)
      clearTimeout(timer)
      timer = setTimeout(connect, Math.min(30000, 1000 * 2 ** Math.min(tries++, 5)))
    }
    function focus() { if (document.visibilityState !== 'hidden') safeRefresh() }
    safeRefresh(); connect()
    poll = setInterval(() => { if (document.visibilityState !== 'hidden') safeRefresh() }, 30000)
    window.addEventListener('focus', focus); window.addEventListener('online', focus)
    document.addEventListener('visibilitychange', focus)
    return () => {
      controller.abort(); active.current = null; clearTimeout(timer); clearInterval(poll)
      if (socket) { socket.onclose = null; socket.onmessage = null; socket.close() }
      window.removeEventListener('focus', focus); window.removeEventListener('online', focus)
      document.removeEventListener('visibilitychange', focus)
    }
  }, [user.id, refresh])

  useEffect(() => {
    if (!toasts.length) return
    const timer = setTimeout(() => setToasts((rows) => rows.filter((row) => row.until > Date.now())), Math.max(1, Math.min(...toasts.map((row) => row.until)) - Date.now()))
    return () => clearTimeout(timer)
  }, [toasts])

  async function read(id) {
    const run = active.current
    await (id ? readNotification(id, run?.signal) : readAllNotifications(run?.signal))
    if (run === active.current && !run?.signal.aborted) await refresh(run.signal)
  }
  async function open(item) {
    const run = active.current
    try {
      await read(item.id)
      if (!run || run.signal.aborted) return false
      const { target } = await notificationTarget(item.id, run.signal)
      if (run.signal.aborted) return false
      if (target.admin) { setDetail({ item, account: target.account, report: target.report }); return true }
      await openNotificationTarget(target, user, run.signal)
      return !run.signal.aborted
    } catch (err) {
      if (run === active.current && !run?.signal.aborted) setError(err.data?.detail || err.message || 'Nội dung không còn khả dụng.')
      return false
    }
  }
  return <NotificationContext.Provider value={{ inbox, error, online, refresh, read, open }}>
    {children}
    {documentTarget && <VideoDialog className="notification-document-dialog" title="Học liệu khóa học" onClose={() => setDocumentTarget(null)}><Suspense fallback={<p>Đang tải học liệu...</p>}><CourseDocuments key={documentTarget.document_id} courseId={documentTarget.course_id} selectedDocumentId={documentTarget.document_id} workspace canManage={user.role === 'TEACHER'} /></Suspense></VideoDialog>}
    {detail && createPortal(<AdminNoticeDetail detail={detail} onClose={() => setDetail(null)} />, document.body)}
    {createPortal(<div className="notification-toasts" aria-live="polite">{toasts.map((item) => <div key={item.id} className="notification-toast" role="status"><button onClick={() => open(item)}>{item.title}</button><button className="icon-button" aria-label="Đóng thông báo" onClick={() => setToasts((rows) => rows.filter((row) => row.id !== item.id))}><X size={17} /></button></div>)}</div>, document.body)}
  </NotificationContext.Provider>
}

function AdminNoticeDetail({ detail, onClose }) {
  const root = useRef(null)
  useEffect(() => {
    root.current?.focus()
    const escape = (event) => { if (event.key === 'Escape') onClose() }
    document.addEventListener('keydown', escape)
    return () => document.removeEventListener('keydown', escape)
  }, [onClose])
  const labels = { username: 'Tên đăng nhập', email: 'Email', full_name: 'Họ tên', role: 'Vai trò', status: 'Trạng thái', document_id: 'Mã học liệu', document_title: 'Học liệu', course_title: 'Khóa học', reporter: 'Người báo cáo', reason: 'Lý do', opinion: 'Ý kiến' }
  return <div className="notification-overlay" onClick={(event) => { if (event.target === event.currentTarget) onClose() }}><section ref={root} tabIndex={-1} role="dialog" aria-modal="true" aria-label="Chi tiết thông báo quản trị" className="notification-panel notification-full"><header><h2>{detail.item.title}</h2><button className="icon-button" aria-label="Đóng chi tiết thông báo" onClick={onClose}><X size={20} /></button></header><div className="notification-admin-detail"><p>{detail.item.body}</p>{Object.entries({ ...detail.account, ...detail.report }).map(([key, value]) => <p key={key}><strong>{labels[key] || key}: </strong>{value || 'Chưa cập nhật'}</p>)}<time>{new Date(detail.item.created_at).toLocaleString('vi-VN')}</time></div></section></div>
}

