import { useEffect, useRef, useState } from 'react'
import { CircleHelp, Eye, EyeOff, LoaderCircle, Pencil, Plus, RefreshCw, Trash2, Video } from 'lucide-react'
import { createVideoQuestion, deleteSessionVideo, deleteVideoQuestion, getSessionVideo, getVideoFile, updateSessionVideo, updateVideoQuestion, uploadSessionVideo } from '../../services/video.service'
import { courseErrorMessage } from '../../services/course.service'
import MaterialRemoveDialog from '../documents/MaterialRemoveDialog'
import InteractiveVideoPlayer from './InteractiveVideoPlayer'
import VideoQuestionDialog from './VideoQuestionDialog'
import VideoUploadDialog from './VideoUploadDialog'
import VideoResponses from './VideoResponses'
import VideoDialog from './VideoDialog'
import { formatVideoTime } from './videoTime'
import './videos.css'

function EditVideo({ info, onSave, onClose }) {
  const [title, setTitle] = useState(info.title)
  const [description, setDescription] = useState(info.description)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const lock = useRef(false)
  return <VideoDialog title="Chỉnh sửa video" pending={saving} onClose={onClose}><form className="video-form" onSubmit={async (event) => { event.preventDefault(); if (lock.current) return; lock.current = true; setSaving(true); setError(''); try { await onSave({ title: title.trim(), description: description.trim() }) } catch (err) { setError(courseErrorMessage(err)) } finally { lock.current = false; setSaving(false) } }}>
    {error && <p className="error-banner" role="alert">{error}</p>}
    <label htmlFor="edit-video-title">Tên video</label><input id="edit-video-title" required maxLength={255} disabled={saving} value={title} onChange={(event) => setTitle(event.target.value)} />
    <label htmlFor="edit-video-description">Mô tả</label><textarea id="edit-video-description" rows={3} maxLength={5000} disabled={saving} value={description} onChange={(event) => setDescription(event.target.value)} />
    <div className="video-dialog-actions"><button className="outline-button" type="button" disabled={saving} onClick={onClose}>Hủy</button><button className="solid-button" type="submit" disabled={saving || !title.trim()}>Lưu thay đổi</button></div>
  </form></VideoDialog>
}

