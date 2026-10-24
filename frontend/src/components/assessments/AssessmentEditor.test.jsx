import { expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import AssessmentEditor from './AssessmentEditor'

it('sets each question type independently and reduces answer keys when switching back to single', async () => {
  const save = vi.fn(async () => {})
  const q = {id:'q1',prompt:'Q1',multiple:false,correct_ids:['a'],choices:[{id:'a',text:'A'},{id:'b',text:'B'}],hint:''}
  render(<AssessmentEditor value={{title:'Mixed quiz',kind:'QUIZ',mode:'PRACTICE',duration_seconds:600,due_at:'2099-01-01T00:00:00Z',questions:[q,{...q,id:'q2',prompt:'Q2'}]}} onSave={save} onClose={vi.fn()} />)
  await userEvent.selectOptions(screen.getByRole('combobox',{name:'Kiểu trắc nghiệm câu 1'}),'MULTIPLE')
  expect(screen.getAllByRole('checkbox')).toHaveLength(2)
  expect(screen.getAllByRole('radio')).toHaveLength(2)
  await userEvent.click(screen.getByRole('checkbox',{name:'Đáp án đúng câu 1: B'}))
  await userEvent.click(screen.getByRole('button',{name:'Lưu bài tập',exact:true}))
  expect(save.mock.calls.at(-1)[0].questions[0]).toMatchObject({multiple:true,correct_ids:['a','b']})
  await userEvent.selectOptions(screen.getByRole('combobox',{name:'Kiểu trắc nghiệm câu 1'}),'SINGLE')
  expect(screen.getAllByRole('radio')).toHaveLength(4)
  expect(screen.getByRole('radio',{name:'Đáp án đúng câu 1: A'})).toBeChecked()
  expect(screen.getByRole('radio',{name:'Đáp án đúng câu 1: B'})).not.toBeChecked()
  await userEvent.click(screen.getByRole('button',{name:'Lưu bài tập',exact:true}))
  expect(save.mock.calls.at(-1)[0].questions[0]).toMatchObject({multiple:false,correct_ids:['a']})
})
