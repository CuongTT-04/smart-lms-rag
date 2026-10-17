import { useEffect, useId, useRef, useState } from 'react'
import FilePicker from '../FilePicker'
import { courseErrorMessage } from '../../services/course.service'
import VideoDialog from './VideoDialog'
import { formatVideoTime } from './videoTime'

export default function VideoUploadDialog({ onSave, onClose }) {
  const prefix = useId()
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [file, setFile] = useState(null)
  const [duration, setDuration] = useState(0)
  const [reading, setReading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const pick = useRef(0)
  const readCleanup = useRef(null)
  const lock = useRef(false)
  useEffect(() => () => { pick.current += 1; readCleanup.current?.() }, [])
  function choose(event) {
    const selected = event.target.files?.[0]
    if (!selected) return
    const request = ++pick.current
    readCleanup.current?.()
    if (!/\.(mp4|webm)$/i.test(selected.name) || !selected.size || selected.size > 200 * 1024 * 1024) { setFile(null); setDuration(0); setReading(false); setError('Chọn video MP4/WebM tối đa 200 MiB.'); return }
    setFile(selected); setDuration(0); setReading(true); setError('')
    const media = document.createElement('video')
    const url = URL.createObjectURL(selected)
    media.preload = 'metadata'
    let finished = false
    const timeout = setTimeout(() => finish(0), 30000)
    function cleanup() {
      if (finished) return
      finished = true
      clearTimeout(timeout)
      media.onloadedmetadata = null; media.onerror = null
      URL.revokeObjectURL(url)
      media.removeAttribute('src'); media.load()
    }
    readCleanup.current = cleanup
    function finish(value) {
      if (finished) return
      cleanup()
      if (request !== pick.current) return
      setReading(false)
      if (value > 0 && value <= 14400 && Number.isFinite(value)) setDuration(value)
      else setError('Không đọc được thời lượng hoặc video dài hơn 4 giờ. Hãy chọn MP4/WebM phát được trong trình duyệt.')
    }
    media.onloadedmetadata = () => finish(media.duration)
    media.onerror = () => finish(0)
    media.src = url
  }
  async function submit(event) {
    event.preventDefault()
    if (lock.current || !file || !duration) return
    lock.current = true; setSaving(true); setError('')
    try { await onSave({ title: title.trim(), description: description.trim(), duration, file }) }
    catch (err) { setError(courseErrorMessage(err)) }
    finally { lock.current = false; setSaving(false) }
  }
  return <VideoDialog title="Thêm video buổi học" pending={saving} onClose={onClose}><form className="video-form" onSubmit={submit}>
    {error && <div className="error-banner" role="alert">{error}</div>}
    <label htmlFor={`${prefix}-title`}>Tên video</label><input id={`${prefix}-title`} maxLength={255} required value={title} disabled={saving} onChange={(event) => setTitle(event.target.value)} />
    <label htmlFor={`${prefix}-description`}>Mô tả <small>(Tùy chọn)</small></label><textarea id={`${prefix}-description`} maxLength={5000} rows={3} value={description} disabled={saving} onChange={(event) => setDescription(event.target.value)} />
    <FilePicker id={`${prefix}-file`} label="Tệp video" file={file} accept="video/mp4,video/webm" disabled={saving || reading} onChange={choose} />
    <small className="video-help-copy">MP4 hoặc WebM · tối đa 200 MiB{reading ? ' · Đang đọc thời lượng...' : duration ? ` · ${formatVideoTime(duration)}` : ''}</small>
    <div className="video-dialog-actions"><button type="button" className="outline-button" disabled={saving} onClick={onClose}>Hủy</button><button type="submit" className="solid-button" disabled={saving || reading || !file || !duration || !title.trim()}>{saving ? 'Đang tải video lên...' : 'Tải video lên'}</button></div>
  </form></VideoDialog>
}
