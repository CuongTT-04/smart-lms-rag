import { beforeEach, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import VideoAnswersReview from './VideoAnswersReview'
import { getMyVideoAnswers } from '../../services/video.service'
vi.mock('../../services/video.service', () => ({ getMyVideoAnswers: vi.fn() }))
const answer = { id: 'a1', question_id: 'q1', question_revision: 1, snapshot: { kind: 'TEXT', prompt: 'Giải thích khái niệm trong bài giảng với một ví dụ cụ thể', start_time: 5 }, text: 'Ví dụ của em dựa trên bài giảng', is_correct: null, created_at: '2026-10-17T06:00:00Z' }
beforeEach(() => vi.clearAllMocks())
it('restores previous answers as collapsed cards and expands the full question and submission', async () => {
  getMyVideoAnswers.mockResolvedValue([answer])
  render(<VideoAnswersReview path="/videos/" videoId="v1" />)
  const title = await screen.findByTitle(answer.snapshot.prompt)
  expect(screen.getByText(answer.text)).not.toBeVisible()
  await userEvent.click(title)
  expect(screen.getByRole('heading', { name: answer.snapshot.prompt })).toBeVisible()
  expect(screen.getByText(answer.text)).toBeVisible()
  expect(screen.getByText('Đã gửi tự luận')).toBeVisible()
  await userEvent.click(title)
  expect(screen.getByText(answer.text)).not.toBeVisible()
})
it('lets the student retry loading saved answers after a network failure', async () => {
  getMyVideoAnswers.mockRejectedValueOnce(new Error('Offline')).mockResolvedValueOnce([answer])
  render(<VideoAnswersReview path="/videos/" videoId="v1" />)
  await screen.findByRole('alert')
  await userEvent.click(screen.getByRole('button', { name: 'Làm mới câu hỏi đã trả lời' }))
  expect(await screen.findByTitle(answer.snapshot.prompt)).toBeVisible()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})
it.each([
  [[{ id: 'q1', revision: 2 }], 'Phiên bản cũ'],
  [[], 'Câu hỏi đã gỡ'],
])('labels historical answers when their question has changed or been removed', async (questions, label) => {
  getMyVideoAnswers.mockResolvedValue([answer])
  render(<VideoAnswersReview path="/videos/" videoId="v1" questions={questions} />)
  await userEvent.click(await screen.findByTitle(answer.snapshot.prompt))
  expect(await screen.findByText(label)).toBeVisible()
  expect(screen.getByText(answer.text)).toBeVisible()
})
