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
vi.mock('./assessments/SessionAssessments',()=>({default:({rows,selectedId,onRequestAssistance})=><button onClick={()=>onRequestAssistance({assessment_id:selectedId || rows[0].id,question_id:'q1',question_number:1,question_prompt:'ALU thực hiện những phép toán nào?'})}>Yêu cầu gợi ý</button>}))
vi.mock('../services/assessment.service',()=>({assessmentPath:()=>'/assessments/',listAssessments:vi.fn(async()=>[
  {id:'a1',title:'Bài A',mode:'PRACTICE'}, {id:'a2',title:'Bài B',mode:'PRACTICE'}])}))
vi.mock('../services/video.service',()=>({videoPath:()=>'/videos/',listSessionVideos:vi.fn(async()=>[])}))
vi.mock('../services/ai.service',()=>({sendChat:vi.fn(),chatErrorMessage:()=>'',
  listConversations:vi.fn(async()=>({results:[],next_cursor:null})),
  createConversation:vi.fn(async()=>({id:'document-conversation'})),
  getConversation:vi.fn(async()=>({id:'document-conversation',turns:[],next_before:null})),
}))
it('aborts the previous exercise hint when another assessment is selected', async()=>{
  sendChat.mockImplementation(()=>new Promise(()=>{}))
  render(<SessionWorkspace course={{id:'c1'}} room={{id:'r1'}} session={{id:'assessment-scope',title:'Buổi học'}} canManage={false} />)
  await userEvent.click(screen.getByRole('button',{name:'Bài tập',exact:true}))
  await userEvent.click(await screen.findByRole('button',{name:/^Bài A/}))
  await userEvent.click(screen.getByRole('button',{name:'Yêu cầu gợi ý'}))
  await waitFor(()=>expect(sendChat).toHaveBeenCalledTimes(1))
  expect(screen.getByText('Gợi ý cho bài')).toBeVisible()
  expect(screen.getByText('Câu 1')).toBeVisible()
  expect(screen.getByText('ALU thực hiện những phép toán nào?')).toBeVisible()
  expect(sendChat.mock.calls[0][0]).toMatchObject({
    course_id:'c1', classroom_id:'r1', session_id:'assessment-scope',
    mode:'hint', assessment_id:'a1', question_id:'q1',
  })
  expect(sendChat.mock.calls[0][0]).not.toHaveProperty('conversation_id')
  const signal=sendChat.mock.calls[0][1].signal
  await userEvent.click(screen.getByRole('button',{name:/^Bài B/}))
  await waitFor(()=>expect(signal.aborted).toBe(true))
  expect(screen.queryByRole('combobox',{name:'Cách hỗ trợ'})).not.toBeInTheDocument()
})

it('returns from exercise hints to material questions and aborts the pending hint', async()=>{
  sendChat.mockImplementation(()=>new Promise(()=>{}))
  render(<SessionWorkspace course={{id:'c1'}} room={{id:'r1'}} session={{id:'return-to-material',title:'Buổi học'}} canManage={false} />)
  await userEvent.click(screen.getByRole('button',{name:'Bài tập',exact:true}))
  await userEvent.click(await screen.findByRole('button',{name:/^Bài A/}))
  await userEvent.click(screen.getByRole('button',{name:'Yêu cầu gợi ý'}))
  await waitFor(()=>expect(sendChat).toHaveBeenCalledTimes(1))
  const signal=sendChat.mock.calls[0][1].signal
  await userEvent.click(screen.getByRole('button',{name:'Hỏi đáp học liệu',exact:true}))
  await waitFor(()=>expect(signal.aborted).toBe(true))
  expect(screen.queryByText('Gợi ý cho bài')).not.toBeInTheDocument()
  expect(screen.queryByText('ALU thực hiện những phép toán nào?')).not.toBeInTheDocument()
  expect(sendChat).toHaveBeenCalledTimes(1)
})

it('keeps the conversation when the assistant is closed and reopened', async()=>{
  sendChat.mockResolvedValue({status:'ANSWERED',answer:'Câu trả lời được giữ lại',citations:[]})
  render(<SessionWorkspace course={{id:'c1'}} room={{id:'r1'}} session={{id:'retained-chat',title:'Buổi học'}} canManage={false} />)
  await userEvent.click(screen.getByRole('button',{name:'Nạp học liệu thử'}))
  await userEvent.click(screen.getByRole('button',{name:'Trợ lý Ayo'}))
  await waitFor(()=>expect(screen.getByRole('textbox',{name:'Câu hỏi cho ayo'})).toBeEnabled())
  await userEvent.type(screen.getByRole('textbox',{name:'Câu hỏi cho ayo'}),'Câu hỏi được giữ lại{Enter}')
  await screen.findByText('Câu hỏi được giữ lại')
  await userEvent.click(screen.getByRole('button',{name:'Đóng ayo'}))
  expect(screen.queryByRole('textbox',{name:'Câu hỏi cho ayo'})).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button',{name:'Trợ lý Ayo'}))
  expect(screen.getByText('Câu hỏi được giữ lại')).toBeVisible()
  expect(sendChat.mock.calls[0][0]).toMatchObject({document_ids:['doc-1'],conversation_id:'document-conversation'})
})

it('shows the selected material title in the assistant and updates on selection', async()=>{
  render(<SessionWorkspace course={{id:'c1'}} room={{id:'r1'}} session={{id:'material-heading',title:''}} canManage={false} />)
  await userEvent.click(screen.getByRole('button',{name:'Trợ lý Ayo'}))
  const panel=within(screen.getByRole('complementary',{name:'Trợ lý Ayo — Bạn đồng hành học tập'}))
  await userEvent.click(screen.getByRole('button',{name:'Nạp học liệu thử'}))
  expect(panel.getByText('Chương một: Kiến thức nền tảng')).toBeVisible()
  const title='Chương hai: Phân tích dữ liệu và các ứng dụng thực tiễn trong hệ thống học tập'
  await userEvent.click(screen.getByRole('button',{name:title,exact:true}))
  expect(panel.getByText(title)).toHaveAttribute('title',title)
  expect(panel.queryByText('Chương một: Kiến thức nền tảng')).not.toBeInTheDocument()
})