export default function SessionVideos({ path, rows, selectedId, canManage, listError, onRefresh, onSelect, uploading = false, onUploadingChange }) {
  const selected = rows.find((item) => item.id === selectedId) || rows[0]
  const [info, setInfo] = useState(null)
  const [src, setSrc] = useState({ id: null, url: '', error: '' })
  const [sourceRevision, setSourceRevision] = useState(0)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const [tab, setTab] = useState('questions')
  const [editing, setEditing] = useState(false)
  const [question, setQuestion] = useState(null)
  const [remove, setRemove] = useState(null)
  const [busy, setBusy] = useState(false)
  const [deleteError, setDeleteError] = useState('')
  const current = useRef(0)
  const player = useRef(null)
  const lock = useRef(false)
  const videoId = selected?.id
  const activeInfo = info?.id === videoId ? info : null

  useEffect(() => {
    if (!videoId) return
    const controller = new AbortController()
    let reading = false
    function refresh() {
      if (reading || lock.current || document.visibilityState === 'hidden') return
      reading = true
      getSessionVideo(path, videoId, controller.signal)
        .then((item) => { if (!controller.signal.aborted) { setInfo(item); setError('') } })
        .catch((err) => { if (!controller.signal.aborted) { setError(courseErrorMessage(err)); if ([401, 403, 404].includes(err.status)) { setInfo(null); player.current?.querySelector('video')?.pause() } } })
        .finally(() => { reading = false })
    }
    refresh()
    const timer = setInterval(refresh, 5000)
    return () => { controller.abort(); clearInterval(timer) }
  }, [path, videoId, revision])

  useEffect(() => {
    if (!videoId) return
    const controller = new AbortController()
    let url
    getVideoFile(path, videoId, controller.signal).then((blob) => {
      if (!controller.signal.aborted) { url = URL.createObjectURL(blob); setSrc({ id: videoId, url }) }
    }).catch((err) => { if (!controller.signal.aborted) setSrc({ id: videoId, url: '', error: courseErrorMessage(err) }) })
    return () => { controller.abort(); if (url) URL.revokeObjectURL(url) }
  }, [path, videoId, sourceRevision])

  async function changePublication() {
    if (lock.current) return
    lock.current = true; setBusy(true); setError('')
    try { await updateSessionVideo(path, videoId, { is_published: !activeInfo.is_published }); await onRefresh() }
    catch (err) { setError(courseErrorMessage(err)) }
    finally { lock.current = false; setBusy(false); setRevision((value) => value + 1) }
  }
  async function confirmDelete() {
    if (lock.current || !remove) return
    lock.current = true; setBusy(true); setDeleteError('')
    try {
      if (remove.kind === 'video') { await deleteSessionVideo(path, videoId); await onRefresh(); onSelect(null) }
      else await deleteVideoQuestion(path, videoId, remove.item.id)
      setRemove(null)
    } catch (err) { setDeleteError(courseErrorMessage(err)) }
    finally { lock.current = false; setBusy(false); setRevision((value) => value + 1) }
  }
  return <section className="session-videos" aria-label="Video buổi học">
    <div className="video-panel-heading"><div><span className="video-eyebrow">VIDEO BUỔI HỌC</span><h2>{activeInfo?.title || 'Bài giảng video'}</h2></div><div className="video-toolbar"><button type="button" className="icon-button" aria-label="Làm mới video" onClick={() => { setError(''); setRevision((value) => value + 1); if (src.id !== videoId || !src.url) setSourceRevision((value) => value + 1); onRefresh() }}><RefreshCw size={18} /></button></div></div>
    {(error || listError) && <div className="error-banner" role="alert">{error || listError}</div>}
    {!selected ? <div className="video-empty"><Video size={42} /><h3>{canManage ? 'Thêm bài giảng đầu tiên' : 'Chưa có video được công bố'}</h3><p>{canManage ? 'Tải video lên và đặt các câu hỏi tại mốc thời gian để học viên tương tác.' : 'Video sẽ xuất hiện tại đây khi giáo viên công bố.'}</p></div> : !activeInfo ? !error && <p role="status"><LoaderCircle className="spin" size={18} />Đang tải video...</p> : <>
      <div className="video-meta-toolbar"><span className={`video-publication ${activeInfo.is_published ? 'is-published' : ''}`}>{activeInfo.is_published ? 'Đã công bố' : 'Bản nháp'}</span><span>{formatVideoTime(activeInfo.duration)} · {activeInfo.questions.length} câu hỏi</span>{canManage && <div className="video-toolbar"><button type="button" className="outline-button" disabled={busy} onClick={() => { player.current?.querySelector('video')?.pause(); setQuestion({ creating: true, start: current.current }) }}><Plus size={17} />Tạo câu hỏi</button><button type="button" className="outline-button" disabled={busy} onClick={changePublication}>{activeInfo.is_published ? <EyeOff size={17} /> : <Eye size={17} />}{activeInfo.is_published ? 'Thu hồi công bố' : 'Công bố video'}</button><button type="button" className="icon-button" aria-label="Chỉnh sửa video" disabled={busy} onClick={() => setEditing(true)}><Pencil size={18} /></button><button type="button" className="icon-button video-danger" aria-label="Gỡ video" disabled={busy} onClick={() => { setDeleteError(''); setRemove({ kind: 'video' }) }}><Trash2 size={18} /></button></div>}</div>
      <div ref={player}>{src.url && src.id === videoId ? <InteractiveVideoPlayer key={canManage ? videoId : `${videoId}:${activeInfo.questions.map((item) => `${item.id}.${item.revision}`).join(',')}`} path={path} info={activeInfo} src={src.url} canManage={canManage} onCurrentTime={(value) => { current.current = value }} /> : src.id === videoId && src.error ? <p className="error-banner" role="alert">{src.error}</p> : <p className="video-source-loading" role="status"><LoaderCircle className="spin" size={20} />Đang tải tệp video...</p>}</div>
      {activeInfo.description && <p className="video-description">{activeInfo.description}</p>}
      {canManage ? <><nav className="detail-tabs" aria-label="Quản lý video"><button type="button" className={tab === 'questions' ? 'active' : ''} onClick={() => setTab('questions')}>Câu hỏi theo mốc</button><button type="button" className={tab === 'responses' ? 'active' : ''} onClick={() => setTab('responses')}>Câu trả lời học viên</button></nav>{tab === 'responses' ? <VideoResponses key={videoId} path={path} videoId={videoId} /> : <div className="video-question-list">{activeInfo.questions.map((item) => <article key={item.id}><span className="video-question-time">{formatVideoTime(item.start_time)}</span><div><strong>{item.prompt}</strong><p>{item.kind === 'MCQ' ? item.multiple ? 'Trắc nghiệm nhiều đáp án' : 'Trắc nghiệm một đáp án' : 'Tự luận'}{item.rewind_time != null ? ` · Sai: quay lại ${formatVideoTime(item.rewind_time)}` : ''} · Phiên bản {item.revision}</p></div><button type="button" className="icon-button" aria-label={`Sửa câu hỏi ${item.prompt}`} onClick={() => { player.current?.querySelector('video')?.pause(); setQuestion({ item }) }}><Pencil size={17} /></button><button type="button" className="icon-button video-danger" aria-label={`Gỡ câu hỏi ${item.prompt}`} onClick={() => { setDeleteError(''); setRemove({ kind: 'question', item }) }}><Trash2 size={17} /></button></article>)}{!activeInfo.questions.length && <div className="video-empty compact"><CircleHelp size={28} /><p>Chưa có câu hỏi. Dừng ở vị trí mong muốn và nhấn “Tạo câu hỏi”.</p></div>}</div>}</> : <p className="video-help-copy">Bạn có thể tua trong phần đã xem. Hoàn thành video và các câu hỏi để mở toàn bộ thanh tua.</p>}
    </>}
    {uploading && <VideoUploadDialog onClose={() => onUploadingChange(false)} onSave={async (values) => { const item = await uploadSessionVideo(path, values); await onRefresh(); onSelect(item.id); setError(''); onUploadingChange(false) }} />}
    {editing && activeInfo && <EditVideo info={activeInfo} onClose={() => setEditing(false)} onSave={async (values) => { await updateSessionVideo(path, videoId, values); setRevision((value) => value + 1); await onRefresh(); setEditing(false) }} />}
    {question && activeInfo && <VideoQuestionDialog key={question.item?.id || 'new'} question={question.item} startTime={question.start} duration={activeInfo.duration} onClose={() => setQuestion(null)} onSave={async (values) => { if (question.item) await updateVideoQuestion(path, videoId, question.item.id, values); else await createVideoQuestion(path, videoId, values); setQuestion(null); setRevision((value) => value + 1) }} />}
    {remove && <MaterialRemoveDialog headingText={remove.kind === 'video' ? 'Gỡ video?' : 'Gỡ câu hỏi?'} descriptionText={remove.kind === 'video' ? 'Video không còn hiển thị cho học viên. Lịch sử câu trả lời được giữ nội bộ.' : 'Câu hỏi không còn chặn video. Lịch sử trả lời cũ vẫn được giữ.'} confirmText="Xác nhận gỡ" pendingText="Đang gỡ..." title="" pending={busy} error={deleteError} onCancel={() => setRemove(null)} onConfirm={confirmDelete} />}
  </section>
}
