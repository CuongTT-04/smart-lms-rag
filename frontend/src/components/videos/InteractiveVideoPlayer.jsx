import { useCallback, useEffect, useRef, useState } from 'react'
import { CheckCircle2, Maximize, Pause, Play, RotateCcw, Volume2 } from 'lucide-react'
import { answerVideoQuestion, getSessionVideo, saveVideoProgress } from '../../services/video.service'
import { courseErrorMessage } from '../../services/course.service'
import { firstCheckpoint, formatVideoTime, seekTarget } from './videoTime'
import VideoCheckpointDialog from './VideoCheckpointDialog'
import VideoAnswersReview from './VideoAnswersReview'

export default function InteractiveVideoPlayer({ path, info, src, canManage, onCurrentTime }) {
  const video = useRef(null)
  const wrapper = useRef(null)
  const [position, setPosition] = useState(info.progress?.position || 0)
  const [playing, setPlaying] = useState(false)
  const [volume, setVolume] = useState(1)
  const [question, setQuestion] = useState(null)
  const [choices, setChoices] = useState([])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [noticeVariant, setNoticeVariant] = useState('info')
  const showNotice = useCallback((text, variant = 'info') => { setNotice(text); setNoticeVariant(variant) }, [])
  const [error, setError] = useState('')
  const [completed, setCompleted] = useState(info.progress?.completed || false)
  const frontier = useRef(info.progress?.seekable_until ?? info.progress?.watched_until ?? info.progress?.position ?? 0)
  const watched = useRef(info.progress?.completed || false)
  const recovering = useRef(false)
  const [answerRevision, setAnswerRevision] = useState(0)
  const passed = useRef(new Set(info.progress?.passed_ids || []))
  const revisions = useRef(new Map(info.questions.map((item) => [item.id, item.revision])))
  const latest = useRef(info)
  const clock = useRef({ position: info.progress?.position || 0, time: 0 })
  const ready = useRef(false)
  const programmatic = useRef(false)
  const gate = useRef(false)
  const saving = useRef(null)
  const answerLock = useRef(false)
  const attempt = useRef(null)
  const alive = useRef(true)

  useEffect(() => {
    latest.current = info
    for (const item of info.questions) {
      if (revisions.current.get(item.id) !== item.revision) passed.current.delete(item.id)
      revisions.current.set(item.id, item.revision)
    }
    for (const id of info.progress?.passed_ids || []) passed.current.add(id)
  }, [info])

  function move(time) {
    if (!video.current) return
    programmatic.current = true
    video.current.currentTime = time
    clock.current = { position: time, time: performance.now() }
    setPosition(time)
    onCurrentTime?.(time)
  }
  function seekLimit() {
    const pending = firstCheckpoint(latest.current.questions, passed.current)
    return canManage || (watched.current && !pending) ? info.duration : Math.min(frontier.current, pending?.start_time ?? info.duration)
  }
  function syncProgress(progress, reset = false) {
    if (!progress) return
    if (reset) frontier.current = progress.seekable_until ?? progress.position
    else frontier.current = Math.max(frontier.current, progress.seekable_until ?? progress.position ?? 0)
    watched.current = reset ? !!progress.completed : watched.current || !!progress.completed
    for (const id of progress.passed_ids || []) passed.current.add(id)
    if (alive.current) setCompleted(watched.current)
  }
  async function persist(time, force = false) {
    if (canManage) return null
    if (saving.current && !force) return null
    const previous = saving.current
    const request = (previous ? previous.catch(() => {}) : Promise.resolve()).then(() => saveVideoProgress(path, info.id, time))
    saving.current = request
    try {
      const result = await request
      if (alive.current) syncProgress(result)
      return result
    } finally { if (saving.current === request) saving.current = null }
  }
  async function recover(err) {
    if (!alive.current || recovering.current) return
    recovering.current = true
    ready.current = false
    video.current?.pause()
    setError(typeof err.data?.detail === 'string' ? err.data.detail : courseErrorMessage(err))
    try {
      const current = await getSessionVideo(path, info.id)
      if (alive.current && current.progress) {
        syncProgress(current.progress, true); move(current.progress.position); ready.current = true
      }
    } catch { if (alive.current) { video.current?.removeAttribute('src'); video.current?.load() } }
    finally { recovering.current = false }
  }
  async function openCheckpoint(item) {
    if (gate.current || canManage) return
    gate.current = true
    video.current?.pause()
    move(item.start_time)
    setError(''); showNotice('')
    try {
      await persist(item.start_time, true)
      if (alive.current) { setChoices([]); setText(''); attempt.current = null; setQuestion(item) }
    } catch (err) { gate.current = false; recover(err) }
  }
  function loaded() {
    ready.current = true
    const position = latest.current.progress?.position || 0
    move(Math.min(position, info.duration))
    const pending = firstCheckpoint(latest.current.questions, passed.current)
    if (!canManage && pending && position >= pending.start_time - 0.1) openCheckpoint(pending)
  }
  function tick() {
    const element = video.current
    if (!element || !ready.current) return
    if (gate.current) { element.pause(); return }
    const time = element.currentTime
    const pending = firstCheckpoint(latest.current.questions, passed.current)
    const naturalLimit = clock.current.position + Math.max(1, (performance.now() - clock.current.time) / 1000 + 0.5)
    if (!canManage && !watched.current && time > Math.max(seekLimit(), naturalLimit)) {
      move(clock.current.position); showNotice('Chỉ được tua trong phần đã xem. Hãy tiếp tục xem video để mở phần tiếp theo.', 'warning'); return
    }
    const observed = !canManage && pending ? Math.min(time, pending.start_time) : time
    frontier.current = Math.max(frontier.current, observed)
    clock.current = { position: observed, time: performance.now() }
    programmatic.current = false
    setPosition(observed); onCurrentTime?.(observed)
    if (!canManage && pending && time >= pending.start_time - 0.05) openCheckpoint(pending)
  }
  function seeking() {
    if (canManage || !ready.current) return
    if (programmatic.current && Math.abs(video.current.currentTime - clock.current.position) < 0.25) { programmatic.current = false; return }
    programmatic.current = false
    if (video.current.currentTime > seekLimit() + 0.05) {
      move(clock.current.position)
      showNotice('Chỉ được tua trong phần đã xem, không được tua tiến đến phần chưa xem.', 'warning')
    } else {
      clock.current = { position: video.current.currentTime, time: performance.now() }
      setPosition(video.current.currentTime); onCurrentTime?.(video.current.currentTime)
    }
  }
  function seek(target) {
    const limit = seekLimit()
    if (Number(target) > limit + 0.05) { showNotice('Chỉ được tua trong phần đã xem, không được tua tiến đến phần chưa xem.', 'warning'); return }
    const allowed = seekTarget(target, limit, info.duration, canManage || watched.current)
    video.current?.pause(); move(allowed)
    if (!canManage) persist(allowed, true).catch(recover)
  }
  function reviewKnowledge() {
    if (answerLock.current || !question) return
    const target = Math.max(0, question.start_time - 10)
    setQuestion(null); gate.current = false
    showNotice('Xem lại kiến thức rồi tiếp tục đến mốc câu hỏi.')
    seek(target)
  }
  function paused() {
    setPlaying(false)
    if (!canManage && ready.current && !gate.current) persist(clock.current.position, true).catch(recover)
  }
  async function togglePlay() {
    if (!ready.current || gate.current) return
    const pending = firstCheckpoint(latest.current.questions, passed.current)
    if (!canManage && pending && clock.current.position >= pending.start_time - 0.05) { openCheckpoint(pending); return }
    if (!video.current.paused) video.current.pause()
    else {
      try { await video.current.play() } catch { setError('Không thể phát video. Hãy nhấn Phát để thử lại hoặc liên hệ giáo viên.') }
    }
  }
  async function submit(event) {
    event.preventDefault()
    if (answerLock.current || !question) return
    answerLock.current = true; setBusy(true); setError('')
    const content = { revision: question.revision, ...(question.kind === 'MCQ' ? { selected_ids: choices } : { text: text.trim() }) }
    const fingerprint = JSON.stringify(content)
    if (attempt.current?.fingerprint !== fingerprint) attempt.current = { fingerprint, id: crypto.randomUUID() }
    try {
      const result = await answerVideoQuestion(path, info.id, question.id, { ...content, request_id: attempt.current.id })
      if (!alive.current) return
      setAnswerRevision((value) => value + 1)
      if (result.progress) syncProgress(result.progress, true)
      if (result.is_correct === false) {
        attempt.current = null
        if (result.rewind_to != null) {
          setQuestion(null); gate.current = false; frontier.current = result.progress?.seekable_until ?? result.rewind_to; move(result.rewind_to)
          showNotice(`Câu trả lời chưa đúng. Video quay lại ${formatVideoTime(result.rewind_to)} để bạn xem lại kiến thức.`, 'warning')
          await video.current.play().catch(() => {})
        } else showNotice('Câu trả lời chưa đúng. Bạn có thể thử lại hoặc xem lại kiến thức trước mốc này.', 'warning')
      } else {
        passed.current.add(question.id)
        setQuestion(null); gate.current = false
        showNotice(question.kind === 'TEXT' ? 'Đã gửi câu trả lời tự luận. Giáo viên có thể xem lại; bạn được tiếp tục video.' : 'Chính xác! Bạn có thể tiếp tục video.', 'success')
        if (!watched.current) await video.current.play().catch(() => {})
      }
    } catch (err) { if (alive.current) setError(typeof err.data?.detail === 'string' ? err.data.detail : courseErrorMessage(err)) }
    finally { answerLock.current = false; if (alive.current) setBusy(false) }
  }
  useEffect(() => {
    if (!notice) return
    const timer = setTimeout(() => showNotice(''), 5000)
    return () => clearTimeout(timer)
  }, [notice, showNotice])
  useEffect(() => {
    if (!error) return
    const timer = setTimeout(() => setError(''), 5000)
    return () => clearTimeout(timer)
  }, [error])
  useEffect(() => {
    alive.current = true
    if (canManage) return () => { alive.current = false }
    const timer = setInterval(() => {
      if (ready.current && video.current && !video.current.paused && !gate.current) persist(video.current.currentTime).catch(recover)
    }, 2000)
    function leave() {
      if (ready.current && !gate.current) persist(clock.current.position, true).catch(() => {})
    }
    function visibility() {
      if (document.visibilityState === 'hidden') { video.current?.pause(); leave() }
    }
    window.addEventListener('pagehide', leave)
    document.addEventListener('visibilitychange', visibility)
    return () => { leave(); alive.current = false; clearInterval(timer); window.removeEventListener('pagehide', leave); document.removeEventListener('visibilitychange', visibility) }
    // The component is keyed by video ID; event handlers use refs for live progress/questions.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, info.id, canManage])

  return <><div className="interactive-video" ref={wrapper}>
    <div className="video-screen" onKeyDown={(event) => {
      if (['INPUT', 'TEXTAREA', 'BUTTON'].includes(event.target.tagName)) return
      if (event.key === 'ArrowRight') { event.preventDefault(); seek(Math.min(clock.current.position + 5, seekLimit())) }
      if (event.key === 'ArrowLeft') { event.preventDefault(); seek(clock.current.position - 5) }
      if (event.key === ' ') { event.preventDefault(); togglePlay() }
    }} tabIndex={0} aria-label="Trình phát video">
      <video ref={video} src={src} preload="metadata" controls={false} disablePictureInPicture disableRemotePlayback playsInline controlsList="nodownload noplaybackrate noremoteplayback" onLoadedMetadata={loaded} onTimeUpdate={tick} onSeeking={seeking} onSeeked={() => { programmatic.current = false }} onRateChange={() => { if (!canManage && !watched.current && video.current.playbackRate !== 1) video.current.playbackRate = 1 }} onPlay={() => { if (gate.current) video.current.pause(); else { clock.current.time = performance.now(); setPlaying(true) } }} onPause={paused} onEnded={() => { setPlaying(false); if (!canManage) persist(info.duration, true).catch(recover) }} onError={() => setError('Không thể phát tệp video. Hãy tải lại hoặc liên hệ giáo viên để kiểm tra định dạng.')} />
    </div>
    <div className="video-controls"><button type="button" className="icon-button" aria-label={playing ? 'Tạm dừng video' : 'Phát video'} disabled={!!question} onClick={togglePlay}>{playing ? <Pause size={19} /> : <Play size={19} />}</button><button type="button" className="icon-button" aria-label="Tua lùi 5 giây" disabled={busy} onClick={() => { if (question) { setQuestion(null); gate.current = false } seek(clock.current.position - 5) }}><RotateCcw size={18} /></button><span className="video-time">{formatVideoTime(position)} / {formatVideoTime(info.duration)}</span><input type="range" aria-label="Tiến trình video" min={0} max={info.duration} step={0.1} value={position} onChange={(event) => { const target = Number(event.target.value); seek(target); if (target > seekLimit()) event.target.value = clock.current.position }} /><Volume2 size={17} aria-hidden="true" /><input className="video-volume" aria-label="Âm lượng video" type="range" min={0} max={1} step={0.05} value={volume} onChange={(event) => { const value = Number(event.target.value); setVolume(value); if (video.current) video.current.volume = value }} /><button type="button" className="icon-button" aria-label="Toàn màn hình video" onClick={async () => { try { if (document.fullscreenElement) await document.exitFullscreen(); else await wrapper.current.requestFullscreen() } catch { setError('Trình duyệt chưa cho phép mở toàn màn hình.') } }}><Maximize size={18} /></button></div>
    {completed && !canManage && <div className="video-completed"><CheckCircle2 size={18} />Đã xem</div>}
    {notice && !question && <p className="video-notice" data-variant={noticeVariant} role="status">{notice}</p>}
    {error && !question && <p className="error-banner" role="alert">{error}</p>}
    {question && <VideoCheckpointDialog question={question} choices={choices} setChoices={setChoices} text={text} setText={setText} busy={busy} notice={notice} noticeVariant={noticeVariant} error={error} onSubmit={submit} onReview={reviewKnowledge} />}
  </div>
    {!canManage && <VideoAnswersReview path={path} videoId={info.id} questions={info.questions} refreshToken={answerRevision} />}
  </>
}
