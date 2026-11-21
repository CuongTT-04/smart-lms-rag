import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { ArrowDown, ArrowUp, ChevronDown, CornerDownRight, LoaderCircle, MessageSquare, MoreVertical, RefreshCw, Reply, Send, Trash2, Volume2, VolumeX, X } from 'lucide-react'
import { courseErrorMessage, listAnnouncementComments, createAnnouncementComment, deleteAnnouncementComment, voteAnnouncementComment, setClassroomCommentMute } from '../services/course.service'
import MaterialRemoveDialog from './documents/MaterialRemoveDialog'

const INITIAL_ROOT_LIMIT = 5

function buildThreads(rows) {
  const byId = new Map(rows.map((row) => [row.id, row]))
  const children = new Map()
  const roots = []
  for (const row of rows) {
    if (row.parent_id && byId.has(row.parent_id)) {
      if (!children.has(row.parent_id)) children.set(row.parent_id, [])
      children.get(row.parent_id).push(row)
    } else {
      roots.push(row)
    }
  }
  return roots.map((root) => {
    const replies = []
    const stack = [...(children.get(root.id) || [])].reverse()
    while (stack.length) {
      const current = stack.pop()
      replies.push({ item: current, parentName: byId.get(current.parent_id)?.author_name || '' })
      for (const child of [...(children.get(current.id) || [])].reverse()) stack.push(child)
    }
    return { root, replies }
  })
}

function initialsOf(name) {
  return (name || '').split(/\s+/).filter(Boolean).slice(-2).map((word) => word[0]).join('').toUpperCase() || '?'
}

