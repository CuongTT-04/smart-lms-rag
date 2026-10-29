import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import SessionAssistant from './SessionAssistant'
import { listConversations, createConversation, getConversation, sendChat, sendChatFeedback } from '../../services/ai.service'

vi.mock('../../services/ai.service', () => ({ listConversations: vi.fn(), createConversation: vi.fn(),
  getConversation: vi.fn(), sendChat: vi.fn(), sendChatFeedback: vi.fn(), chatErrorMessage: () => 'Không thể tải hội thoại.' }))
const scope = { course_id: 'course', classroom_id: 'room', session_id: 'lesson' }
const result = { request_id: 'answer', conversation_id: 'conv', turn_id: 'turn', status: 'ANSWERED', answer: 'Đáp án đã lưu [1]',
  citations: [{ label: 1, document_id: 'doc', version_id: 'v', page_number: 1, document_title: 'PDF', excerpt: 'Nguồn' }], rating: 'LIKE', timing: {total_ms: 65000} }
const detail = { id: 'conv', title: 'Câu hỏi cũ', turns: [{ id: 'turn', position: 1, question: 'Câu hỏi cũ', created_at: '2026-10-27T18:45:00Z', status: 'COMPLETED', result }], next_before: null }
beforeEach(() => {
  vi.stubGlobal('matchMedia', () => ({ matches: true }))
  vi.stubGlobal('crypto', { randomUUID: vi.fn(() => 'message-uuid') })
  listConversations.mockReset(); listConversations.mockResolvedValue({ results: [], next_cursor: null })
  getConversation.mockReset(); getConversation.mockResolvedValue(detail)
  createConversation.mockReset(); createConversation.mockResolvedValue({ id: 'new-conv' })
  sendChat.mockReset(); sendChat.mockResolvedValue({ ...result, conversation_id: 'new-conv', turn_id: 'new-turn', request_id: 'new-answer' })
  sendChatFeedback.mockReset(); sendChatFeedback.mockImplementation(async (_id, rating) => ({ rating }))
})

it('restores the latest server conversation and its saved feedback', async () => {
  listConversations.mockResolvedValue({ results: [{ id: 'conv', title: 'Câu hỏi cũ' }], next_cursor: null })
  render(<SessionAssistant scope={scope} documentId="doc" />)
  expect(await screen.findByText('Câu hỏi cũ')).toBeVisible()
  expect(await screen.findByRole('button', { name: 'Thích câu trả lời' })).toHaveAttribute('aria-pressed', 'true')
  expect(document.querySelector('.ai-user-turn time')).toHaveAttribute('datetime', '2026-10-27T18:45:00Z')
  expect(document.querySelector('.ai-user-turn time').textContent).toMatch(/^\d{2}:\d{2}$/)
  expect(screen.getByText('Phản hồi trong 1 phút 05 giây')).toBeVisible()
  expect(getConversation).toHaveBeenCalledWith('conv', expect.anything())
  expect(listConversations.mock.calls[0][0]).toEqual({ ...scope, document_id: 'doc' })
})

it('creates a session lazily and sends stable IDs with document-only scope', async () => {
  render(<SessionAssistant scope={scope} documentId="doc" />)
  await waitFor(() => expect(screen.getByRole('textbox', { name: 'Câu hỏi cho ayo' })).toBeEnabled())
  expect(createConversation).not.toHaveBeenCalled()
  await userEvent.type(screen.getByRole('textbox', { name: 'Câu hỏi cho ayo' }), 'Câu hỏi mới{Enter}')
  expect(await screen.findByRole('button', { name: 'Trích dẫn [1]' })).toBeVisible()
  expect(createConversation.mock.calls[0][0]).toEqual({ ...scope, document_id: 'doc' })
  expect(sendChat.mock.calls[0][0]).toEqual({ ...scope, document_ids: ['doc'], conversation_id: 'new-conv',
    client_message_id: 'message-uuid', question: 'Câu hỏi mới', mode: 'qa' })
})

it('new chat clears the view without deleting the previous session and history can reopen it', async () => {
  listConversations.mockResolvedValue({ results: [{ id: 'conv', title: 'Câu hỏi cũ' }], next_cursor: null })
  render(<SessionAssistant scope={scope} documentId="doc" />)
  await screen.findByText('Câu hỏi cũ')
  await userEvent.click(screen.getByRole('button', { name: 'Chat mới' }))
  expect(screen.queryByText('Câu hỏi cũ')).not.toBeInTheDocument()
  expect(createConversation).not.toHaveBeenCalled()
  await userEvent.click(screen.getByRole('button', { name: 'Lịch sử' }))
  await userEvent.click(await screen.findByRole('button', { name: 'Mở phiên Câu hỏi cũ' }))
  expect(await screen.findByText('Câu hỏi cũ')).toBeVisible()
})

