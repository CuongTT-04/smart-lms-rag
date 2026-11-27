import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { useState } from 'react'
import InstitutionCombobox from './InstitutionCombobox'
import { listInstitutions } from '../services/institution.service'

vi.mock('../services/institution.service', () => ({ listInstitutions: vi.fn() }))
const school = { id: 'school', name: 'Đại học Bách khoa Hà Nội', province: 'Hà Nội', campus: '', aliases: ['HUST'] }
function Form() {
  const [value, setValue] = useState(null)
  return <InstitutionCombobox value={value} onChange={setValue} />
}
async function tick() { await act(async () => { await vi.advanceTimersByTimeAsync(300) }) }
beforeEach(() => { vi.useFakeTimers(); listInstitutions.mockReset(); listInstitutions.mockResolvedValue({ results: [school], has_more: false }) })
afterEach(() => { vi.useRealTimers() })

it('debounces queries, supports keyboard choice and exposes selected school', async () => {
  render(<Form />)
  const input = screen.getByRole('combobox')
  fireEvent.focus(input)
  fireEvent.change(input, { target: { value: 'bach' } })
  expect(listInstitutions).not.toHaveBeenCalled()
  await tick()
  expect(listInstitutions).toHaveBeenCalledWith('bach', expect.any(AbortSignal))
  expect(screen.getByRole('option', { name: /Đại học Bách khoa/ })).toBeVisible()
  fireEvent.keyDown(input, { key: 'ArrowDown' })
  fireEvent.keyDown(input, { key: 'Enter' })
  expect(input).toHaveValue(school.name)
  expect(input).toHaveAttribute('aria-expanded', 'false')
})

it('aborts old query and ignores a late response', async () => {
  let resolveOld
  listInstitutions.mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve }))
  render(<Form />)
  const input = screen.getByRole('combobox')
  fireEvent.focus(input)
  await tick()
  const oldSignal = listInstitutions.mock.calls[0][1]
  fireEvent.change(input, { target: { value: 'hust' } })
  await tick()
  expect(oldSignal.aborted).toBe(true)
  await act(async () => { resolveOld({ results: [{ ...school, name: 'Kết quả cũ' }] }) })
  expect(screen.queryByText('Kết quả cũ')).not.toBeInTheDocument()
  expect(screen.getByRole('option', { name: /Đại học Bách khoa/ })).toBeVisible()
})

it('offers an unlisted school even without results and closes with Escape', async () => {
  listInstitutions.mockResolvedValue({ results: [], has_more: false })
  render(<Form />)
  const input = screen.getByRole('combobox')
  fireEvent.focus(input); await tick()
  expect(screen.getByText('Không tìm thấy trường phù hợp.')).toBeVisible()
  fireEvent.click(screen.getByRole('option', { name: 'Chưa có trường trong danh sách' }))
  expect(input).toHaveValue('Chưa có trường trong danh sách')
  fireEvent.focus(input); fireEvent.keyDown(input, { key: 'Escape' })
  expect(input).toHaveAttribute('aria-expanded', 'false')
})

it('offers retry after failure and prevents submit from selection keys', async () => {
  listInstitutions.mockRejectedValueOnce(new Error('offline'))
  const submit = vi.fn(event => event.preventDefault())
  render(<form onSubmit={submit}><Form /></form>)
  const input = screen.getByRole('combobox')
  fireEvent.focus(input); await tick()
  fireEvent.click(screen.getByRole('button', { name: 'Thử lại' })); await tick()
  expect(listInstitutions).toHaveBeenCalledTimes(2)
  fireEvent.keyDown(input, { key: 'ArrowDown' }); fireEvent.keyDown(input, { key: 'Enter' })
  expect(submit).not.toHaveBeenCalled()
})
