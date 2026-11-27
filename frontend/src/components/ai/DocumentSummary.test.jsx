import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import DocumentSummary from './DocumentSummary'
import { advanceSummaryTask, getSummaryTask, sendChat } from '../../services/ai.service'

vi.mock('../../services/ai.service', () => ({ sendChat: vi.fn(), advanceSummaryTask: vi.fn(), getSummaryTask: vi.fn(), sendChatFeedback: vi.fn(), chatErrorMessage: () => 'Không đọc đủ nguồn.' }))
const scope = { course_id: 'course', session_id: 'session' }
const result = { status: 'ANSWERED', mode: 'summary', answer: 'Bản tổng hợp nội dung học liệu.',
  citations: [{ label: 1, document_id: 'doc', version_id: 'version', page_number: 2, document_title: 'Triết học' }],
  coverage: { method: 'coherent_summary_v1', page_start: 2, page_end: 3, document_pages: 12, chunks_scanned: 4, whole_document: false } }
const pending = { id: 'job', status: 'PENDING', progress: { phase: 'map', blocks_read: 0, blocks_total: 4, steps: 0 } }
beforeEach(() => {
  sendChat.mockReset(); advanceSummaryTask.mockReset(); getSummaryTask.mockReset()
  vi.stubGlobal('crypto', { randomUUID: () => 'summary-request' })
  sendChat.mockResolvedValue(pending)
  advanceSummaryTask.mockResolvedValue({ id: 'job', status: 'COMPLETED', result })
  getSummaryTask.mockResolvedValue(pending)
})

it('submits an explicit document and page range without conversation history', async () => {
  render(<DocumentSummary scope={scope} documentId="doc" onClose={vi.fn()} />)
  await userEvent.clear(screen.getByLabelText('Từ trang PDF'))
  await userEvent.type(screen.getByLabelText('Từ trang PDF'), '2')
  await userEvent.type(screen.getByLabelText('Đến trang PDF'), '3')
  await userEvent.click(screen.getByRole('button', { name: 'Tóm tắt', exact: true }))
  expect(await screen.findByText(/4 đoạn đã đọc/)).toHaveTextContent('Phạm vi đã chọn')
  expect(sendChat.mock.calls[0][0]).toEqual({ ...scope, document_ids: ['doc'], mode: 'summary',
    question: 'Tóm tắt nội dung học liệu theo phạm vi trang.', page_start: 2, page_end: 3, summary_request_id: 'summary-request' })
  expect(advanceSummaryTask).toHaveBeenCalledWith('job', expect.anything())
  expect(screen.getByRole('button', { name: 'Nguồn trong phạm vi tóm tắt (1)' })).toBeVisible()
})

it('omits the end page for full document selection and displays actual returned coverage', async () => {
  advanceSummaryTask.mockResolvedValue({ id: 'job', status: 'COMPLETED', result: { ...result, coverage: { ...result.coverage, page_start: 1, page_end: 12, whole_document: true } } })
  render(<DocumentSummary scope={scope} documentId="doc" onClose={vi.fn()} />)
  await userEvent.click(screen.getByRole('button', { name: 'Tóm tắt', exact: true }))
  expect(await screen.findByText(/Toàn tài liệu/)).toBeVisible()
  expect(sendChat.mock.calls[0][0]).not.toHaveProperty('page_end')
})

it('does not expose a stale result after unmount or show failed output as a summary', async () => {
  let finish
  sendChat.mockImplementation(() => new Promise(resolve => { finish = resolve }))
  const { unmount } = render(<DocumentSummary scope={scope} documentId="doc" onClose={vi.fn()} />)
  await userEvent.click(screen.getByRole('button', { name: 'Tóm tắt', exact: true }))
  await waitFor(() => expect(sendChat).toHaveBeenCalledOnce())
  const signal = sendChat.mock.calls[0][1].signal
  unmount()
  expect(signal.aborted).toBe(true)
  await act(async () => finish(pending))
  expect(screen.queryByText(/Bản tổng hợp nội dung/)).not.toBeInTheDocument()
})

