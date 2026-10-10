import { useEffect, useRef, useState } from 'react'
import { Link, LoaderCircle, MessageSquare, Plus, RefreshCw, X } from 'lucide-react'
import { courseErrorMessage, createClassroomAnnouncement, listClassroomAnnouncements } from '../services/course.service'

import AnnouncementImage from './AnnouncementImage'
import FilePicker from './FilePicker'

export default function ClassroomAnnouncements({ courseId, roomId, canManage = true }) {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [revision, setRevision] = useState(0)
  const [editing, setEditing] = useState(false)
  const [content, setContent] = useState('')
  const [image, setImage] = useState(null)
  const [preview, setPreview] = useState('')
  const [link, setLink] = useState('')
  const fileInput = useRef(null)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const lock = useRef(false)
  const trigger = useRef(null)
  useEffect(() => {
    const controller = new AbortController()
    listClassroomAnnouncements(courseId, roomId, controller.signal)
      .then((items) => { if (!controller.signal.aborted) setRows(items) })
      .catch((err) => { if (!controller.signal.aborted) setError(courseErrorMessage(err)) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [courseId, roomId, revision])
  useEffect(() => {
    if (!image) return
    const reader = new FileReader()
    reader.onload = () => setPreview(reader.result)
    reader.readAsDataURL(image)
    return () => { reader.onload = null; if (reader.readyState === 1) reader.abort() }
  }, [image])
  function clearAttachment() {
    setImage(null); setPreview('')
    if (fileInput.current) fileInput.current.value = ''
  }
  function selectImage(event) {
    const file = event.target.files?.[0]
    if (!file) return
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024) {
      setError('Chọn ảnh JPG, PNG hoặc WebP, tối đa 5 MB.')
      event.target.value = ''; return
    }
    setError(''); setPreview(''); setImage(file)
  }
  async function post(event) {
    event.preventDefault()
    if (lock.current || !content.trim()) return
    if (link.trim() && !/^https?:\/\//i.test(link.trim())) { setError('Link phải bắt đầu bằng https:// hoặc http://.'); return }
    lock.current = true; setSaving(true); setError('')
    try {
      const item = await createClassroomAnnouncement(courseId, roomId, { content: content.trim(), ...(link.trim() ? { link: link.trim() } : {}), ...(image ? { image } : {}) })
      setRows((items) => [item, ...items]); setContent(''); setLink(''); clearAttachment(); setEditing(false)
      trigger.current?.focus()
    } catch (err) { setError(courseErrorMessage(err)) }
    finally { lock.current = false; setSaving(false) }
  }
  return <section className="class-news" aria-label="Bảng tin của lớp">
    <div className="class-content-toolbar">
      {canManage && <button ref={trigger} type="button" className="solid-button" onClick={() => { setEditing(true); setError('') }} disabled={editing || loading}><Plus size={18} />Thêm mới</button>}
      <button type="button" className="icon-button" aria-label="Tải lại bảng tin" disabled={loading || saving} onClick={() => { setLoading(true); setError(''); setRevision((v) => v + 1) }}><RefreshCw size={18} /></button>
    </div>
    {error && <div className="error-banner" role="alert">{error}</div>}
    {editing && <form className="class-announcement-composer" onSubmit={post}>
      <label htmlFor="class-announcement-content">Nội dung thông báo</label>
      <textarea id="class-announcement-content" autoFocus maxLength={5000} rows={5} placeholder="Viết thông báo cho lớp..." value={content} disabled={saving} onChange={(event) => setContent(event.target.value)} />
      <div className="class-announcement-attachments">
        <div className="class-attachment-image-field"><FilePicker label="Ảnh đính kèm" inputRef={fileInput} id="class-announcement-image" file={image} accept="image/jpeg,image/png,image/webp" onChange={selectImage} disabled={saving} /><small>JPG, PNG hoặc WebP · tối đa 5 MB</small></div>
        <div className="class-attachment-link-field"><label htmlFor="class-announcement-link"><Link size={18} />Đường link</label><input id="class-announcement-link" type="url" placeholder="https://..." maxLength={2000} value={link} onChange={(event) => setLink(event.target.value)} disabled={saving} />{link && <button type="button" className="icon-button" aria-label="Bỏ đường link" disabled={saving} onClick={() => setLink('')}><X size={17} /></button>}</div>
      </div>
      {image && <div className="class-attachment-preview">{preview && <img src={preview} alt="Xem trước ảnh đính kèm" />}<span>{image.name}</span><button type="button" className="outline-button" disabled={saving} onClick={clearAttachment}><X size={17} />Bỏ ảnh</button></div>}
      <div className="class-composer-actions"><button type="button" className="outline-button" disabled={saving} onClick={() => { setEditing(false); setContent(''); setLink(''); clearAttachment(); setError(''); trigger.current?.focus() }}>Hủy</button><button type="submit" className="solid-button" disabled={saving || !content.trim()}>{saving && <LoaderCircle size={18} className="spin" />}{saving ? 'Đang đăng...' : 'Đăng thông báo'}</button></div>
    </form>}
    {loading ? <p className="class-loading">Đang tải bảng tin...</p> : rows.length ? <div className="class-announcements">{rows.map((item) => <article className="class-announcement-card" key={item.id}><header><strong>{item.author_name || 'Giáo viên'}</strong><time dateTime={item.created_at}>{new Date(item.created_at).toLocaleString('vi-VN')}</time></header><p>{item.content}</p>{item.has_image && <AnnouncementImage courseId={courseId} roomId={roomId} announcementId={item.id} />}{/^https?:\/\//i.test(item.link || '') && <a className="class-announcement-link" href={item.link} target="_blank" rel="noopener noreferrer"><Link size={18} />{item.link}</a>}</article>)}</div> : !error && <div className="class-session-empty class-tab-placeholder"><span><MessageSquare size={32} /></span><h2>Bảng tin của lớp</h2><p>Thông báo và cập nhật dành cho lớp sẽ hiển thị tại đây.</p></div>}
  </section>
}
