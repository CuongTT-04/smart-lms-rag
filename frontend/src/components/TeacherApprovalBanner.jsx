import { useState, useId } from 'react'
import { Mail, RefreshCw, ShieldAlert, X } from 'lucide-react'
import { sendEmailVerification, authErrorMessage } from '../services/auth.service'
import { useTeachingAccess } from '../hooks/teaching-access'
import './teacher-approval.css'

export function TeachingAction({ children, disabled = false, type = 'button', ...props }) {
  const { allowed, reason } = useTeachingAccess()
  const id = useId()
  const [open, setOpen] = useState(false)
  return <span className="teaching-action" tabIndex={allowed ? undefined : 0}
    aria-describedby={!allowed ? id : undefined} onFocus={() => setOpen(true)} onBlur={() => setOpen(false)}
    onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}
    onClick={() => { if (!allowed) setOpen(value => !value) }}
    onKeyDown={event => { if (!allowed && ['Enter', ' '].includes(event.key)) { event.preventDefault(); setOpen(value => !value) } }}>
    <button {...props} type={type} disabled={!allowed || disabled} aria-describedby={!allowed ? id : props['aria-describedby']}>{children}</button>
    {!allowed && <span className="teaching-tooltip" id={id} role="tooltip" hidden={!open}>{reason}</span>}
  </span>
}

export default function TeacherApprovalBanner({ user, accessKey, check, onRefresh, onAccount }) {
  const [dismissed, setDismissed] = useState('')
  const [mail, setMail] = useState({ busy: false, message: '' })
  const approval = user.teacher_profile?.approval
  const key = `ohayo:approval-banner:${accessKey}:${Boolean(user.email_verified)}`
  let stored = false
  try { stored = sessionStorage.getItem(key) === 'hidden' } catch { /* Storage may be disabled. */ }
  if (dismissed === key || stored) return null
  const title = approval?.status === 'REVOKED' ? 'Quyền giảng dạy đã bị thu hồi'
    : approval?.status === 'REJECTED' ? 'Yêu cầu giảng dạy đã bị từ chối'
      : approval?.status === 'PENDING' ? 'Tài khoản giáo viên đang chờ duyệt'
        : 'Chưa xác nhận được quyền giảng dạy'

  async function send() {
    if (mail.busy) return
    setMail({ busy: true, message: '' })
    try {
      const result = await sendEmailVerification()
      setMail({ busy: false, message: result.already_verified ? 'Email đã được xác minh. Hãy kiểm tra lại trạng thái.' : 'Đã tiếp nhận yêu cầu. Vui lòng kiểm tra hộp thư.' })
    } catch (error) { setMail({ busy: false, message: authErrorMessage(error) }) }
  }

  return <section className="teacher-approval-banner" role="status" aria-label="Trạng thái xét duyệt giảng dạy">
    <ShieldAlert size={22} aria-hidden="true" />
    <div className="teacher-approval-copy"><h2>{title}</h2>
      <p>Bạn vẫn có thể quản lý tài khoản, nhưng chưa thể tạo hoặc quản lý khóa học, lớp học và học liệu.</p>
      {['REJECTED', 'REVOKED'].includes(approval?.status) && approval.reason && <p>Lý do: {approval.reason}</p>}
      <p>{user.email_verified ? 'Email đã xác minh. Vui lòng chờ hoặc liên hệ quản trị viên để được xét duyệt.' : 'Hãy xác minh email. Email .edu.vn hợp lệ được xét tự động sau xác minh; việc từ chối hoặc thu hồi cần quản trị viên xem xét lại.'}</p>
      <div className="teacher-approval-actions">
        {!user.email_verified && <button className="outline-button" type="button" disabled={mail.busy} onClick={send}><Mail size={16} />{mail.busy ? 'Đang gửi…' : 'Gửi email xác minh'}</button>}
        <button className="outline-button" type="button" disabled={check.busy} onClick={onRefresh}><RefreshCw size={16} className={check.busy ? 'spin' : ''} />Kiểm tra trạng thái</button>
        <button className="text-button" type="button" onClick={onAccount}>Tài khoản</button>
      </div>
      {(mail.message || check.error) && <p>{check.error || mail.message}</p>}
    </div>
    <button className="icon-button" type="button" aria-label="Ẩn thông báo xét duyệt" title="Ẩn tạm trong phiên này" onClick={() => {
      try { sessionStorage.setItem(key, 'hidden') } catch { /* Keep the in-memory dismissal. */ }
      setDismissed(key)
    }}><X size={18} /></button>
  </section>
}
