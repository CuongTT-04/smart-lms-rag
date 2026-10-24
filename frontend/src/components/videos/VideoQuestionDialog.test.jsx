import { expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import VideoQuestionDialog from './VideoQuestionDialog'
it('seeds the timestamp from playback and submits an essay without rewind or MCQ keys', async () => {
  const save = vi.fn(async () => {})
  render(<VideoQuestionDialog startTime={80} duration={180} onSave={save} onClose={vi.fn()} />)
  expect(screen.getByLabelText(/Mốc bắt đầu/)).toHaveValue('01:20')
  await userEvent.click(screen.getByRole('combobox', { name: 'Loại câu hỏi' }))
  await userEvent.click(screen.getByRole('option', { name: 'Tự luận' }))
  expect(screen.queryByLabelText(/Mốc quay lại/)).not.toBeInTheDocument()
  await userEvent.type(screen.getByLabelText('Nội dung câu hỏi'), 'Trình bày khái niệm')
  await userEvent.click(screen.getByRole('button', { name: 'Tạo câu hỏi', exact: true }))
  expect(save).toHaveBeenCalledWith(expect.objectContaining({ kind: 'TEXT', start_time: 80, rewind_time: null, choices: [], correct_ids: [] }))
  expect(screen.getByRole('button', { name: 'Tạo gợi ý bằng AI' })).toBeDisabled()
})
it('lets teachers choose multiple selection independently of the number of correct answers', async () => {
  const save = vi.fn(async () => {})
  const question = {kind:'MCQ',prompt:'Chọn đúng',multiple:false,correct_ids:['a'],choices:[{id:'a',text:'A'},{id:'b',text:'B'}],start_time:5,rewind_time:null}
  render(<VideoQuestionDialog question={question} duration={180} onSave={save} onClose={vi.fn()} />)
  expect(screen.getAllByRole('radio')).toHaveLength(2)
  await userEvent.click(screen.getByRole('combobox',{name:'Kiểu trắc nghiệm'}))
  await userEvent.click(screen.getByRole('option',{name:'Nhiều đáp án'}))
  expect(screen.getAllByRole('checkbox')).toHaveLength(2)
  await userEvent.click(screen.getByRole('button',{name:'Lưu thay đổi',exact:true}))
  expect(save).toHaveBeenCalledWith(expect.objectContaining({multiple:true,correct_ids:['a']}))
})
