import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {
  ClassroomProgressBadge,
  DocumentCompletionButton,
  SessionProgressBadge,
} from './LearningProgress'
import { useClassroomProgress } from '../../hooks/useClassroomProgress'
import { completeClassroomDocument, getClassroomProgress } from '../../services/course.service'

vi.mock('../../services/course.service', async (original) => ({
  ...await original(),
  getClassroomProgress: vi.fn(),
  completeClassroomDocument: vi.fn(),
}))

function ProgressHarness({ courseId, classroomId, versionId, documentLoaded = true }) {
  const { progress, loading, error, reload } = useClassroomProgress(courseId, classroomId, true)
  const completed = Boolean(
    progress?.sessions
      ?.flatMap((session) => session.activities)
      .find((activity) => activity.kind === 'PDF' && activity.version_id === versionId)?.completed
  )
  return <div>
    <ClassroomProgressBadge progress={progress} loading={loading} error={error} />
    <SessionProgressBadge progress={progress} sessionId="s1" />
    <DocumentCompletionButton
      courseId={courseId}
      classroomId={classroomId}
      versionId={versionId}
      documentLoaded={documentLoaded}
      completed={completed}
      onCompleted={() => reload()}
    />
  </div>
}

describe('LearningProgress', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('renders loading, empty, partial, complete and error badge states', () => {
    const { rerender } = render(<ClassroomProgressBadge loading />)
    expect(screen.getByRole('status')).toHaveTextContent('Đang tải tiến độ')

    rerender(<ClassroomProgressBadge error="Không thể tải" />)
    expect(screen.getByRole('status')).toHaveTextContent('Không thể tải')

    rerender(<ClassroomProgressBadge progress={{ has_activities: false, total_activities: 0, completed_activities: 0, percent: 0, completed_at: null }} />)
    expect(screen.getByText('Chưa có hoạt động')).toBeVisible()

    const partial = {
      has_activities: true,
      total_activities: 4,
      completed_activities: 2,
      percent: 50,
      completed_at: null,
      sessions: [{ session_id: 's1', total_activities: 2, completed_activities: 1 }],
    }
    rerender(<>
      <ClassroomProgressBadge progress={partial} />
      <SessionProgressBadge progress={partial} sessionId="s1" />
    </>)
    expect(screen.getByLabelText('Tiến độ lớp học: 2/4 hoạt động (50%)')).toHaveTextContent('2/4 hoạt động · 50%')
    expect(screen.getByText('1/2 hoàn thành')).toBeVisible()
  })

  it('disables completion until document loads, prevents double submit, and reloads after success', async () => {
    const initialPayload = {
      classroom_id: 'r1',
      has_activities: true,
      total_activities: 2,
      completed_activities: 0,
      percent: 0,
      completed_at: null,
      sessions: [{
        session_id: 's1',
        total_activities: 2,
        completed_activities: 0,
        activities: [{ kind: 'PDF', id: 'd1', version_id: 'v1', title: 'Doc', completed: false }],
      }],
    }
    const updatedPayload = {
      ...initialPayload,
      completed_activities: 1,
      percent: 50,
      sessions: [{
        session_id: 's1',
        total_activities: 2,
        completed_activities: 1,
        activities: [{ kind: 'PDF', id: 'd1', version_id: 'v1', title: 'Doc', completed: true }],
      }],
    }

    getClassroomProgress.mockResolvedValueOnce(initialPayload).mockResolvedValueOnce(updatedPayload)
    let resolveComplete
    completeClassroomDocument.mockImplementationOnce(() => new Promise((resolve) => { resolveComplete = resolve }))

    const { rerender } = render(<ProgressHarness courseId="c1" classroomId="r1" versionId="v1" documentLoaded={false} />)
    await waitFor(() => expect(screen.getByText('0/2 hoạt động · 0%')).toBeVisible())
    expect(screen.getByRole('button', { name: 'Đánh dấu đã học tài liệu này' })).toBeDisabled()

    rerender(<ProgressHarness courseId="c1" classroomId="r1" versionId="v1" documentLoaded />)
    const button = screen.getByRole('button', { name: 'Đánh dấu đã học tài liệu này' })
    expect(button).toBeEnabled()

    await userEvent.dblClick(button)
    expect(completeClassroomDocument).toHaveBeenCalledTimes(1)
    expect(completeClassroomDocument).toHaveBeenCalledWith('c1', 'r1', 'v1', expect.any(AbortSignal))
    expect(screen.getByRole('button', { name: 'Đánh dấu đã học tài liệu này' })).toBeDisabled()

    await act(async () => { resolveComplete(updatedPayload) })
    expect(await screen.findByText('Đã học')).toBeVisible()
    expect(screen.getByText('1/2 hoạt động · 50%')).toBeVisible()
  })

  it('keeps uncompleted state on failure and resets when version changes', async () => {
    completeClassroomDocument.mockRejectedValueOnce({ status: 0 })
    const { rerender } = render(
      <DocumentCompletionButton courseId="c1" classroomId="r1" versionId="v1" documentLoaded completed={false} />
    )
    await userEvent.click(screen.getByRole('button', { name: 'Đánh dấu đã học tài liệu này' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Không thể kết nối')
    expect(screen.queryByText('Đã học')).not.toBeInTheDocument()

    rerender(<DocumentCompletionButton courseId="c1" classroomId="r1" versionId="v2" documentLoaded completed={false} />)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Đánh dấu đã học tài liệu này' })).toBeEnabled()
  })

  it('ignores stale classroom progress responses when switching classrooms', async () => {
    let resolveRoom1
    getClassroomProgress
      .mockImplementationOnce(() => new Promise((resolve) => { resolveRoom1 = resolve }))
      .mockResolvedValueOnce({
        classroom_id: 'r2',
        has_activities: true,
        total_activities: 3,
        completed_activities: 3,
        percent: 100,
        completed_at: '2026-11-18T10:00:00Z',
        sessions: [],
      })

    const { rerender } = render(<ProgressHarness courseId="c1" classroomId="r1" versionId="v1" />)
    await waitFor(() => expect(getClassroomProgress).toHaveBeenCalledWith('c1', 'r1', expect.any(AbortSignal)))

    rerender(<ProgressHarness courseId="c1" classroomId="r2" versionId="v1" />)
    expect(await screen.findByText('3/3 hoạt động · 100%')).toBeVisible()

    await act(async () => {
      resolveRoom1({
        classroom_id: 'r1',
        has_activities: true,
        total_activities: 5,
        completed_activities: 1,
        percent: 20,
        completed_at: null,
        sessions: [],
      })
    })
    expect(screen.getByText('3/3 hoạt động · 100%')).toBeVisible()
    expect(screen.queryByText('1/5 hoạt động · 20%')).not.toBeInTheDocument()
  })
})
