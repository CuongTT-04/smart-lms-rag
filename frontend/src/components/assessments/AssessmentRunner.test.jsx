import { beforeEach, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import AssessmentRunner from './AssessmentRunner'
import { assessmentWrite, saveAssessmentDraft } from '../../services/assessment.service'

vi.mock('../../services/assessment.service', () => ({ assessmentWrite: vi.fn(), saveAssessmentDraft: vi.fn(), getAssessment: vi.fn(), downloadAssessmentFile: vi.fn() }))
const question = { id: 'q1', prompt: 'Chọn A', choices: [{id:'a',text:'Lựa chọn A'},{id:'b',text:'Lựa chọn B'}], hint:'Gợi ý riêng' }
const info = { id:'a1', mode:'PRACTICE', kind:'QUIZ', questions:[question], due_at:'2099-01-01T00:00:00Z', server_now:new Date().toISOString(), attempts:[], hint:'Gợi ý của giáo viên' }
const draft = () => ({ id:'at1', number:1, status:'DRAFT', revision:0, answers:{}, text:'', file_name:'', questions:[question], server_now:new Date().toISOString(), expires_at:'2099-01-01T00:00:00Z' })
beforeEach(() => {
  vi.clearAllMocks()
  Object.defineProperty(document, 'fullscreenElement', {configurable:true,value:null})
  HTMLElement.prototype.requestFullscreen = vi.fn(async function () { Object.defineProperty(document, 'fullscreenElement', {configurable:true,value:this}) })
  document.exitFullscreen = vi.fn(async () => {
    Object.defineProperty(document, 'fullscreenElement', {configurable:true,value:null})
    document.dispatchEvent(new Event('fullscreenchange'))
  })
  assessmentWrite.mockImplementation(async (path) => path.endsWith('start/') ? draft() : path.endsWith('submit/') ? {...draft(),status:'SUBMITTED',score:10} : {recorded:true})
  saveAssessmentDraft.mockImplementation(async (_, values) => ({...draft(),answers:values.answers || {},revision:values.revision+1}))
})
it.each(['QUIZ','TEXT'])('exits fullscreen only after confirmed successful TEST submission (%s), without a violation', async (kind) => {
  render(<AssessmentRunner path="/assessments/a1/" info={{...info,mode:'TEST',kind}} />)
  await userEvent.click(screen.getByRole('button',{name:'Bắt đầu làm bài'}))
  await userEvent.click(screen.getByRole('button',{name:'Nộp bài',exact:true}))
  expect(document.exitFullscreen).not.toHaveBeenCalled()
  await userEvent.click(screen.getByRole('button',{name:'Xác nhận nộp',exact:true}))
  await waitFor(()=>expect(document.exitFullscreen).toHaveBeenCalledTimes(1))
  expect(document.fullscreenElement).toBeNull()
  expect(assessmentWrite.mock.calls.some(([p])=>p.endsWith('events/'))).toBe(false)
})
it('exits fullscreen when the server returns an automatically finalized TEST attempt', async () => {
  assessmentWrite.mockResolvedValueOnce({...draft(),status:'SUBMITTED',auto_submitted:true})
  render(<AssessmentRunner path="/assessments/a1/" info={{...info,mode:'TEST'}} />)
  await userEvent.click(screen.getByRole('button',{name:'Bắt đầu làm bài'}))
  await waitFor(()=>expect(document.exitFullscreen).toHaveBeenCalledTimes(1))
  expect(screen.getByText(/Hệ thống đã chốt câu trả lời được lưu/)).toBeVisible()
})
it('keeps fullscreen and the confirmation dialog when TEST submission fails', async () => {
  assessmentWrite.mockImplementation(async (path)=>{
    if (path.endsWith('submit/')) throw {status:503}
    return draft()
  })
  render(<AssessmentRunner path="/assessments/a1/" info={{...info,mode:'TEST'}} />)
  await userEvent.click(screen.getByRole('button',{name:'Bắt đầu làm bài'}))
  await userEvent.click(screen.getByRole('button',{name:'Nộp bài',exact:true}))
  await userEvent.click(screen.getByRole('button',{name:'Xác nhận nộp',exact:true}))
  await waitFor(()=>expect(screen.getAllByRole('alert')).toHaveLength(2))
  expect(screen.getByRole('dialog',{name:'Xác nhận nộp bài kiểm tra'})).toBeVisible()
  expect(document.exitFullscreen).not.toHaveBeenCalled()
  expect(document.fullscreenElement).not.toBeNull()
})
it('practice allows submit without a one-shot dialog and exposes assistance', async () => {
  render(<AssessmentRunner path="/assessments/a1/" info={info} />)
  expect(screen.getByRole('button',{name:'Trợ giúp AI'})).toBeVisible()
  await userEvent.click(screen.getByRole('button',{name:'Bắt đầu làm bài'}))
  await userEvent.click(screen.getByRole('radio',{name:'Lựa chọn A'}))
  await userEvent.click(screen.getByRole('button',{name:'Nộp bài',exact:true}))
  expect(await screen.findByText('Điểm: 10/10')).toBeVisible()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(HTMLElement.prototype.requestFullscreen).not.toHaveBeenCalled()
  expect(saveAssessmentDraft).toHaveBeenCalledWith('/assessments/a1/attempts/at1/',{revision:0,answers:{q1:'a'}})
})
it('test requests fullscreen, logs a warning without submitting and requires confirmation', async () => {
  const active = vi.fn()
  render(<AssessmentRunner path="/assessments/a1/" info={{...info,mode:'TEST'}} onTestActive={active} />)
  expect(screen.queryByRole('button',{name:'Trợ giúp AI'})).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button',{name:'Bắt đầu làm bài'}))
  expect(HTMLElement.prototype.requestFullscreen).toHaveBeenCalled()
  expect(assessmentWrite).toHaveBeenCalledWith('/assessments/a1/start/','POST',expect.objectContaining({fullscreen:true}))
  Object.defineProperty(document, 'fullscreenElement', {configurable:true,value:null})
  act(() => fireEvent(document,new Event('fullscreenchange')))
  expect(await screen.findByText(/Bạn đã thoát toàn màn hình/)).toBeVisible()
  expect(assessmentWrite).toHaveBeenCalledWith('/assessments/a1/attempts/at1/events/','POST',expect.objectContaining({kind:'FULLSCREEN_EXIT'}))
  expect(assessmentWrite.mock.calls.some(([p])=>p.endsWith('submit/'))).toBe(false)
  await userEvent.click(screen.getByRole('button',{name:'Nộp bài',exact:true}))
  expect(screen.getByRole('dialog',{name:'Xác nhận nộp bài kiểm tra'})).toBeVisible()
  await userEvent.click(screen.getByRole('button',{name:'Hủy',exact:true}))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button',{name:'Nộp bài',exact:true}))
  await userEvent.click(screen.getByRole('button',{name:'Xác nhận nộp',exact:true}))
  await waitFor(() => expect(assessmentWrite).toHaveBeenCalledWith('/assessments/a1/attempts/at1/submit/','POST',{revision:0,confirmed:true}))
})
it('does not start a test when fullscreen is unavailable', async () => {
  HTMLElement.prototype.requestFullscreen = undefined
  render(<AssessmentRunner path="/assessments/a1/" info={{...info,mode:'TEST'}} />)
  await userEvent.click(screen.getByRole('button',{name:'Bắt đầu làm bài'}))
  expect(await screen.findByRole('alert')).toHaveTextContent('Trình duyệt không hỗ trợ toàn màn hình')
  expect(assessmentWrite).not.toHaveBeenCalled()
})
it('keeps the text test title and task inside the fullscreen area', async () => {
  render(<AssessmentRunner path="/assessments/a1/" info={{...info,mode:'TEST',kind:'TEXT',title:'Giải thích RAG',description:'Phân tích vai trò truy xuất trong RAG.'}} />)
  await userEvent.click(screen.getByRole('button',{name:'Bắt đầu làm bài'}))
  const fullscreenArea = document.fullscreenElement
  expect(fullscreenArea).toHaveTextContent('Giải thích RAG')
  expect(fullscreenArea).toHaveTextContent('Phân tích vai trò truy xuất trong RAG.')
})
it('warns before closing a page with changes that have not reached the server', async () => {
  render(<AssessmentRunner path="/assessments/a1/" info={info} />)
  await userEvent.click(screen.getByRole('button',{name:'Bắt đầu làm bài'}))
  await userEvent.click(screen.getByRole('radio',{name:'Lựa chọn A'}))
  const leaving = new Event('beforeunload',{cancelable:true})
  fireEvent(window,leaving)
  expect(leaving.defaultPrevented).toBe(true)
  await userEvent.click(screen.getByRole('button',{name:'Lưu bản nháp',exact:true}))
  const saved = new Event('beforeunload',{cancelable:true})
  fireEvent(window,saved)
  expect(saved.defaultPrevented).toBe(false)
})
it('uses round single controls and square multiple controls in one quiz and saves all selections', async () => {
  const questions = [question,{...question,id:'q2',prompt:'Chọn nhiều',multiple:true}]
  assessmentWrite.mockResolvedValueOnce({...draft(),questions})
  render(<AssessmentRunner path="/assessments/a1/" info={{...info,questions}} />)
  await userEvent.click(screen.getByRole('button',{name:'Bắt đầu làm bài'}))
  expect(screen.getAllByRole('radio')).toHaveLength(2)
  expect(screen.getAllByRole('checkbox')).toHaveLength(2)
  await userEvent.click(screen.getAllByRole('radio')[0])
  await userEvent.click(screen.getAllByRole('radio')[1])
  await userEvent.click(screen.getAllByRole('checkbox')[0])
  await userEvent.click(screen.getAllByRole('checkbox')[1])
  await userEvent.click(screen.getByRole('button',{name:'Lưu bản nháp',exact:true}))
  expect(saveAssessmentDraft).toHaveBeenCalledWith('/assessments/a1/attempts/at1/',{revision:0,answers:{q1:'b',q2:['a','b']}})
})
