import { beforeEach, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import CourseDocuments from './CourseDocuments'
import { listDocuments } from '../../services/document.service'
import { completeClassroomDocument, getClassroomProgress } from '../../services/course.service'

vi.mock('../../services/document.service', () => ({ listDocuments: vi.fn() }))
vi.mock('../../services/course.service', () => ({
  completeClassroomDocument: vi.fn(), getClassroomProgress: vi.fn(), courseErrorMessage: () => 'Lỗi kết nối',
}))
vi.mock('./MaterialActions', () => ({ default: () => null }))
vi.mock('./PdfViewer', () => ({ default: ({ onReady }) => <button onClick={() => onReady(true)}>PDF đã tải</button> }))

const row = { document_id: 'd1', version_id: 'v1', published_version_id: 'v1', title: 'CPU', extraction_status: 'READY', watermark_status: 'READY' }
const progress = (completed) => ({ sessions: [{ session_id: 's1', activities: [{ kind: 'PDF', version_id: 'v1', completed }] }] })

beforeEach(() => {
  vi.clearAllMocks()
  listDocuments.mockResolvedValue([row])
  getClassroomProgress.mockResolvedValue(progress(false))
  completeClassroomDocument.mockResolvedValue(progress(true))
})

it('records completion only after opening the PDF and requires completion of a newly published version', async () => {
  const view = render(<CourseDocuments courseId="c1" classroomId="r1" sessionId="s1" workspace />)
  const button = await screen.findByRole('button', { name: 'Đánh dấu đã học tài liệu này' })
  expect(button).toBeDisabled()
  await userEvent.click(screen.getByRole('button', { name: 'PDF đã tải' }))
  await userEvent.click(button)
  expect(completeClassroomDocument).toHaveBeenCalledWith('c1', 'r1', 'v1', expect.any(AbortSignal))
  expect(await screen.findByLabelText('Đã học phiên bản tài liệu hiện tại')).toBeVisible()

  listDocuments.mockResolvedValue([{ ...row, version_id: 'v2', published_version_id: 'v2' }])
  view.rerender(<CourseDocuments courseId="c1" classroomId="r1" sessionId="s1" workspace refreshToken={1} />)
  await waitFor(() => expect(screen.queryByLabelText('Đã học phiên bản tài liệu hiện tại')).not.toBeInTheDocument())
  expect(screen.getByRole('button', { name: 'Đánh dấu đã học tài liệu này' })).toBeDisabled()
})

it('keeps the completion response when an older progress request is still in flight', async () => {
  let resolveOld
  getClassroomProgress.mockImplementation(() => new Promise((resolve) => { resolveOld = resolve }))
  render(<CourseDocuments courseId="c1" classroomId="r1" sessionId="s1" workspace />)
  await screen.findByRole('button', { name: 'PDF đã tải' })
  await waitFor(() => expect(getClassroomProgress).toHaveBeenCalled())
  await userEvent.click(screen.getByRole('button', { name: 'PDF đã tải' }))
  await userEvent.click(screen.getByRole('button', { name: 'Đánh dấu đã học tài liệu này' }))
  await screen.findByLabelText('Đã học phiên bản tài liệu hiện tại')
  resolveOld(progress(false))
  await waitFor(() => expect(screen.getByLabelText('Đã học phiên bản tài liệu hiện tại')).toBeVisible())
})
