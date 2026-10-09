import { useEffect, useState } from 'react'
import { getAnnouncementImage } from '../services/course.service'

export default function AnnouncementImage({ courseId, roomId, announcementId }) {
  const [src, setSrc] = useState('')
  const [error, setError] = useState(false)
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    let url
    getAnnouncementImage(courseId, roomId, announcementId, controller.signal)
      .then((blob) => {
        if (controller.signal.aborted) return
        url = URL.createObjectURL(blob); setSrc(url)
      })
      .catch(() => { if (!controller.signal.aborted) setError(true) })
    return () => { controller.abort(); if (url) URL.revokeObjectURL(url) }
  }, [courseId, roomId, announcementId, revision])
  return src ? <img className="class-announcement-image" src={src} alt="Ảnh đính kèm thông báo" /> : error ? <button type="button" className="outline-button" onClick={() => { setError(false); setRevision((v) => v + 1) }}>Tải lại ảnh</button> : <p role="status">Đang tải ảnh...</p>
}
