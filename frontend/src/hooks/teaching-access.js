import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { currentUser } from '../services/auth.service'

export const TeachingAccessContext = createContext({ allowed: false, reason: 'Tài khoản chưa được duyệt giảng dạy.' })
export const useTeachingAccess = () => useContext(TeachingAccessContext)
export const teachingAllowed = user => user?.role === 'TEACHER' && user.status === 'ACTIVE' && user.teaching_allowed === true

export function useTeachingStatus(user, onUserUpdated, onSessionExpired) {
  const [observed, setObserved] = useState(null)
  const [check, setCheck] = useState({ busy: false, error: '' })
  const serial = useRef(0)
  const controller = useRef(null)
  const effective = observed?.basis === user ? observed.value : user

  const refresh = useCallback(async () => {
    const ticket = ++serial.current
    controller.current?.abort()
    controller.current = new AbortController()
    setCheck({ busy: true, error: '' })
    try {
      const account = await currentUser(controller.current.signal)
      if (ticket !== serial.current) return
      if (!account || account.id !== user.id) {
        setObserved({ basis: user, value: { ...user, teaching_allowed: false } })
        setCheck({ busy: false, error: 'Phiên đăng nhập đã thay đổi. Vui lòng đăng nhập lại.' })
        onSessionExpired?.('Phiên đăng nhập đã thay đổi. Vui lòng đăng nhập lại.')
        return
      }
      setObserved({ basis: user, value: account })
      setCheck({ busy: false, error: '' })
      onUserUpdated?.(account)
    } catch (error) {
      if (ticket !== serial.current) return
      setCheck({ busy: false, error: 'Chưa kiểm tra được trạng thái. Vui lòng thử lại.' })
      if (error.status === 401) onSessionExpired?.('Phiên đăng nhập đã hết hạn.')
    }
  }, [user, onUserUpdated, onSessionExpired])

  useEffect(() => {
    const focus = () => { if (!document.hidden) refresh() }
    const denied = () => {
      setObserved({ basis: user, value: { ...user, teaching_allowed: false } })
      refresh()
    }
    window.addEventListener('focus', focus)
    document.addEventListener('visibilitychange', focus)
    window.addEventListener('ohayo:teaching-access-denied', denied)
    const timer = setInterval(focus, 60000)
    return () => {
      serial.current += 1
      controller.current?.abort()
      clearInterval(timer)
      window.removeEventListener('focus', focus)
      document.removeEventListener('visibilitychange', focus)
      window.removeEventListener('ohayo:teaching-access-denied', denied)
    }
  }, [refresh, user])

  const revision = effective.teacher_profile?.approval?.revision ?? 'unknown'
  return { effective, allowed: teachingAllowed(effective), check, refresh,
    accessKey: `${effective.id}:${effective.last_login || 'session'}:${revision}:${effective.teacher_profile?.approval?.status || 'unknown'}` }
}
