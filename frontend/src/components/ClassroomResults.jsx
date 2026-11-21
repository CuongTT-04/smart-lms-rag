import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, ArrowRight, BarChart3, Download, LoaderCircle, RefreshCw, Search } from 'lucide-react'
import { courseErrorMessage, exportClassroomResults, getClassroomResults } from '../services/course.service'

const SUBMISSION_OPTIONS = [
  ['', 'Tất cả trạng thái nộp'],
  ['SUBMITTED', 'Đã nộp'],
  ['DRAFT', 'Đang làm nháp'],
  ['NOT_SUBMITTED', 'Chưa nộp'],
]

const GRADING_OPTIONS = [
  ['', 'Tất cả trạng thái chấm'],
  ['GRADED', 'Đã chấm'],
  ['PENDING', 'Chờ chấm'],
  ['NOT_APPLICABLE', 'Chưa áp dụng'],
]

function formatScore(value) {
  if (value === null || value === undefined) return '—'
  const rounded = Math.round(Number(value) * 100) / 100
  return `${rounded}`
}

function cellStatusText(cell) {
  if (cell.score !== null && cell.score !== undefined) {
    return `${formatScore(cell.score)}/10`
  }
  if (cell.submission_status === 'DRAFT') return 'Đang làm'
  if (cell.submission_status === 'NOT_SUBMITTED') return 'Chưa nộp'
  if (cell.grading_status === 'PENDING') return 'Chờ chấm'
  return 'Đã nộp'
}

