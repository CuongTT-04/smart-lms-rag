import { beforeEach, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import AssessmentDashboard from './AssessmentDashboard'
import { getAssessment, downloadAssessmentFile } from '../../services/assessment.service'
vi.mock('../../services/assessment.service', () => ({getAssessment:vi.fn(),downloadAssessmentFile:vi.fn(),assessmentWrite:vi.fn()}))
const report = {summary:{total:1,submitted:0,not_submitted:1,pending:0,average:null,violations:0},students:[],attempts:[],score_distribution:[],question_stats:[],submissions_by_day:[]}
beforeEach(() => {vi.clearAllMocks();window.history.replaceState(null, '', '/');getAssessment.mockResolvedValue(report)})
it('loads and opens the exact submission selected by a notification', async () => {
  window.history.replaceState({ohayoNavigation:{owner:'standalone',values:{'assessment.a1.attempt':'attempt-1'}}}, '', '/')
  getAssessment.mockImplementation(async (path) => path.includes('/attempts/') ? {
    id:'attempt-1',student_name:'Người nộp',number:1,status:'SUBMITTED',text:'Bài làm cần xem',grade_published:false,
  } : report)
  render(<AssessmentDashboard path="/assessments/a1/" info={{id:'a1',mode:'TEST',kind:'TEXT'}} />)
  expect(await screen.findByRole('dialog', {name:'Người nộp · Lượt 1'})).toBeVisible()
  expect(screen.getByText('Bài làm cần xem')).toBeVisible()
})
it.each(['TEST','PRACTICE'])('shows dashboard and filtered Excel export in %s', async (mode) => {
  render(<AssessmentDashboard path="/assessments/a1/" info={{id:'a1',mode,kind:'QUIZ'}} />)
  await waitFor(()=>expect(screen.getByRole('button',{name:'Xuất Excel'})).toBeEnabled())
  expect(screen.getByRole('heading',{name:mode==='TEST'?'Dashboard · Kiểm tra':'Dashboard · Ôn tập'})).toBeVisible()
  await userEvent.type(screen.getByRole('textbox',{name:'Tìm học viên'}),'Cuong')
  await userEvent.selectOptions(screen.getByRole('combobox',{name:'Trạng thái bài nộp'}),'PENDING')
  await waitFor(()=>expect(getAssessment).toHaveBeenLastCalledWith('/assessments/a1/dashboard/?q=Cuong&status=PENDING',expect.anything()))
  await waitFor(()=>expect(screen.getByRole('button',{name:'Xuất Excel'})).toBeEnabled())
  await userEvent.click(screen.getByRole('button',{name:'Xuất Excel'}))
  expect(downloadAssessmentFile).toHaveBeenCalledWith('/assessments/a1/export/?q=Cuong&status=PENDING','ket-qua-a1.xlsx','xlsx')
})
