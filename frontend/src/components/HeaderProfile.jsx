import { useEffect, useId, useRef, useState } from 'react'
import { ArrowRight, CircleUserRound, Mail, Phone } from 'lucide-react'
import UserAvatar from './UserAvatar'

export default function HeaderProfile({ user, onAccount }) {
  const [open, setOpen] = useState(false)
  const root = useRef(null)
  const trigger = useRef(null)
  const accountButton = useRef(null)
  const closeTimer = useRef(null)
  const id = useId()
  const teacher = user.role === 'TEACHER'
  const role = teacher ? 'Giáo viên' : 'Học viên'

  useEffect(() => {
    function outside(event) {
      if (!root.current?.contains(event.target)) setOpen(false)
    }
    document.addEventListener('pointerdown', outside)
    return () => {
      document.removeEventListener('pointerdown', outside)
      clearTimeout(closeTimer.current)
    }
  }, [])

  function show() {
    clearTimeout(closeTimer.current)
    setOpen(true)
  }

  function leave() {
    clearTimeout(closeTimer.current)
    closeTimer.current = setTimeout(() => {
      if (!root.current?.contains(document.activeElement)) setOpen(false)
    }, 180)
  }

  function keyboard(event) {
    if (event.key === 'Escape') {
      clearTimeout(closeTimer.current)
      setOpen(false)
      trigger.current?.focus()
    }
    if (event.key === 'ArrowDown' && event.target === trigger.current) {
      event.preventDefault()
      show()
      requestAnimationFrame(() => accountButton.current?.focus())
    }
  }

  function manage() {
    clearTimeout(closeTimer.current)
    setOpen(false)
    onAccount()
  }

  return <div ref={root} className="header-profile" onPointerEnter={(event) => { if (event.pointerType === 'mouse') show() }}
    onPointerLeave={(event) => { if (event.pointerType === 'mouse') leave() }} onKeyDown={keyboard}
    onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false) }}>
    <button ref={trigger} className="header-avatar-button" type="button" aria-label="Xem hồ sơ của bạn" title="Hồ sơ của bạn"
      aria-expanded={open} aria-controls={id} onClick={() => { clearTimeout(closeTimer.current); setOpen(!open) }}>
      <UserAvatar user={user} />
    </button>
    {open && <section id={id} className="header-profile-dropdown" aria-label={`Hồ sơ ${role.toLowerCase()}`}>
      <div className="header-profile-summary"><UserAvatar user={user} /><div><h2>{user.full_name || user.username}</h2><span className="header-profile-role">{role}</span><p>@{user.username}</p></div></div>
      <div className="header-profile-body">
        {user.email && <p className="header-profile-contact"><Mail size={15} aria-hidden="true" /><span>{user.email}</span></p>}
        {user.phone && <p className="header-profile-contact"><Phone size={15} aria-hidden="true" /><span>{user.phone}</span></p>}
        <dl className="header-profile-details">
          {teacher ? <><div><dt>Giới thiệu</dt><dd>{user.teacher_profile?.bio || 'Chưa cập nhật'}</dd></div><div><dt>Chuyên môn</dt><dd>{user.teacher_profile?.specialization || 'Chưa cập nhật'}</dd></div></>
            : <div><dt>Mục tiêu học tập</dt><dd>{user.student_profile?.learning_goal || 'Chưa cập nhật'}</dd></div>}
        </dl>
      </div>
      <button ref={accountButton} className="header-profile-manage" type="button" onClick={manage}><CircleUserRound size={18} aria-hidden="true" /><span>Quản lý tài khoản</span><ArrowRight size={16} aria-hidden="true" /></button>
    </section>}
  </div>
}
