import { useState } from 'react'

export default function UserAvatar({ user, className = 'profile-avatar', preview }) {
  const [failed, setFailed] = useState(null)
  const url = preview || user.avatar_url
  const initials = (user.full_name || user.username || 'OH').trim().split(/\s+/).slice(-2).map((part) => part[0]).join('').toUpperCase()
  return <span className={`${className} user-avatar`}>
    {url && failed !== url ? <img src={url} alt={`Ảnh đại diện của ${user.full_name || user.username}`} onError={() => setFailed(url)} /> : initials}
  </span>
}
