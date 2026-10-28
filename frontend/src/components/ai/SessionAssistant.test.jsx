import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi, expect, it, beforeEach } from 'vitest'
import SessionAssistant from './SessionAssistant'
import ChatAnswer from './ChatAnswer'
import { sendChat, sendChatFeedback } from '../../services/ai.service'

vi.mock('../../services/ai.service', () => ({ sendChat: vi.fn(), sendChatFeedback: vi.fn(), chatErrorMessage: () => 'Không thể sử dụng AI.' }))
const scope={course_id:'c1',classroom_id:'r1',session_id:'s1'}
const citation={label:1,document_id:'d1',version_id:'v1',chunk_id:'ch1',document_title:'Tài liệu',page_number:3,excerpt:'Đoạn trích nguyên văn từ PDF.'}
const response={request_id:'answer-1',status:'ANSWERED',answer:'Nội dung [1]',citations:[citation]}
beforeEach(() => {
  sendChat.mockReset(); sendChat.mockResolvedValue(response)
  sendChatFeedback.mockReset(); sendChatFeedback.mockImplementation(async (_id,rating)=>({rating}))
  vi.stubGlobal('matchMedia',()=>({matches:true}))
})

it('sends server selectors only and opens a trusted citation', async () => {
  const open=vi.fn()
  render(<SessionAssistant scope={scope} onOpenCitation={open} />)
  await userEvent.type(screen.getByRole('textbox',{name:'Câu hỏi cho ayo'}),'Nội dung?')
  await userEvent.click(screen.getByRole('button',{name:'Gửi câu hỏi'}))
  expect(await screen.findByRole('button',{name:'Trích dẫn [1]'})).toBeVisible()
  expect(sendChat).toHaveBeenCalledWith({...scope,mode:'qa',question:'Nội dung?'},expect.objectContaining({signal:expect.any(AbortSignal)}))
  expect(screen.getByRole('button',{name:'[1] Tài liệu — trang 3'})).not.toBeVisible()
  await userEvent.click(screen.getByText('Nguồn học liệu (1)'))
  await userEvent.click(screen.getByRole('button',{name:'[1] Tài liệu — trang 3'}))
  expect(open).toHaveBeenCalledWith(citation)
  await userEvent.click(screen.getByText('Nguồn học liệu (1)'))
  expect(screen.getByRole('button',{name:'[1] Tài liệu — trang 3'})).not.toBeVisible()
})

it('posts questions into a retained conversation and clears the composer', async () => {
  render(<SessionAssistant scope={scope} />)
  const input=screen.getByRole('textbox',{name:'Câu hỏi cho ayo'})
  await userEvent.type(input,'Câu hỏi đầu{Enter}')
  expect(await screen.findByText('Câu hỏi đầu')).toBeVisible()
  expect(input).toHaveValue('')
  await screen.findByRole('button',{name:'Trích dẫn [1]'})
  sendChat.mockResolvedValueOnce({...response,request_id:'answer-2',answer:'Câu trả lời tiếp theo'})
  await userEvent.type(input,'Câu hỏi sau{Enter}')
  expect(await screen.findByText('Câu trả lời tiếp theo')).toBeVisible()
  expect(screen.getByText('Câu hỏi đầu')).toBeVisible()
  expect(screen.getByText('Câu hỏi sau')).toBeVisible()
})

it('previews the original excerpt on hover or focus and retains the PDF source', async () => {
  render(<SessionAssistant scope={scope} />)
  await userEvent.type(screen.getByRole('textbox',{name:'Câu hỏi cho ayo'}),'Nguồn?{Enter}')
  const marker=await screen.findByRole('button',{name:'Trích dẫn [1]'})
  await userEvent.hover(marker)
  expect(screen.getByRole('tooltip')).toHaveTextContent('Đoạn trích nguyên văn từ PDF.')
  await userEvent.unhover(marker)
  await waitFor(() => expect(screen.queryByRole('tooltip')).not.toBeInTheDocument())
  marker.focus()
  expect(await screen.findByRole('tooltip')).toHaveTextContent('trang 3')
  await userEvent.click(screen.getByText('Nguồn học liệu (1)'))
  expect(screen.getByRole('button',{name:'[1] Tài liệu — trang 3'})).toBeVisible()
})

it('saves changes to answer feedback and does not claim success on failure', async () => {
  render(<SessionAssistant scope={scope} />)
  await userEvent.type(screen.getByRole('textbox',{name:'Câu hỏi cho ayo'}),'Đánh giá{Enter}')
  const like=await screen.findByRole('button',{name:'Thích câu trả lời'})
  await userEvent.click(like)
  expect(like).toHaveAttribute('aria-pressed','true')
  expect(sendChatFeedback).toHaveBeenLastCalledWith('answer-1','LIKE',expect.anything())
  await userEvent.click(like)
  expect(like).toHaveAttribute('aria-pressed','false')
  sendChatFeedback.mockRejectedValueOnce(new Error('offline'))
  await userEvent.click(screen.getByRole('button',{name:'Không thích câu trả lời'}))
  expect(await screen.findByRole('alert')).toHaveTextContent('Chưa lưu được đánh giá')
  expect(screen.getByRole('button',{name:'Không thích câu trả lời'})).toHaveAttribute('aria-pressed','false')
})