function formatCommentTime(value) {
  return new Date(value).toLocaleString('vi-VN', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' })
}

export default function AnnouncementComments({ courseId, roomId, announcementId, moderationRevision = 0, onModerationChange, focusCommentId, defaultOpen = true }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const [busy, setBusy] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [draft, setDraft] = useState('')
  const [replyTo, setReplyTo] = useState(null)
  const [menu, setMenu] = useState(null)
  const [remove, setRemove] = useState(null)
  const focusKey = focusCommentId || null
  const [panelState, setPanelState] = useState(() => ({ focus: focusKey, open: defaultOpen || Boolean(focusKey) }))
  const [replyOverrides, setReplyOverrides] = useState({})
  const [showAllRoots, setShowAllRoots] = useState(false)
  const isOpen = panelState.focus === focusKey ? panelState.open : (defaultOpen || Boolean(focusKey))
  const setIsOpen = (next) => setPanelState((previous) => {
    const current = previous.focus === focusKey ? previous.open : (defaultOpen || Boolean(focusKey))
    const open = typeof next === 'function' ? next(current) : next
    return { focus: focusKey, open }
  })
  const lock = useRef(false)
  const readController = useRef(null)
  const field = useRef(null)
  const focusComposerPending = useRef(false)
  const menuBox = useRef(null)
  const menuTrigger = useRef(null)
  const fieldId = useId()
  const panelId = useId()
  const focusedComment = useRef(null)

  const threads = useMemo(() => buildThreads(data?.results || []), [data])
  const ownerRootById = useMemo(() => {
    const map = new Map()
    for (const thread of threads) {
      map.set(thread.root.id, thread.root.id)
      for (const reply of thread.replies) map.set(reply.item.id, thread.root.id)
    }
    return map
  }, [threads])
  const focusedRootId = focusCommentId ? ownerRootById.get(focusCommentId) || null : null
  const focusedRootIndex = focusedRootId ? threads.findIndex((thread) => thread.root.id === focusedRootId) : -1
  const visibleLimit = showAllRoots ? threads.length : Math.max(INITIAL_ROOT_LIMIT, focusedRootIndex >= 0 ? focusedRootIndex + 1 : INITIAL_ROOT_LIMIT)
  const visibleThreads = threads.slice(0, visibleLimit)
  const hiddenRootsCount = Math.max(0, threads.length - visibleThreads.length)
  const activeCount = useMemo(() => (data ? data.results.filter((item) => !item.is_deleted).length : null), [data])

  function isRepliesOpen(rootId) {
    if (Object.prototype.hasOwnProperty.call(replyOverrides, rootId)) return replyOverrides[rootId]
    if (focusedRootId === rootId) return true
    return defaultOpen
  }

  function toggleReplies(rootId) {
    const next = !isRepliesOpen(rootId)
    setReplyOverrides((previous) => ({ ...previous, [rootId]: next }))
  }

  useEffect(() => {
    if (!focusCommentId || !data || !isOpen || focusedComment.current === focusCommentId) return
    const timer = setTimeout(() => {
      const node = document.getElementById(`comment-${focusCommentId}`)
      if (node) { focusedComment.current = focusCommentId; node.scrollIntoView?.({ block: 'center', behavior: 'smooth' }) }
    }, 150)
    return () => clearTimeout(timer)
  }, [focusCommentId, data, isOpen])

  useEffect(() => {
    if (!isOpen || !focusComposerPending.current || !data?.can_comment) return
    focusComposerPending.current = false
    field.current?.focus()
  }, [isOpen, data])

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
        .finally(() => {
          pending = false
          if (!current.signal.aborted) setRefreshing(false)
        })
    }
    refresh()
    const timer = isOpen ? setInterval(refresh, 3000) : null
    window.addEventListener('focus', refresh)
    document.addEventListener('visibilitychange', refresh)
    return () => {
      if (timer) clearInterval(timer)
      controller?.abort()
      window.removeEventListener('focus', refresh)
      document.removeEventListener('visibilitychange', refresh)
    }
  }, [courseId, roomId, announcementId, moderationRevision, revision, isOpen])

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
    const targetParent = replyTo
    await act(async () => {
      const item = await createAnnouncementComment(courseId, roomId, announcementId, { content: draft.trim(), ...(targetParent ? { parent_id: targetParent.id } : {}) })
      setData((value) => ({ ...value, results: [...value.results, item] }))
      if (targetParent) {
        const ownerRoot = ownerRootById.get(targetParent.id) || targetParent.id
        setReplyOverrides((previous) => ({ ...previous, [ownerRoot]: true }))
      } else if (threads.length >= visibleLimit) {
        setShowAllRoots(true)
      }
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
  function openAndCompose() {
    focusComposerPending.current = true
    setIsOpen(true)
    if (isOpen) field.current?.focus()
  }
  function startReply(item, rootId) {
    setReplyTo(item)
    setReplyOverrides((previous) => ({ ...previous, [rootId]: true }))
    field.current?.focus()
  }
  function renderCommentItem(item, rootId, nested = false, parentName = '') {
    const canShowMenu = item.can_delete || (data.can_manage && item.author_role === 'STUDENT')
    return <article id={`comment-${item.id}`} key={item.id} className={`comment-item${focusCommentId === item.id ? ' notification-focus' : ''}${nested ? ' is-reply' : ''}`} aria-label={`Bình luận của ${item.author_name}`}>
      <span className={`comment-avatar${nested ? ' is-small' : ''}`} aria-hidden="true">{initialsOf(item.author_name)}</span>
      <div className="comment-content-col">
        <div className={`comment-bubble${item.is_deleted ? ' is-deleted' : ''}`}>
          <div className="comment-byline">
            <strong>{item.author_name}</strong>
            {item.author_role === 'TEACHER' && <span className="comment-teacher">Giáo viên</span>}
            {data.can_manage && item.author_muted && <span className="comment-mute-badge"><VolumeX size={12} />Đang mute</span>}
            <time dateTime={item.created_at}>{formatCommentTime(item.created_at)}</time>
          </div>
          {nested && parentName && <span className="comment-reply-label">Trả lời {parentName}</span>}
          <p className={item.is_deleted ? 'comment-deleted' : ''}>{item.is_deleted ? 'Bình luận đã bị xóa.' : item.content}</p>
        </div>
        <div className="comment-meta-actions">
          {!item.is_deleted && <>
            <button type="button" className="comment-vote comment-upvote" aria-label={`Upvote bình luận của ${item.author_name}`} aria-pressed={item.my_vote === 1} disabled={busy} onClick={() => vote(item, 1)}><ArrowUp size={15} /><span>{item.upvotes}</span></button>
            <button type="button" className="comment-vote comment-downvote" aria-label={`Downvote bình luận của ${item.author_name}`} aria-pressed={item.my_vote === -1} disabled={busy} onClick={() => vote(item, -1)}><ArrowDown size={15} /><span>{item.downvotes}</span></button>
            <button type="button" className="comment-inline-action" aria-label={`Trả lời ${item.author_name}`} disabled={busy || !data.can_comment} onClick={() => startReply(item, rootId)}><Reply size={14} /><span>Trả lời</span></button>
          </>}
          {canShowMenu && <div className="comment-menu-wrap">
            <button type="button" className="comment-more-button" aria-label={`Tùy chọn bình luận của ${item.author_name}`} aria-haspopup="menu" aria-expanded={menu === item.id} disabled={busy} onClick={(event) => { menuTrigger.current = event.currentTarget; setMenu(menu === item.id ? null : item.id) }}><MoreVertical size={15} /></button>
            {menu === item.id && <div className="comment-menu" role="menu" aria-label="Tùy chọn bình luận" ref={menuBox}>
              {item.can_delete && <button type="button" role="menuitem" onClick={() => { setMenu(null); setRemove(item); setError('') }}><Trash2 size={16} />Xóa bình luận</button>}
              {data.can_manage && item.author_role === 'STUDENT' && <button type="button" role="menuitem" onClick={() => mute(item.author_id, item.author_name, !item.author_muted)}>{item.author_muted ? <Volume2 size={16} /> : <VolumeX size={16} />}{item.author_muted ? 'Bỏ mute học viên' : 'Mute học viên'}</button>}
            </div>}
          </div>}
        </div>
      </div>
    </article>
  }

  const toggleLabel = activeCount === null
    ? 'Bình luận'
    : activeCount > 0 ? `${activeCount} bình luận` : 'Chưa có bình luận'

  return <section className={`announcement-comments${isOpen ? ' is-open' : ''}`} aria-label="Bình luận của thông báo" aria-busy={busy}>
    <div className="comment-bar">
      <button type="button" className="comment-toggle-btn" aria-expanded={isOpen} aria-controls={panelId} onClick={() => setIsOpen((value) => !value)}>
        <MessageSquare size={16} aria-hidden="true" />
        <span>{toggleLabel}</span>
        <ChevronDown size={16} className={`comment-toggle-chevron${isOpen ? ' is-open' : ''}`} aria-hidden="true" />
      </button>
      <div className="comment-bar-actions">
        {!isOpen && data?.can_comment && <button type="button" className="comment-text-button comment-compose-trigger" onClick={openAndCompose}>Viết bình luận</button>}
        {isOpen && data && <button type="button" className="comment-text-button" aria-label="Làm mới bình luận" disabled={busy} onClick={() => { setError(''); setRefreshing(true); setRevision((value) => value + 1) }}><RefreshCw size={14} className={refreshing ? 'spin' : ''} aria-hidden="true" /><span>Làm mới</span></button>}
      </div>
    </div>
    {error && !remove && <div className="error-banner comment-error-banner" role="alert">{error}<button type="button" className="comment-text-button" onClick={() => { setError(''); setRevision((value) => value + 1) }}>Thử lại</button></div>}
    {isOpen && <div id={panelId} className="comment-drawer">
      {!data ? !error && <p className="comment-loading" role="status"><LoaderCircle size={15} className="spin" aria-hidden="true" />Đang tải bình luận...</p> : <>
        {data.can_manage && data.muted_students.length > 0 && <details className="comment-muted-list"><summary>Học viên đang mute ({data.muted_students.length})</summary>
          {data.muted_students.map((person) => <div key={person.id}><span>{person.name}</span><button type="button" className="comment-text-button" aria-label={`Bỏ mute ${person.name}`} disabled={busy} onClick={() => mute(person.id, person.name, false)}><Volume2 size={16} />Bỏ mute</button></div>)}
        </details>}
        {visibleThreads.length > 0 ? <div className="comment-thread-list">
          {visibleThreads.map(({ root, replies }) => {
            const repliesOpen = isRepliesOpen(root.id)
            const repliesId = `${panelId}-replies-${root.id}`
            return <div key={root.id} className={`comment-thread${replies.length > 0 ? ' has-replies' : ''}${repliesOpen && replies.length > 0 ? ' is-expanded' : ''}`}>
              {renderCommentItem(root, root.id, false)}
              {replies.length > 0 && <div className="comment-replies-block">
                {!repliesOpen ? <button type="button" className="comment-replies-toggle" aria-expanded={false} aria-controls={repliesId} onClick={() => toggleReplies(root.id)}>
                  <CornerDownRight size={15} aria-hidden="true" />
                  <span>Xem {replies.length} phản hồi</span>
                </button> : <>
                  <div id={repliesId} className="comment-replies-list">
                    {replies.map(({ item, parentName }) => renderCommentItem(item, root.id, true, parentName))}
                  </div>
                  <button type="button" className="comment-replies-toggle is-collapse" aria-expanded={true} aria-controls={repliesId} onClick={() => toggleReplies(root.id)}>
                    <ChevronDown size={15} className="is-flipped" aria-hidden="true" />
                    <span>Ẩn {replies.length} phản hồi</span>
                  </button>
                </>}
              </div>}
            </div>
          })}
          {hiddenRootsCount > 0 && <button type="button" className="comment-more-roots" onClick={() => setShowAllRoots(true)}>Xem thêm {hiddenRootsCount} bình luận</button>}
          {showAllRoots && threads.length > INITIAL_ROOT_LIMIT && <button type="button" className="comment-more-roots" onClick={() => setShowAllRoots(false)}>Thu gọn bớt bình luận</button>}
        </div> : <p className="comment-empty-state">Chưa có bình luận nào. Hãy mở đầu cuộc thảo luận.</p>}
        {data.can_comment ? <form className="comment-composer" onSubmit={post}>
          {replyTo && <div className="comment-reply-target"><span>Đang trả lời <strong>{replyTo.author_name}</strong></span><button type="button" className="icon-button" aria-label="Hủy trả lời" onClick={() => setReplyTo(null)}><X size={15} /></button></div>}
          <div className="comment-composer-box">
            <label className="sr-only" htmlFor={fieldId}>Nội dung bình luận</label>
            <textarea ref={field} id={fieldId} value={draft} maxLength={2000} rows={1} disabled={busy} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); post(event) }
            }} placeholder={replyTo ? `Trả lời ${replyTo.author_name}...` : 'Viết bình luận...'} />
            <button type="submit" className="comment-send-button" aria-label="Gửi bình luận" disabled={busy || !draft.trim()}>{busy ? <LoaderCircle size={16} className="spin" /> : <Send size={16} />}<span>Gửi</span></button>
          </div>
        </form> : <p className="comment-muted-notice" role="status"><VolumeX size={17} />Bạn đã bị tắt quyền bình luận trong lớp này.</p>}
      </>}
    </div>}
    {remove && <MaterialRemoveDialog title="" headingText="Xóa bình luận?" descriptionText="Nội dung bình luận sẽ bị xóa. Các câu trả lời bên dưới vẫn được giữ lại." confirmText="Xác nhận xóa" pendingText="Đang xóa..." pending={busy} error={error} onCancel={() => { setRemove(null); setError('') }} onConfirm={confirmDelete} />}
  </section>
}
