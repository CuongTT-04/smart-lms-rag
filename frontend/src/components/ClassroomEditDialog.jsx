import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Check, LoaderCircle, Trash2 } from 'lucide-react'
import { courseErrorMessage, updateClassroom, deleteClassroom } from '../services/course.service'
import '../documents.css'

export default function ClassroomEditDialog({ courseId, room, onClose, onSaved, onDeleted }) {
  const [draft, setDraft] = useState({ name: room.name, visibility: room.visibility ?? 'PRIVATE', require_approval: room.require_approval ?? false, is_join_enabled: room.is_join_enabled })
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const locked = useRef(false)
  const dialog = useRef(null)
  const close = useRef(onClose)
  useEffect(() => { close.current = confirmDelete ? () => setConfirmDelete(false) : onClose }, [onClose, confirmDelete])
  useEffect(() => {
    const previous = document.activeElement
    const oldOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    dialog.current.querySelector('input').focus()
    const keydown = (event) => {
      if (event.key === 'Escape') { event.preventDefault(); if (!locked.current) close.current(); return }
      if (event.key !== 'Tab') return
      const nodes = [...dialog.current.querySelectorAll('input, select, button')].filter((node) => !node.disabled)
      const first = nodes[0], last = nodes.at(-1)
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
    }
    document.addEventListener('keydown', keydown)
    return () => { document.removeEventListener('keydown', keydown); document.body.style.overflow = oldOverflow; if (previous?.isConnected) previous.focus() }
  }, [])
  useEffect(() => { dialog.current.querySelector('input, button')?.focus() }, [confirmDelete])
  function change(field, value) { setDraft((current) => ({ ...current, [field]: value })) }
  async function remove() {
    if (locked.current) return
    locked.current = true; setSaving(true); setError('')
    try { await deleteClassroom(courseId, room.id); onDeleted?.(room.id) }
    catch (err) { setError(courseErrorMessage(err)) }
    finally { locked.current = false; setSaving(false) }
  }
  async function save(event) {
    event.preventDefault()
    if (locked.current || !draft.name.trim()) return
    locked.current = true; setSaving(true); setError('')
    try { const updated = await updateClassroom(courseId, room.id, { ...draft, name: draft.name.trim() }); onSaved(updated) }
    catch (err) { setError(courseErrorMessage(err)) }
    finally { locked.current = false; setSaving(false) }
  }
  return createPortal(<div className="modal-layer" onClick={(event) => { if (event.target === event.currentTarget && !locked.current) close.current() }}>
    <section ref={dialog} className="form-modal classroom-edit-dialog" role="dialog" aria-modal="true" aria-labelledby="classroom-edit-title">
      <h2 id="classroom-edit-title">{confirmDelete ? 'Xóa lớp học?' : 'Chỉnh sửa lớp học'}</h2>
      {confirmDelete ? <>
        <p>Bạn muốn xóa lớp <strong>{room.name}</strong>? Các buổi học và học liệu trong lớp sẽ được gỡ, học viên không còn truy cập lớp và các yêu cầu tham gia đang chờ sẽ bị hủy.</p>
        {error && <div className="error-banner" role="alert">{error}</div>}
        <div className="modal-actions"><button type="button" className="outline-button" disabled={saving} onClick={() => { setConfirmDelete(false); setError('') }}>Hủy</button><button type="button" className="material-danger-button" disabled={saving} onClick={remove}>{saving ? 'Đang xóa…' : 'Xác nhận xóa'}</button></div>
      </> : <form onSubmit={save}>
        {error && <div className="error-banner" role="alert">{error}</div>}
        <label>Tên lớp<input required maxLength={255} value={draft.name} disabled={saving} onChange={(event) => change('name', event.target.value)} /></label>
        <label>Mức hiển thị<select value={draft.visibility} disabled={saving} onChange={(event) => change('visibility', event.target.value)}><option value="PRIVATE">Riêng tư</option><option value="PUBLIC">Công khai</option></select></label>
        <label className="classroom-edit-check"><input type="checkbox" checked={draft.require_approval} disabled={saving} onChange={(event) => change('require_approval', event.target.checked)} />Yêu cầu giáo viên xét duyệt</label>
        <label className="classroom-edit-check"><input type="checkbox" checked={draft.is_join_enabled} disabled={saving} onChange={(event) => change('is_join_enabled', event.target.checked)} />Mở đăng ký</label>
        <div className="modal-actions"><button type="button" className="material-danger-button classroom-delete-action" disabled={saving} onClick={() => { setError(''); setConfirmDelete(true) }}><Trash2 size={17} /> Xóa lớp học</button><button type="button" className="outline-button" disabled={saving} onClick={onClose}>Hủy</button><button className="solid-button" disabled={saving || !draft.name.trim()}>{saving ? <LoaderCircle className="spin" size={17} /> : <Check size={17} />} Lưu chỉnh sửa</button></div>
      </form>}
    </section>
  </div>, document.body)
}