export default function ClassroomResults({ courseId, roomId, canManage = true }) {
  const [q, setQ] = useState('')
  const [submissionStatus, setSubmissionStatus] = useState('')
  const [gradingStatus, setGradingStatus] = useState('')
  const [page, setPage] = useState(1)
  const [revision, setRevision] = useState(0)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [exporting, setExporting] = useState(false)
  const epochRef = useRef(0)

  const filterKey = JSON.stringify({ courseId, roomId, q, submissionStatus, gradingStatus, page })

  useEffect(() => {
    const controller = new AbortController()
    const epoch = ++epochRef.current
    const timer = setTimeout(() => {
      setLoading(true)
      const params = {
        ...(q.trim() ? { q: q.trim() } : {}),
        ...(submissionStatus ? { submission_status: submissionStatus } : {}),
        ...(gradingStatus ? { grading_status: gradingStatus } : {}),
        page,
      }
      getClassroomResults(courseId, roomId, params, controller.signal)
        .then((result) => {
          if (controller.signal.aborted || epochRef.current !== epoch) return
          setData({ ...result, _filterKey: filterKey })
          setError('')
        })
        .catch((err) => {
          if (controller.signal.aborted || epochRef.current !== epoch) return
          setError(courseErrorMessage(err))
        })
        .finally(() => {
          if (!controller.signal.aborted && epochRef.current === epoch) setLoading(false)
        })
    }, 150)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [courseId, roomId, q, submissionStatus, gradingStatus, page, revision, filterKey])

  const current = data?._filterKey === filterKey ? data : null

  async function handleExport() {
    if (exporting || !canManage) return
    setExporting(true)
    setError('')
    try {
      await exportClassroomResults(courseId, roomId, {
        ...(q.trim() ? { q: q.trim() } : {}),
        ...(submissionStatus ? { submission_status: submissionStatus } : {}),
        ...(gradingStatus ? { grading_status: gradingStatus } : {}),
      })
    } catch (err) {
      setError(courseErrorMessage(err))
    } finally {
      setExporting(false)
    }
  }

  const assessments = current?.assessments || []
  const rows = current?.results || []
  const summary = current?.summary
  const hasFilters = Boolean(q.trim() || submissionStatus || gradingStatus)

  return <section className="classroom-results-panel" aria-labelledby="class-results-title">
    <div className="classroom-results-header">
      <div>
        <h2 id="class-results-title"><BarChart3 size={20} aria-hidden="true" />Kết quả học tập</h2>
        <p className="assessment-muted">
          Điểm bài ôn tập lấy lượt đã nộp{canManage ? '' : '/công bố'} cao nhất; bài kiểm tra lấy lượt hợp lệ duy nhất (khác với dashboard từng bài vốn hiển thị lượt nộp mới nhất).
        </p>
      </div>
      <div className="classroom-results-actions">
        {canManage && <button type="button" className="outline-button" disabled={!current || exporting} onClick={handleExport}>
          <Download size={16} aria-hidden="true" />{exporting ? 'Đang xuất…' : 'Xuất Excel'}
        </button>}
        <button type="button" className="icon-button" aria-label="Làm mới bảng kết quả" title="Làm mới bảng kết quả" disabled={loading} onClick={() => setRevision((v) => v + 1)}>
          {loading ? <LoaderCircle size={18} className="spin" /> : <RefreshCw size={18} />}
        </button>
      </div>
    </div>

    <div className="classroom-results-filters">
      {canManage && <label className="classroom-results-search">
        <Search size={17} aria-hidden="true" />
        <span className="sr-only">Tìm học viên</span>
        <input
          type="search"
          placeholder="Tìm theo tên hoặc tài khoản…"
          value={q}
          onChange={(e) => { setQ(e.target.value); setPage(1) }}
        />
      </label>}
      <select aria-label="Lọc trạng thái nộp bài" value={submissionStatus} onChange={(e) => { setSubmissionStatus(e.target.value); setPage(1) }}>
        {SUBMISSION_OPTIONS.map(([val, label]) => <option key={val} value={val}>{label}</option>)}
      </select>
      <select aria-label="Lọc trạng thái chấm điểm" value={gradingStatus} onChange={(e) => { setGradingStatus(e.target.value); setPage(1) }}>
        {GRADING_OPTIONS.map(([val, label]) => <option key={val} value={val}>{label}</option>)}
      </select>
    </div>

    {error && <div className="error-banner" role="alert">{error}</div>}

    {!current && loading && <p className="class-loading" role="status"><LoaderCircle className="spin" size={18} />Đang tải kết quả lớp học…</p>}

    {current && <>
      <div className="classroom-results-metrics">
        {canManage && <article><span>Học viên</span><strong>{summary.student_count}</strong></article>}
        <article><span>Bài áp dụng</span><strong>{summary.active_assessment_count}</strong></article>
        <article><span>Lượt đã nộp</span><strong>{summary.submitted_cells}</strong></article>
        <article><span>Lượt chưa nộp</span><strong>{summary.not_submitted_cells}</strong></article>
        <article><span>Bài chờ chấm</span><strong>{summary.pending_grading_cells}{summary.pending_attempts > summary.pending_grading_cells ? ` (${summary.pending_attempts} lượt)` : ''}</strong></article>
        <article><span>Điểm trung bình</span><strong>{formatScore(summary.average_score)}</strong></article>
      </div>

      {rows.length === 0 ? (
        <div className="class-session-empty">
          <BarChart3 size={30} aria-hidden="true" />
          <h3>{hasFilters ? 'Không có kết quả phù hợp bộ lọc' : 'Chưa có học viên hoặc bài đánh giá'}</h3>
          <p>{hasFilters ? 'Thử xóa bộ lọc tìm kiếm hoặc trạng thái để xem lại toàn bộ dữ liệu.' : 'Khi lớp có học viên tham gia hoặc bài đánh giá được công bố, kết quả sẽ hiển thị tại đây.'}</p>
        </div>
      ) : (
        <div className="assessment-table-wrap">
          <table className="assessment-table classroom-results-table">
            <caption>Bảng kết quả học tập</caption>
            <thead>
              <tr>
                <th>Học viên</th>
                <th>Tiến độ</th>
                <th>Đã nộp / Chưa nộp</th>
                <th>Bài chờ chấm</th>
                <th>Điểm TB</th>
                {assessments.map((item) => <th key={item.id}>
                  <span>{item.title}</span>
                  <small className="result-col-tags">
                    {item.mode === 'TEST' ? 'Kiểm tra' : 'Ôn tập'}
                    {item.is_removed && <em className="result-badge is-removed">Đã gỡ</em>}
                    {!item.is_removed && item.is_overdue && <em className="result-badge is-overdue">Quá hạn</em>}
                  </small>
                </th>)}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const cells = new Map(row.assessments.map((cell) => [cell.assessment_id, cell]))
                return <tr key={row.student_id}>
                  <td><strong>{row.name}</strong><small className="result-username">{row.username}</small></td>
                  <td>
                    {row.progress.has_activities
                      ? `${row.progress.completed_activities}/${row.progress.total_activities} (${Math.round(row.progress.percent * 100) / 100}%)`
                      : 'Chưa có hoạt động'}
                  </td>
                  <td>{row.submitted_count} / {row.not_submitted_count}{row.draft_count > 0 ? ` (${row.draft_count} nháp)` : ''}</td>
                  <td>{row.pending_grading_count}{row.pending_attempts_count > row.pending_grading_count ? ` (${row.pending_attempts_count} lượt)` : ''}</td>
                  <td><strong>{formatScore(row.average_score)}</strong></td>
                  {assessments.map((item) => {
                    const cell = cells.get(item.id)
                    if (!cell) return <td key={item.id}>—</td>
                    return <td key={item.id}>
                      <span className={`result-cell-status is-${cell.grading_status.toLowerCase()}`}>
                        {cellStatusText(cell)}
                      </span>
                      {cell.is_overdue && <small className="result-badge is-overdue">Quá hạn</small>}
                      {cell.pending_attempts_count > 0 && cell.grading_status === 'GRADED' && (
                        <small className="result-pending-extra">+{cell.pending_attempts_count} chờ chấm</small>
                      )}
                    </td>
                  })}
                </tr>
              })}
            </tbody>
          </table>
        </div>
      )}

      {(current.previous || current.next) && <div className="classroom-results-pagination">
        <button type="button" className="outline-button" disabled={!current.previous || loading} onClick={() => setPage((p) => Math.max(1, p - 1))}>
          <ArrowLeft size={16} />Trang trước
        </button>
        <span>Trang {page} · Tổng {current.count} học viên</span>
        <button type="button" className="outline-button" disabled={!current.next || loading} onClick={() => setPage((p) => p + 1)}>
          Trang sau<ArrowRight size={16} />
        </button>
      </div>}
    </>}
  </section>
}
