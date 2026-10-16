import { useEffect, useId, useRef, useState } from 'react'
import { ArrowDown, ArrowUp, LoaderCircle, MoreVertical, Reply, Send, Trash2, Volume2, VolumeX, X } from 'lucide-react'
import { courseErrorMessage, listAnnouncementComments, createAnnouncementComment, deleteAnnouncementComment, voteAnnouncementComment, setClassroomCommentMute } from '../services/course.service'
import MaterialRemoveDialog from './documents/MaterialRemoveDialog'

function threadOrder(rows) {
  const children = new Map()
  for (const row of rows) {
    const parent = row.parent_id || null
    if (!children.has(parent)) children.set(parent, [])
    children.get(parent).push(row)
  }
  const stack = (children.get(null) || []).map((item) => ({ item, nested: false })).reverse()
  const ordered = []
  while (stack.length) {
    const entry = stack.pop()
    ordered.push(entry)
    for (const item of [...(children.get(entry.item.id) || [])].reverse()) stack.push({ item, nested: true })
  }
  return ordered
}

export default function AnnouncementComments({ courseId, roomId, announcementId, moderationRevision = 0, onModerationChange }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const [busy, setBusy] = useState(false)
  const [draft, setDraft] = useState('')
  const [replyTo, setReplyTo] = useState(null)
  const [menu, setMenu] = useState(null)
  const [remove, setRemove] = useState(null)
  const lock = useRef(false)
  const readController = useRef(null)
  const field = useRef(null)
  const menuBox = useRef(null)
  const menuTrigger = useRef(null)
  const fieldId = useId()

  useEffect(() => {
    let controller
    let pending = false
    let loaded = false
    function refresh() {
      if (pending || lock.current || document.visibilityState === 'hidden') return
      pending = true
      controller = new AbortController()
      const current = controller
      readController.current = current
      listAnnouncementComments(courseId, roomId, announcementId, current.signal)
        .then((value) => {
          if (current.signal.aborted) return
          setData(value)
          if (!loaded) setError('')
          loaded = true
          setReplyTo((target) => target && value.results.some((item) => item.id === target.id && !item.is_deleted) ? target : null)
        })
        .catch((err) => {
          if (current.signal.aborted) return
          if (!loaded || [401, 403, 404].includes(err.status)) setError(courseErrorMessage(err))
          if ([401, 403, 404].includes(err.status)) setData(null)
        })
        .finally(() => { pending = false })
    }
    refresh()
    const timer = setInterval(refresh, 3000)
    window.addEventListener('focus', refresh)
    document.addEventListener('visibilitychange', refresh)
    return () => {
      clearInterval(timer)
      controller?.abort()
      window.removeEventListener('focus', refresh)
      document.removeEventListener('visibilitychange', refresh)
    }
  }, [courseId, roomId, announcementId, moderationRevision, revision])

  useEffect(() => {
    if (!menu) return
    menuBox.current?.querySelector('[role="menuitem"]')?.focus()
    function outside(event) {
      if (!menuBox.current?.contains(event.target) && !menuTrigger.current?.contains(event.target)) setMenu(null)
    }
    function keys(event) {
      if (event.key === 'Escape') { setMenu(null); menuTrigger.current?.focus() }
      if (['ArrowDown', 'ArrowUp'].includes(event.key)) {
        event.preventDefault()
        const items = [...(menuBox.current?.querySelectorAll('[role="menuitem"]') || [])]
        const index = items.indexOf(document.activeElement)
        items[(index + (event.key === 'ArrowDown' ? 1 : items.length - 1)) % items.length]?.focus()
      }
    }
    document.addEventListener('pointerdown', outside)
    document.addEventListener('keydown', keys)
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', keys) }
  }, [menu])

  async function act(action) {
    if (lock.current) return false
    readController.current?.abort()
    lock.current = true; setBusy(true); setError('')
    try { await action(); return true }
    catch (err) {
      setError(typeof err.data?.detail === 'string' ? err.data.detail : courseErrorMessage(err))
      if (err.status === 403) setRevision((value) => value + 1)
      return false
    } finally { lock.current = false; setBusy(false) }
  }
  async function post(event) {
    event.preventDefault()
    if (!draft.trim()) return
    await act(async () => {
      const item = await createAnnouncementComment(courseId, roomId, announcementId, { content: draft.trim(), ...(replyTo ? { parent_id: replyTo.id } : {}) })
      setData((value) => ({ ...value, results: [...value.results, item] }))
      setDraft(''); setReplyTo(null)
    })
  }
  function vote(item, value) {
    act(async () => {
      const updated = await voteAnnouncementComment(courseId, roomId, announcementId, item.id, item.my_vote === value ? 0 : value)
      setData((previous) => ({ ...previous, results: previous.results.map((row) => row.id === item.id ? updated : row) }))
    })
  }
  function mute(userId, name, isMuted) {
    setMenu(null)
    act(async () => {
      await setClassroomCommentMute(courseId, roomId, userId, isMuted)
      setData((value) => ({ ...value,
        muted_students: [...value.muted_students.filter((person) => person.id !== userId), ...(isMuted ? [{ id: userId, name }] : [])],
        results: value.results.map((item) => item.author_id === userId ? { ...item, author_muted: isMuted } : item),
      }))
      onModerationChange?.()
    })
  }
  async function confirmDelete() {
    await act(async () => {
      await deleteAnnouncementComment(courseId, roomId, announcementId, remove.id)
      setData((value) => ({ ...value, results: value.results.map((item) => item.id === remove.id ? { ...item, content: '', is_deleted: true, can_delete: false, upvotes: 0, downvotes: 0, my_vote: 0 } : item) }))
      if (replyTo?.id === remove.id) setReplyTo(null)
      setRemove(null)
    })
  }
  return <section className="announcement-comments" aria-label="Bình luận của thông báo" aria-busy={busy}>
    <div className="comment-section-heading"><h3>Bình luận {data && <span>{data.results.filter((item) => !item.is_deleted).length}</span>}</h3>
      {data && <button type="button" className="comment-text-button" disabled={busy} onClick={() => { setError(''); setRevision((value) => value + 1) }}>Làm mới bình luận</button>}
    </div>
    {error && !remove && <div className="error-banner" role="alert">{error}<button type="button" className="comment-text-button" onClick={() => { setError(''); setRevision((value) => value + 1) }}>Thử lại</button></div>}
    {!data ? !error && <p role="status">Đang tải bình luận...</p> : <>
      {data.can_manage && data.muted_students.length > 0 && <details className="comment-muted-list"><summary>Học viên đang mute ({data.muted_students.length})</summary>
        {data.muted_students.map((person) => <div key={person.id}><span>{person.name}</span><button type="button" className="comment-text-button" aria-label={`Bỏ mute ${person.name}`} disabled={busy} onClick={() => mute(person.id, person.name, false)}><Volume2 size={16} />Bỏ mute</button></div>)}
      </details>}
      <div className="comment-list">{threadOrder(data.results).map(({ item, nested }) => <article key={item.id} className={`comment-row${nested ? ' comment-reply' : ''}`} aria-label={`Bình luận của ${item.author_name}`}>
        <span className="comment-avatar" aria-hidden="true">{item.author_name.split(/\s+/).filter(Boolean).slice(-2).map((word) => word[0]).join('').toUpperCase()}</span>
        <div className="comment-body"><div className="comment-byline"><strong>{item.author_name}</strong>{item.author_role === 'TEACHER' && <span className="comment-teacher">Giáo viên</span>}<time dateTime={item.created_at}>{new Date(item.created_at).toLocaleString('vi-VN', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' })}</time>{data.can_manage && item.author_muted && <span className="comment-mute-badge"><VolumeX size={12} />Đang mute</span>}</div>
          {nested && <span className="comment-reply-label">Trả lời {data.results.find((parent) => parent.id === item.parent_id)?.author_name}</span>}
          <p className={item.is_deleted ? 'comment-deleted' : ''}>{item.is_deleted ? 'Bình luận đã bị xóa.' : item.content}</p>
          {!item.is_deleted && <div className="comment-votes">
            <button type="button" className="comment-vote comment-upvote" aria-label={`Upvote bình luận của ${item.author_name}`} aria-pressed={item.my_vote === 1} disabled={busy} onClick={() => vote(item, 1)}><ArrowUp size={17} /><span>{item.upvotes}</span></button>
            <button type="button" className="comment-vote comment-downvote" aria-label={`Downvote bình luận của ${item.author_name}`} aria-pressed={item.my_vote === -1} disabled={busy} onClick={() => vote(item, -1)}><ArrowDown size={17} /><span>{item.downvotes}</span></button>
          </div>}
        </div>
        <div className="comment-actions">
          {!item.is_deleted && <button type="button" className="icon-button" aria-label={`Trả lời ${item.author_name}`} title="Trả lời" disabled={busy || !data.can_comment} onClick={() => { setReplyTo(item); field.current?.focus() }}><Reply size={18} /></button>}
          {(item.can_delete || (data.can_manage && item.author_role === 'STUDENT')) && <div className="comment-menu-wrap">
            <button type="button" className="icon-button" aria-label={`Tùy chọn bình luận của ${item.author_name}`} aria-haspopup="menu" aria-expanded={menu === item.id} disabled={busy} onClick={(event) => { menuTrigger.current = event.currentTarget; setMenu(menu === item.id ? null : item.id) }}><MoreVertical size={18} /></button>
            {menu === item.id && <div className="comment-menu" role="menu" aria-label="Tùy chọn bình luận" ref={menuBox}>
              {item.can_delete && <button type="button" role="menuitem" onClick={() => { setMenu(null); setRemove(item); setError('') }}><Trash2 size={16} />Xóa bình luận</button>}
              {data.can_manage && item.author_role === 'STUDENT' && <button type="button" role="menuitem" onClick={() => mute(item.author_id, item.author_name, !item.author_muted)}>{item.author_muted ? <Volume2 size={16} /> : <VolumeX size={16} />}{item.author_muted ? 'Bỏ mute học viên' : 'Mute học viên'}</button>}
            </div>}
          </div>}
        </div>
      </article>)}</div>
      {data.can_comment ? <form className="comment-composer" onSubmit={post}>
        {replyTo && <div className="comment-reply-target">Đang trả lời {replyTo.author_name}<button type="button" className="icon-button" aria-label="Hủy trả lời" onClick={() => setReplyTo(null)}><X size={16} /></button></div>}
        <label className="sr-only" htmlFor={fieldId}>Nội dung bình luận</label>
        <textarea ref={field} id={fieldId} value={draft} maxLength={2000} rows={1} disabled={busy} onChange={(event) => setDraft(event.target.value)} placeholder="Viết bình luận..." />
        <button type="submit" className="solid-button" aria-label="Gửi bình luận" disabled={busy || !draft.trim()}>{busy ? <LoaderCircle size={17} className="spin" /> : <Send size={17} />}<span>Gửi</span></button>
      </form> : <p className="comment-muted-notice" role="status"><VolumeX size={17} />Bạn đã bị tắt quyền bình luận trong lớp này.</p>}
    </>}
    {remove && <MaterialRemoveDialog title="" headingText="Xóa bình luận?" descriptionText="Nội dung bình luận sẽ bị xóa. Các câu trả lời bên dưới vẫn được giữ lại." confirmText="Xác nhận xóa" pendingText="Đang xóa..." pending={busy} error={error} onCancel={() => { setRemove(null); setError('') }} onConfirm={confirmDelete} />}
  </section>
}
