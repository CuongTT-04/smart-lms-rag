import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ClassroomResults from './ClassroomResults'
import { exportClassroomResults, getClassroomResults } from '../services/course.service'

vi.mock('../services/course.service', async (original) => ({
  ...await original(),
  getClassroomResults: vi.fn(),
  exportClassroomResults: vi.fn(),
}))

const sampleTeacherPayload = {
  count: 2,
  next: null,
  previous: null,
  classroom_id: 'r1',
  classroom_name: 'Lớp Sáng',
  viewer_role: 'TEACHER',
  score_policy: { practice: 'HIGHEST_SUBMITTED', test: 'SINGLE_ATTEMPT', average_scope: 'VISIBLE_GRADED_ONLY' },
  filters: { q: '', submission_status: '', grading_status: '' },
  assessments: [
    { id: 'a1', title: 'Ôn tập 1', mode: 'PRACTICE', kind: 'QUIZ', due_at: '2026-11-30T10:00:00Z', is_overdue: false, is_removed: false },
    { id: 'a2', title: 'Kiểm tra 1', mode: 'TEST', kind: 'TEXT', due_at: '2026-11-10T10:00:00Z', is_overdue: true, is_removed: false },
    { id: 'a3', title: 'Bài cũ', mode: 'PRACTICE', kind: 'QUIZ', due_at: '2026-11-20T10:00:00Z', is_overdue: false, is_removed: true },
  ],
  summary: {
    student_count: 2,
    active_assessment_count: 2,
    removed_assessment_count: 1,
    submitted_cells: 3,
    draft_cells: 0,
    not_submitted_cells: 1,
    pending_grading_cells: 2,
    pending_attempts: 2,
    average_score: 4.0,
  },
  results: [
    {
      student_id: 's1',
      name: 'Nguyễn Văn An',
      username: 'an',
      enrollment_status: 'ACTIVE',
      progress: { total_activities: 4, completed_activities: 2, percent: 50.0, has_activities: true, completed_at: null },
      submitted_count: 2,
      draft_count: 0,
      not_submitted_count: 0,
      pending_grading_count: 2,
      pending_attempts_count: 2,
      graded_count: 1,
      overdue_count: 0,
      average_score: 8.0,
      assessments: [
        { assessment_id: 'a1', title: 'Ôn tập 1', mode: 'PRACTICE', kind: 'QUIZ', is_removed: false, is_overdue: false, submission_status: 'SUBMITTED', grading_status: 'GRADED', has_pending_grading: true, score: 8.0, score_policy: 'HIGHEST_SUBMITTED', attempt_count: 2, submitted_attempts_count: 2, pending_attempts_count: 1, submitted_at: '2026-11-18T10:00:00Z' },
        { assessment_id: 'a2', title: 'Kiểm tra 1', mode: 'TEST', kind: 'TEXT', is_removed: false, is_overdue: true, submission_status: 'SUBMITTED', grading_status: 'PENDING', has_pending_grading: true, score: null, score_policy: 'SINGLE_ATTEMPT', attempt_count: 1, submitted_attempts_count: 1, pending_attempts_count: 1, submitted_at: '2026-11-18T11:00:00Z' },
        { assessment_id: 'a3', title: 'Bài cũ', mode: 'PRACTICE', kind: 'QUIZ', is_removed: true, is_overdue: false, submission_status: 'SUBMITTED', grading_status: 'GRADED', has_pending_grading: false, score: 6.0, score_policy: 'HIGHEST_SUBMITTED', attempt_count: 1, submitted_attempts_count: 1, pending_attempts_count: 0, submitted_at: '2026-11-17T10:00:00Z' },
      ],
    },
    {
      student_id: 's2',
      name: 'Trần Thị Bình',
      username: 'binh',
      enrollment_status: 'ACTIVE',
      progress: { total_activities: 4, completed_activities: 1, percent: 25.0, has_activities: true, completed_at: null },
      submitted_count: 1,
      draft_count: 0,
      not_submitted_count: 1,
      pending_grading_count: 0,
      pending_attempts_count: 0,
      graded_count: 1,
      overdue_count: 1,
      average_score: 0.0,
      assessments: [
        { assessment_id: 'a1', title: 'Ôn tập 1', mode: 'PRACTICE', kind: 'QUIZ', is_removed: false, is_overdue: false, submission_status: 'SUBMITTED', grading_status: 'GRADED', has_pending_grading: false, score: 0.0, score_policy: 'HIGHEST_SUBMITTED', attempt_count: 1, submitted_attempts_count: 1, pending_attempts_count: 0, submitted_at: '2026-11-18T09:00:00Z' },
        { assessment_id: 'a2', title: 'Kiểm tra 1', mode: 'TEST', kind: 'TEXT', is_removed: false, is_overdue: true, submission_status: 'NOT_SUBMITTED', grading_status: 'NOT_APPLICABLE', has_pending_grading: false, score: null, score_policy: 'SINGLE_ATTEMPT', attempt_count: 0, submitted_attempts_count: 0, pending_attempts_count: 0, submitted_at: null },
      ],
    },
  ],
}

describe('ClassroomResults', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('renders teacher results table with zero score, pending, overdue, removed badges and filters', async () => {
    getClassroomResults.mockResolvedValue(sampleTeacherPayload)
    exportClassroomResults.mockResolvedValue(undefined)

    render(<ClassroomResults courseId="c1" roomId="r1" canManage />)

    expect(await screen.findByText('Nguyễn Văn An')).toBeVisible()
    expect(screen.getByText('Trần Thị Bình')).toBeVisible()
    expect(screen.getByText('8/10')).toBeVisible()
    expect(screen.getByText('0/10')).toBeVisible()
    expect(screen.getByText('Đã gỡ')).toBeVisible()
    expect(screen.getAllByText('Quá hạn').length).toBeGreaterThan(0)
    expect(screen.getByText('+1 chờ chấm')).toBeVisible()

    await userEvent.selectOptions(screen.getByLabelText('Lọc trạng thái chấm điểm'), 'PENDING')
    await waitFor(() => expect(getClassroomResults).toHaveBeenLastCalledWith(
      'c1', 'r1', { grading_status: 'PENDING', page: 1 }, expect.any(AbortSignal)
    ))

    await userEvent.click(screen.getByRole('button', { name: 'Xuất Excel' }))
    expect(exportClassroomResults).toHaveBeenCalledWith('c1', 'r1', { grading_status: 'PENDING' })
  })

  it('renders student view without teacher search or export controls and handles empty state', async () => {
    getClassroomResults.mockResolvedValueOnce({
      ...sampleTeacherPayload,
      count: 0,
      viewer_role: 'STUDENT',
      assessments: [],
      summary: {
        student_count: 0,
        active_assessment_count: 0,
        removed_assessment_count: 0,
        submitted_cells: 0,
        draft_cells: 0,
        not_submitted_cells: 0,
        pending_grading_cells: 0,
        pending_attempts: 0,
        average_score: null,
      },
      results: [],
    })

    render(<ClassroomResults courseId="c1" roomId="r1" canManage={false} />)
    expect(await screen.findByText('Chưa có học viên hoặc bài đánh giá')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Xuất Excel' })).not.toBeInTheDocument()
    expect(screen.queryByPlaceholderText('Tìm theo tên hoặc tài khoản…')).not.toBeInTheDocument()
  })

  it('shows error banner when loading results fails', async () => {
    getClassroomResults.mockRejectedValueOnce({ status: 404 })
    render(<ClassroomResults courseId="c1" roomId="r1" canManage />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Không tìm thấy')
  })
})
