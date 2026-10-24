import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { it, expect, vi } from 'vitest'
import SessionWorkspace from './SessionWorkspace'
import { sendChat } from '../services/ai.service'
vi.mock('./notifications/NotificationBell',()=>({default:()=>null}))
vi.mock('./documents/CourseDocuments',()=>({default:({onDocumentsChanged})=><button onClick={()=>onDocumentsChanged([
  {document_id:'doc-1',title:'Chương một: Kiến thức nền tảng'},
  {document_id:'doc-2',title:'Chương hai: Phân tích dữ liệu và các ứng dụng thực tiễn trong hệ thống học tập'},
])}>Nạp học liệu thử</button>}))
vi.mock('./assessments/SessionAssessments',()=>({default:({rows,selectedId,onRequestAssistance})=><button onClick={()=>onRequestAssistance({assessment_id:selectedId || rows[0].id,question_id:'q1'})}>Yêu cầu gợi ý</button>}))
vi.mock('../services/assessment.service',()=>({assessmentPath:()=>'/assessments/',listAssessments:vi.fn(async()=>[
  {id:'a1',title:'Bài A',mode:'PRACTICE'}, {id:'a2',title:'Bài B',mode:'PRACTICE'}])}))
vi.mock('../services/video.service',()=>({videoPath:()=>'/videos/',listSessionVideos:vi.fn(async()=>[])}))
vi.mock('../services/ai.service',()=>({sendChat:vi.fn(),chatErrorMessage:()=>''}))
it('aborts the previous exercise hint when another assessment is selected', async()=>{
  sendChat.mockImplementation(()=>new Promise(()=>{}))
  render(<SessionWorkspace course={{id:'c1'}} room={{id:'r1'}} session={{id:'assessment-scope',title:'Buổi học'}} canManage={false} />)
  await userEvent.click(screen.getByRole('button',{name:'Bài tập',exact:true}))
  await userEvent.click(await screen.findByRole('button',{name:/^Bài A/}))
  await userEvent.click(screen.getByRole('button',{name:'Yêu cầu gợi ý'}))
  await userEvent.type(screen.getByRole('textbox',{name:'Câu hỏi cho trợ lý'}),'Tôi nên bắt đầu ra sao?')
  await userEvent.click(screen.getByRole('button',{name:'Gửi câu hỏi'}))
  const signal=sendChat.mock.calls[0][1].signal
  await userEvent.click(screen.getByRole('button',{name:/^Bài B/}))
  await waitFor(()=>expect(signal.aborted).toBe(true))
  expect(screen.queryByRole('combobox',{name:'Cách hỗ trợ'})).not.toBeInTheDocument()
})

it('keeps the conversation when the assistant is closed and reopened', async()=>{
  sendChat.mockResolvedValue({status:'ANSWERED',answer:'Câu trả lời được giữ lại',citations:[]})
  render(<SessionWorkspace course={{id:'c1'}} room={{id:'r1'}} session={{id:'retained-chat',title:'Buổi học'}} canManage={false} />)
  await userEvent.click(screen.getByRole('button',{name:'Trợ lý AI'}))
  await userEvent.type(screen.getByRole('textbox',{name:'Câu hỏi cho trợ lý'}),'Câu hỏi được giữ lại{Enter}')
  await screen.findByText('Câu hỏi được giữ lại')
  await userEvent.click(screen.getByRole('button',{name:'Đóng trợ lý AI'}))
  expect(screen.queryByRole('textbox',{name:'Câu hỏi cho trợ lý'})).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button',{name:'Trợ lý AI'}))
  expect(screen.getByText('Câu hỏi được giữ lại')).toBeVisible()
})

it('shows the selected material title in the assistant and updates on selection', async()=>{
  render(<SessionWorkspace course={{id:'c1'}} room={{id:'r1'}} session={{id:'material-heading',title:''}} canManage={false} />)
  await userEvent.click(screen.getByRole('button',{name:'Trợ lý AI'}))
  const panel=within(screen.getByRole('complementary',{name:'Trợ lý AI của buổi học'}))
  await userEvent.click(screen.getByRole('button',{name:'Nạp học liệu thử'}))
  expect(panel.getByText('Chương một: Kiến thức nền tảng')).toBeVisible()
  const title='Chương hai: Phân tích dữ liệu và các ứng dụng thực tiễn trong hệ thống học tập'
  await userEvent.click(screen.getByRole('button',{name:title,exact:true}))
  expect(panel.getByText(title)).toHaveAttribute('title',title)
  expect(panel.queryByText('Chương một: Kiến thức nền tảng')).not.toBeInTheDocument()
})
