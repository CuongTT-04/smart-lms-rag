import { useEffect, useRef, useState } from 'react'
import { CheckCircle2, LoaderCircle } from 'lucide-react'
import { completeClassroomDocument, courseErrorMessage } from '../../services/course.service'

export function ClassroomProgressBadge({ progress, loading = false, error = '' }) {
  if (loading && !progress) {
    return <span className="learning-progress-badge is-loading" role="status"><LoaderCircle size={15} className="spin" aria-hidden="true" />Đang tải tiến độ…</span>
  }
  if (error && !progress) {
    return <span className="learning-progress-badge is-error" role="status">{error}</span>
  }
  if (!progress) return null
  if (!progress.has_activities) {
    return <span className="learning-progress-badge is-empty">Chưa có hoạt động</span>
  }
  const percent = Math.round(Number(progress.percent || 0) * 100) / 100
  return <span className={`learning-progress-badge ${progress.completed_at ? 'is-complete' : ''}`} aria-label={`Tiến độ lớp học: ${progress.completed_activities}/${progress.total_activities} hoạt động (${percent}%)`}>
    {progress.completed_at && <CheckCircle2 size={15} aria-hidden="true" />}
    <span>{progress.completed_activities}/{progress.total_activities} hoạt động · {percent}%</span>
  </span>
}

export function SessionProgressBadge({ progress, sessionId }) {
  if (!progress || !sessionId) return null
  const session = progress.sessions?.find((item) => item.session_id === sessionId)
  if (!session) return null
  if (!session.total_activities) {
    return <span className="session-progress-badge is-empty">Chưa có hoạt động</span>
  }
  return <span className={`session-progress-badge ${session.completed_activities === session.total_activities ? 'is-complete' : ''}`}>
    {session.completed_activities}/{session.total_activities} hoàn thành
  </span>
}

export function DocumentCompletionButton({ courseId, classroomId, versionId, documentLoaded = false, completed = false, onCompleted }) {
  const scopeKey = `${courseId || ''}:${classroomId || ''}:${versionId || ''}`
  const [state, setState] = useState({ scope: scopeKey, pending: false, error: '' })
  const pendingRef = useRef(false)
  const controllerRef = useRef(null)
  const epochRef = useRef(0)

  useEffect(() => {
    pendingRef.current = false
    controllerRef.current?.abort()
    epochRef.current += 1
    return () => {
      controllerRef.current?.abort()
      epochRef.current += 1
    }
  }, [scopeKey])

  const pending = state.scope === scopeKey ? state.pending : false
  const error = state.scope === scopeKey ? state.error : ''
  const ready = Boolean(courseId && classroomId && versionId && documentLoaded)

  async function handleComplete() {
    if (pendingRef.current || !ready || completed) return
    pendingRef.current = true
    const epoch = ++epochRef.current
    const controller = new AbortController()
    controllerRef.current = controller
    setState({ scope: scopeKey, pending: true, error: '' })
    try {
      const updated = await completeClassroomDocument(courseId, classroomId, versionId, controller.signal)
      if (controller.signal.aborted || epochRef.current !== epoch) return
      setState({ scope: scopeKey, pending: false, error: '' })
      await onCompleted?.(updated)
    } catch (err) {
      if (controller.signal.aborted || epochRef.current !== epoch) return
      setState({ scope: scopeKey, pending: false, error: courseErrorMessage(err) })
    } finally {
      if (epochRef.current === epoch) pendingRef.current = false
    }
  }

  if (completed) {
    return <span className="document-completed-pill" role="status" aria-label="Đã học phiên bản tài liệu hiện tại">
      <CheckCircle2 size={16} aria-hidden="true" />Đã học
    </span>
  }

  return <div className="document-completion-control">
    <button
      type="button"
      className="outline-button"
      disabled={!ready || pending}
      aria-label="Đánh dấu đã học tài liệu này"
      onClick={handleComplete}
    >
      {pending ? <LoaderCircle size={16} className="spin" aria-hidden="true" /> : <CheckCircle2 size={16} aria-hidden="true" />}
      {pending ? 'Đang ghi nhận…' : 'Đánh dấu đã học'}
    </button>
    {error && <p className="error-banner" role="alert">{error}</p>}
  </div>
}
