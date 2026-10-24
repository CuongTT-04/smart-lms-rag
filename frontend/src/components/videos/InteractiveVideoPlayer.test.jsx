import { beforeEach, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import InteractiveVideoPlayer from './InteractiveVideoPlayer'
import { answerVideoQuestion, saveVideoProgress } from '../../services/video.service'

vi.mock('../../services/video.service', () => ({ saveVideoProgress: vi.fn(async (_, __, position) => ({ position, completed: false })), answerVideoQuestion: vi.fn(), getSessionVideo: vi.fn(), getMyVideoAnswers: vi.fn(async () => []) }))
const q = { id: 'q1', revision: 1, prompt: 'Chọn đáp án', kind: 'MCQ', multiple: true, start_time: 0, rewind_time: null, choices: [{ id: 'a', text: 'Lựa chọn A' }, { id: 'b', text: 'Lựa chọn B' }], hint: 'Gợi nhắc khái niệm' }
const info = { id: 'v1', duration: 60, questions: [], progress: { position: 0, passed_ids: [] } }
beforeEach(() => {
  vi.clearAllMocks()
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined)
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {})
  vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(() => {})
})
function open(values = info, canManage = false) {
  const view = render(<InteractiveVideoPlayer path="/videos/" info={values} src="blob:test" canManage={canManage} />)
  const media = view.container.querySelector('video')
  fireEvent.loadedMetadata(media)
  return media
}
it('blocks direct student forward seeking but allows the teacher to seek', () => {
  const media = open()
  media.currentTime = 30
  fireEvent.seeking(media)
  expect(media.currentTime).toBe(0)
})
it('allows teacher forward seeking', () => {
  const media = open(info, true)
  media.currentTime = 30
  fireEvent.seeking(media)
  expect(media.currentTime).toBe(30)
})
it('restores the saved position and permits student rewind', async () => {
  const media = open({ ...info, progress: { position: 20, passed_ids: [] } })
  expect(media.currentTime).toBe(20)
  await userEvent.click(screen.getByRole('button', { name: 'Tua lùi 5 giây' }))
  expect(media.currentTime).toBe(15)
  expect(saveVideoProgress).toHaveBeenCalledWith('/videos/', 'v1', 15)
})
it('submits multiple selections to the server and remains blocked after a wrong answer without rewind', async () => {
  answerVideoQuestion.mockResolvedValue({ id: 'a1', is_correct: false, rewind_to: null })
  open({ ...info, questions: [q] })
  await screen.findByText('Chọn đáp án')
  await userEvent.click(screen.getByLabelText('Lựa chọn A'))
  await userEvent.click(screen.getByLabelText('Lựa chọn B'))
  await userEvent.click(screen.getByRole('button', { name: 'Gửi câu trả lời' }))
  expect(answerVideoQuestion).toHaveBeenCalledWith('/videos/', 'v1', 'q1', expect.objectContaining({ selected_ids: ['a', 'b'], revision: 1 }))
  expect(await screen.findByText(/Câu trả lời chưa đúng/)).toHaveAttribute('data-variant', 'warning')
  expect(screen.getByRole('button', { name: 'Phát video' })).toBeDisabled()
})
it('unlocks after an essay submission', async () => {
  answerVideoQuestion.mockResolvedValue({ id: 'a1', is_correct: null, rewind_to: null })
  open({ ...info, questions: [{ ...q, kind: 'TEXT', choices: [], rewind_time: null }] })
  await userEvent.type(await screen.findByLabelText('Câu trả lời của bạn'), 'Em giải thích theo tài liệu')
  await userEvent.click(screen.getByRole('button', { name: 'Gửi câu trả lời' }))
  await waitFor(() => expect(screen.queryByLabelText('Câu trả lời của bạn')).not.toBeInTheDocument())
  expect(screen.getByRole('button', { name: 'Phát video' })).toBeEnabled()
  expect(await screen.findByText(/Đã gửi câu trả lời tự luận/)).toHaveAttribute('data-variant', 'success')
})
it('persists the current position when paused and explains blocked timeline jumps', async () => {
  const media = open({ ...info, progress: { position: 20, passed_ids: [] } })
  fireEvent.change(screen.getByRole('slider', { name: 'Tiến trình video' }), { target: { value: '40' } })
  expect(await screen.findByText('Chỉ được tua trong phần đã xem, không được tua tiến đến phần chưa xem.')).toBeVisible()
  expect(media.currentTime).toBe(20)
  fireEvent.pause(media)
  await waitFor(() => expect(saveVideoProgress).toHaveBeenCalledWith('/videos/', 'v1', 20))
})
it('forces a wrong MCQ answer back to the configured time and closes the checkpoint', async () => {
  answerVideoQuestion.mockResolvedValue({ id: 'a1', is_correct: false, rewind_to: 2 })
  const media = open({ ...info, progress: { position: 10, passed_ids: [] }, questions: [{ ...q, start_time: 10, rewind_time: 2 }] })
  await screen.findByText('Chọn đáp án')
  await userEvent.click(screen.getByLabelText('Lựa chọn A'))
  await userEvent.click(screen.getByRole('button', { name: 'Gửi câu trả lời' }))
  await waitFor(() => expect(media.currentTime).toBe(2))
  expect(screen.queryByRole('region', { name: 'Câu hỏi tại mốc video' })).not.toBeInTheDocument()
  expect(await screen.findByText(/Video quay lại 00:02/)).toBeVisible()
})
it('allows seeking forward inside previously watched content after rewinding', async () => {
  const media = open({ ...info, progress: { position: 5, watched_until: 5, seekable_until: 5, passed_ids: [] } })
  fireEvent.change(screen.getByRole('slider', { name: 'Tiến trình video' }), { target: { value: '1' } })
  fireEvent.change(screen.getByRole('slider', { name: 'Tiến trình video' }), { target: { value: '3' } })
  expect(media.currentTime).toBe(3)
  await waitFor(() => expect(saveVideoProgress).toHaveBeenCalledWith('/videos/', 'v1', 3))
})
it('restores watched status and permits unrestricted student seeking after completion', () => {
  const media = open({ ...info, progress: { position: 1, watched_until: 60, seekable_until: 60, completed: true, passed_ids: [] } })
  fireEvent.change(screen.getByRole('slider', { name: 'Tiến trình video' }), { target: { value: '50' } })
  expect(media.currentTime).toBe(50)
  expect(screen.getByText('Đã xem')).toBeVisible()
})
it('opens checkpoint questions in a dialog and does not unlock playback by closing it', async () => {
  open({ ...info, questions: [q] })
  await screen.findByRole('dialog', { name: 'Câu hỏi tại mốc video' })
  await userEvent.click(screen.getByRole('button', { name: 'Đóng hộp thoại' }))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Phát video' }))
  expect(await screen.findByRole('dialog', { name: 'Câu hỏi tại mốc video' })).toBeVisible()
})
it('dismisses playback notifications after five seconds', async () => {
  vi.useFakeTimers()
  try {
    open()
    fireEvent.change(screen.getByRole('slider', { name: 'Tiến trình video' }), { target: { value: '40' } })
    expect(screen.getByText(/không được tua tiến/)).toBeVisible()
    await act(async () => vi.advanceTimersByTimeAsync(5000))
    expect(screen.queryByText(/không được tua tiến/)).not.toBeInTheDocument()
  } finally { vi.useRealTimers() }
})
