import { beforeEach, expect, it, vi } from 'vitest'
import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import AnnouncementComments from './AnnouncementComments'
import { listAnnouncementComments, createAnnouncementComment, deleteAnnouncementComment, voteAnnouncementComment, setClassroomCommentMute } from '../services/course.service'

vi.mock('../services/course.service', async (original) => ({ ...await original(),
  listAnnouncementComments: vi.fn(), createAnnouncementComment: vi.fn(), deleteAnnouncementComment: vi.fn(),
  voteAnnouncementComment: vi.fn(), setClassroomCommentMute: vi.fn(),
}))
const comment = { id: 'cm1', author_id: 'u1', author_name: 'Minh Anh', author_role: 'STUDENT', content: 'Em có câu hỏi', parent_id: null, created_at: '2026-10-17T08:00:00Z', can_delete: false, upvotes: 0, downvotes: 0, my_vote: 0 }
const payload = { results: [comment], can_comment: true, can_manage: false, muted_students: [] }
const open = () => render(<AnnouncementComments courseId="c1" roomId="r1" announcementId="a1" />)
beforeEach(() => { vi.clearAllMocks(); listAnnouncementComments.mockResolvedValue(payload) })

it('refreshes remote replies and votes automatically without discarding the draft', async () => {
  const view = open()
  try {
    await screen.findByText('Em có câu hỏi')
    await userEvent.type(screen.getByRole('textbox', { name: 'Nội dung bình luận' }), 'Đang soạn')
    listAnnouncementComments.mockResolvedValue({ ...payload, results: [{ ...comment, upvotes: 3 }, { ...comment, id: 'cm2', parent_id: 'cm1', content: 'Phản hồi từ người khác' }] })
    expect(await screen.findByText('Phản hồi từ người khác', {}, { timeout: 4000 })).toBeVisible()
    expect(within(screen.getAllByRole('button', { name: 'Upvote bình luận của Minh Anh' })[0]).getByText('3')).toBeVisible()
    expect(screen.getByRole('textbox', { name: 'Nội dung bình luận' })).toHaveValue('Đang soạn')
  } finally { view.unmount() }
})

it('does not overwrite a new vote with an older refresh response', async () => {
  open()
  await screen.findByText('Em có câu hỏi')
  let resolveRefresh
  listAnnouncementComments.mockImplementationOnce(() => new Promise((resolve) => { resolveRefresh = resolve }))
  await userEvent.click(screen.getByRole('button', { name: 'Làm mới bình luận' }))
  voteAnnouncementComment.mockResolvedValueOnce({ ...comment, my_vote: 1, upvotes: 1 })
  const upvote = screen.getByRole('button', { name: 'Upvote bình luận của Minh Anh' })
  await userEvent.click(upvote)
  await act(async () => { resolveRefresh(payload) })
  expect(upvote).toHaveAttribute('aria-pressed', 'true')
  expect(within(upvote).getByText('1')).toBeVisible()
})

it('retains a failed reply draft and submits it to the selected comment', async () => {
  createAnnouncementComment.mockRejectedValueOnce({ status: 400, data: { detail: 'Chưa gửi được' } }).mockResolvedValueOnce({ ...comment, id: 'cm2', content: 'Câu trả lời', parent_id: 'cm1' })
  open()
  await userEvent.click(await screen.findByRole('button', { name: 'Trả lời Minh Anh' }))
  await userEvent.type(screen.getByRole('textbox', { name: 'Nội dung bình luận' }), 'Câu trả lời')
  await userEvent.click(screen.getByRole('button', { name: 'Gửi bình luận' }))
  expect(await screen.findByText('Chưa gửi được')).toBeVisible()
  expect(screen.getByRole('textbox', { name: 'Nội dung bình luận' })).toHaveValue('Câu trả lời')
  await userEvent.click(screen.getByRole('button', { name: 'Gửi bình luận' }))
  expect(createAnnouncementComment).toHaveBeenLastCalledWith('c1', 'r1', 'a1', { content: 'Câu trả lời', parent_id: 'cm1' })
  expect(await screen.findByText('Câu trả lời')).toBeVisible()
})

it('toggles downvote and hides actions on another students comment', async () => {
  voteAnnouncementComment.mockResolvedValueOnce({ ...comment, my_vote: -1, downvotes: 1 }).mockResolvedValueOnce(comment)
  open()
  const down = await screen.findByRole('button', { name: 'Downvote bình luận của Minh Anh' })
  await userEvent.click(down)
  expect(down).toHaveAttribute('aria-pressed', 'true')
  expect(within(down).getByText('1')).toBeVisible()
  await userEvent.click(down)
  expect(voteAnnouncementComment).toHaveBeenLastCalledWith('c1', 'r1', 'a1', 'cm1', 0)
  expect(screen.queryByRole('button', { name: 'Tùy chọn bình luận của Minh Anh' })).not.toBeInTheDocument()
})

it('offers only deletion for own student comment and preserves replies after deletion', async () => {
  listAnnouncementComments.mockResolvedValue({ ...payload, results: [{ ...comment, can_delete: true }, { ...comment, id: 'cm2', parent_id: 'cm1', content: 'Phản hồi còn nguyên' }] })
  deleteAnnouncementComment.mockResolvedValue(null)
  open()
  await userEvent.click(await screen.findByRole('button', { name: 'Tùy chọn bình luận của Minh Anh' }))
  expect(within(screen.getByRole('menu')).getAllByRole('menuitem')).toHaveLength(1)
  await userEvent.click(screen.getByRole('menuitem', { name: 'Xóa bình luận' }))
  await userEvent.click(screen.getByRole('button', { name: 'Xác nhận xóa' }))
  expect(await screen.findByText('Bình luận đã bị xóa.')).toBeVisible()
  expect(screen.getByText('Phản hồi còn nguyên')).toBeVisible()
})

it('lets teachers mute and unmute a student', async () => {
  listAnnouncementComments.mockResolvedValue({ ...payload, can_manage: true, results: [{ ...comment, can_delete: true }] })
  setClassroomCommentMute.mockResolvedValue({ is_muted: true })
  open()
  await userEvent.click(await screen.findByRole('button', { name: 'Tùy chọn bình luận của Minh Anh' }))
  await userEvent.click(screen.getByRole('menuitem', { name: 'Mute học viên' }))
  expect(setClassroomCommentMute).toHaveBeenCalledWith('c1', 'r1', 'u1', true)
  await userEvent.click(await screen.findByRole('button', { name: 'Bỏ mute Minh Anh' }))
  expect(setClassroomCommentMute).toHaveBeenLastCalledWith('c1', 'r1', 'u1', false)
})

it('lets teachers unmute a student even when no comments remain', async () => {
  listAnnouncementComments.mockResolvedValue({ ...payload, can_manage: true, results: [], muted_students: [{ id: 'u1', name: 'Minh Anh' }] })
  setClassroomCommentMute.mockResolvedValue({ is_muted: false })
  open()
  await userEvent.click(await screen.findByText('Học viên đang mute (1)'))
  await userEvent.click(screen.getByRole('button', { name: 'Bỏ mute Minh Anh' }))
  expect(setClassroomCommentMute).toHaveBeenCalledWith('c1', 'r1', 'u1', false)
})

it('shows a read-only message when the student is muted', async () => {
  listAnnouncementComments.mockResolvedValue({ ...payload, can_comment: false })
  open()
  expect(await screen.findByText('Bạn đã bị tắt quyền bình luận trong lớp này.')).toBeVisible()
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Trả lời Minh Anh' })).toBeDisabled()
})