it('shows an error and allows retry without inventing coverage', async () => {
  sendChat.mockRejectedValueOnce(new Error('incomplete'))
  render(<DocumentSummary scope={scope} documentId="doc" onClose={vi.fn()} />)
  await userEvent.click(screen.getByRole('button', { name: 'Tóm tắt', exact: true }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Không đọc đủ nguồn.')
  expect(screen.queryByText(/đoạn đã đọc/)).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Tóm tắt', exact: true })).toBeEnabled()
})

it('does not show partial summaries and completes multiple phases before showing the result', async () => {
  advanceSummaryTask.mockResolvedValueOnce({ ...pending, progress: { phase: 'reduce', blocks_read: 4, blocks_total: 4, steps: 1 } })
    .mockResolvedValueOnce({ id: 'job', status: 'COMPLETED', result })
  render(<DocumentSummary scope={scope} documentId="doc" onClose={vi.fn()} />)
  await userEvent.click(screen.getByRole('button', { name: 'Tóm tắt', exact: true }))
  expect(await screen.findByText(/4 đoạn đã đọc/)).toBeVisible()
  expect(advanceSummaryTask).toHaveBeenCalledTimes(2)
})

it('resumes the same job after a network error without creating another task', async () => {
  advanceSummaryTask.mockRejectedValueOnce({ status: 504 })
  render(<DocumentSummary scope={scope} documentId="doc" onClose={vi.fn()} />)
  await userEvent.click(screen.getByRole('button', { name: 'Tóm tắt', exact: true }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Tiến độ đã được lưu')
  await userEvent.click(screen.getByRole('button', { name: 'Tóm tắt', exact: true }))
  await screen.findByText(/4 đoạn đã đọc/)
  expect(sendChat).toHaveBeenCalledTimes(1)
  expect(getSummaryTask).toHaveBeenCalledWith('job', expect.anything())
})

it('stops advancing on quota denial and resumes the saved job only after explicit retry', async () => {
  advanceSummaryTask.mockRejectedValueOnce({ status: 429, data: { code: 'AI_QUOTA_EXCEEDED' } })
  render(<DocumentSummary scope={scope} documentId="doc" onClose={vi.fn()} />)
  await userEvent.click(screen.getByRole('button', { name: 'Tóm tắt', exact: true }))
  await screen.findByRole('alert')
  expect(advanceSummaryTask).toHaveBeenCalledTimes(1)
  expect(screen.getByRole('button', { name: 'Tóm tắt', exact: true })).toBeEnabled()
  await userEvent.click(screen.getByRole('button', { name: 'Tóm tắt', exact: true }))
  await screen.findByText(/4 đoạn đã đọc/)
  expect(sendChat).toHaveBeenCalledTimes(1)
  expect(getSummaryTask).toHaveBeenCalledWith('job', expect.anything())
})

it('reads a completed job after disconnection without another model step', async () => {
  advanceSummaryTask.mockRejectedValueOnce({ status: 0 })
  getSummaryTask.mockResolvedValueOnce({ id: 'job', status: 'COMPLETED', result })
  render(<DocumentSummary scope={scope} documentId="doc" onClose={vi.fn()} />)
  await userEvent.click(screen.getByRole('button', { name: 'Tóm tắt', exact: true }))
  await screen.findByRole('alert')
  await userEvent.click(screen.getByRole('button', { name: 'Tóm tắt', exact: true }))
  await screen.findByText(/4 đoạn đã đọc/)
  expect(sendChat).toHaveBeenCalledTimes(1)
  expect(advanceSummaryTask).toHaveBeenCalledTimes(1)
})

it('does not describe a policy denial as a recoverable connection problem', async () => {
  advanceSummaryTask.mockRejectedValueOnce({ status: 403, data: { code: 'AI_NOT_ALLOWED' } })
  render(<DocumentSummary scope={scope} documentId="doc" onClose={vi.fn()} />)
  await userEvent.click(screen.getByRole('button', { name: 'Tóm tắt', exact: true }))
  expect(await screen.findByRole('alert')).not.toHaveTextContent('Tiến độ đã được lưu')
  expect(screen.queryByText(/4 đoạn đã đọc/)).not.toBeInTheDocument()
})

it('does not present an old extractive response as a coherent summary', async () => {
  advanceSummaryTask.mockResolvedValue({ id: 'job', status: 'COMPLETED', result: { ...result, coverage: { ...result.coverage, method: 'extractive_page_balanced_v1' } } })
  render(<DocumentSummary scope={scope} documentId="doc" onClose={vi.fn()} />)
  await userEvent.click(screen.getByRole('button', { name: 'Tóm tắt', exact: true }))
  await screen.findByRole('alert')
  expect(screen.queryByText(/4 đoạn đã đọc/)).not.toBeInTheDocument()
})