it('shows thinking while pending and keeps the question on failure', async () => {
  let reject
  sendChat.mockImplementation(()=>new Promise((_resolve, fail)=>{reject=fail}))
  render(<SessionAssistant scope={scope} />)
  await userEvent.type(screen.getByRole('textbox',{name:'Câu hỏi cho ayo'}),'Giải thích{Enter}')
  expect(screen.getByRole('status')).toHaveTextContent('Đang suy nghĩ')
  expect(screen.getByText('Giải thích')).toBeVisible()
  reject(new Error('offline'))
  expect(await screen.findByRole('alert')).toBeVisible()
  expect(screen.getByText('Giải thích')).toBeVisible()
})

it('uses Shift+Enter for a newline instead of submitting', async () => {
  render(<SessionAssistant scope={scope} />)
  const input=screen.getByRole('textbox',{name:'Câu hỏi cho ayo'})
  await userEvent.type(input,'Dòng đầu{Shift>}{Enter}{/Shift}Dòng sau')
  expect(input).toHaveValue('Dòng đầu\nDòng sau')
  expect(sendChat).not.toHaveBeenCalled()
})

it('keeps a focused citation preview open when the pointer leaves', async () => {
  render(<SessionAssistant scope={scope} />)
  await userEvent.type(screen.getByRole('textbox',{name:'Câu hỏi cho ayo'}),'Nguồn?{Enter}')
  const marker=await screen.findByRole('button',{name:'Trích dẫn [1]'})
  await userEvent.click(marker)
  await userEvent.unhover(marker)
  await new Promise((resolve)=>setTimeout(resolve,200))
  expect(screen.getByRole('tooltip')).toBeVisible()
  await userEvent.keyboard('{Escape}')
  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
})

it('reveals words over time and then exposes interactive citations', async () => {
  vi.stubGlobal('matchMedia',()=>({matches:false}))
  vi.useFakeTimers()
  try {
    const {container}=render(<ChatAnswer result={response} />)
    expect(container.querySelector('.ai-chat-answer [aria-hidden="true"]')).toHaveTextContent('')
    await act(async()=>{vi.advanceTimersByTime(24)})
    expect(container.querySelector('.ai-chat-answer [aria-hidden="true"]')).toHaveTextContent('Nội')
    await act(async()=>{vi.advanceTimersByTime(200)})
    expect(screen.getByRole('button',{name:'Trích dẫn [1]'})).toBeVisible()
    expect(container.querySelector('.ai-typing-cursor')).toBeNull()
  } finally { vi.useRealTimers() }
})

it('ignores a late response after scope changes', async () => {
  let finish
  sendChat.mockImplementation(() => new Promise((resolve) => { finish=resolve }))
  const {rerender}=render(<SessionAssistant scope={scope} />)
  await userEvent.type(screen.getByRole('textbox',{name:'Câu hỏi cho ayo'}),'Câu hỏi cũ')
  await userEvent.click(screen.getByRole('button',{name:'Gửi câu hỏi'}))
  const signal=sendChat.mock.calls[0][1].signal
  rerender(<SessionAssistant scope={{...scope,session_id:'s2'}} />)
  await waitFor(() => expect(signal.aborted).toBe(true))
  finish(response)
  await waitFor(() => expect(screen.queryByText('Nội dung [1]')).not.toBeInTheDocument())
})

it('shows service errors and allows retry', async () => {
  sendChat.mockRejectedValue(new Error('secret'))
  render(<SessionAssistant scope={scope} />)
  await userEvent.type(screen.getByRole('textbox',{name:'Câu hỏi cho ayo'}),'Nội dung?')
  await userEvent.click(screen.getByRole('button',{name:'Gửi câu hỏi'}))
  expect(await screen.findByRole('alert')).toHaveTextContent('Không thể sử dụng AI.')
  expect(screen.getByRole('textbox',{name:'Câu hỏi cho ayo'})).toBeEnabled()
})

it('starts in hint mode when opened from a practice question', async () => {
  render(<SessionAssistant scope={scope} exercise={{assessment_id:'a1',question_id:'q1'}} />)
  await userEvent.type(screen.getByRole('textbox',{name:'Câu hỏi cho ayo'}),'Giúp tôi bắt đầu')
  await userEvent.click(screen.getByRole('button',{name:'Gửi câu hỏi'}))
  expect(sendChat.mock.calls[0][0]).toMatchObject({mode:'hint',assessment_id:'a1',question_id:'q1'})
})