it('does not render a late answer into a new chat', async () => {
  let finish
  sendChat.mockImplementation(() => new Promise(resolve => { finish = resolve }))
  render(<SessionAssistant scope={scope} documentId="doc" />)
  await waitFor(() => expect(screen.getByRole('textbox', { name: 'Câu hỏi cho ayo' })).toBeEnabled())
  await userEvent.type(screen.getByRole('textbox', { name: 'Câu hỏi cho ayo' }), 'Lượt đang chạy{Enter}')
  await waitFor(() => expect(sendChat).toHaveBeenCalled())
  await userEvent.click(screen.getByRole('button', { name: 'Chat mới' }))
  await act(async () => finish(result))
  expect(screen.queryByText('Lượt đang chạy')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Trích dẫn [1]' })).not.toBeInTheDocument()
})

it('changing documents loads the new scope without leaking old turns', async () => {
  listConversations.mockResolvedValueOnce({ results: [{ id: 'conv' }], next_cursor: null })
  const { rerender } = render(<SessionAssistant scope={scope} documentId="doc" />)
  await screen.findByText('Câu hỏi cũ')
  rerender(<SessionAssistant scope={scope} documentId="other-doc" />)
  await waitFor(() => expect(listConversations).toHaveBeenLastCalledWith({ ...scope, document_id: 'other-doc' }, expect.anything()))
  expect(screen.queryByText('Câu hỏi cũ')).not.toBeInTheDocument()
})

it('keeps a new reply last when loading older turns', async () => {
  listConversations.mockResolvedValue({ results: [{ id: 'conv' }] })
  getConversation.mockResolvedValueOnce({ ...detail, turns: [{ ...detail.turns[0], position: 21 }], next_before: 21 })
  render(<SessionAssistant scope={scope} documentId="doc" />)
  await screen.findByText('Câu hỏi cũ')
  await userEvent.type(screen.getByRole('textbox'), 'Lượt mới nhất{Enter}')
  await waitFor(() => expect(screen.getByRole('textbox')).toBeEnabled())
  getConversation.mockResolvedValueOnce({ ...detail, turns: [{ ...detail.turns[0], id: 'older', position: 1, question: 'Lượt đầu tiên' }], next_before: null })
  await userEvent.click(screen.getByRole('button', { name: 'Xem các lượt trước' }))
  await screen.findByText('Lượt đầu tiên')
  expect([...document.querySelectorAll('.ai-user-message')].map(row => row.textContent)).toEqual(['Lượt đầu tiên', 'Câu hỏi cũ', 'Lượt mới nhất'])
})

it('retries an uncertain network outcome with the original idempotency key', async () => {
  sendChat.mockRejectedValueOnce({ status: 0 })
  render(<SessionAssistant scope={scope} documentId="doc" />)
  await waitFor(() => expect(screen.getByRole('textbox')).toBeEnabled())
  await userEvent.type(screen.getByRole('textbox'), 'Đừng tạo lượt trùng{Enter}')
  await userEvent.click(await screen.findByRole('button', { name: 'Kiểm tra lại lượt hỏi' }))
  await screen.findByRole('button', { name: 'Trích dẫn [1]' })
  expect(sendChat).toHaveBeenCalledTimes(2)
  expect(sendChat.mock.calls[1][0]).toEqual(sendChat.mock.calls[0][0])
  expect(document.querySelectorAll('.ai-user-message')).toHaveLength(1)
})

it('does not leave older-history pagination stuck if a question is sent while loading it', async () => {
  let finishOlder
  listConversations.mockResolvedValue({ results: [{ id: 'conv' }] })
  getConversation.mockResolvedValueOnce({ ...detail, next_before: 21 })
  render(<SessionAssistant scope={scope} documentId="doc" />)
  await screen.findByText('Câu hỏi cũ')
  getConversation.mockImplementationOnce(() => new Promise(resolve => { finishOlder = resolve }))
  await userEvent.click(screen.getByRole('button', { name: 'Xem các lượt trước' }))
  await userEvent.type(screen.getByRole('textbox'), 'Câu hỏi tiếp{Enter}')
  await waitFor(() => expect(sendChat).toHaveBeenCalled())
  await act(async () => finishOlder({ ...detail, turns: [], next_before: null }))
  expect(screen.getByRole('button', { name: 'Xem các lượt trước' })).toBeEnabled()
})

it('anchors history to its icon and supports outside dismissal and Escape with focus restoration', async () => {
  render(<SessionAssistant scope={scope} documentId="doc" />)
  await waitFor(() => expect(screen.getByRole('textbox')).toBeEnabled())
  const trigger = screen.getByRole('button', { name: 'Lịch sử', exact: true })
  await userEvent.click(trigger)
  const dialog = screen.getByRole('dialog', { name: 'Lịch sử chat' })
  expect(dialog.parentElement).toContainElement(trigger)
  await userEvent.keyboard('{Escape}')
  expect(trigger).toHaveFocus()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(dialog).toBeInTheDocument()
  await waitFor(() => expect(dialog).not.toBeInTheDocument())
  await userEvent.click(trigger)
  await userEvent.click(screen.getByRole('textbox'))
  expect(trigger).toHaveAttribute('aria-expanded', 'false')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})
