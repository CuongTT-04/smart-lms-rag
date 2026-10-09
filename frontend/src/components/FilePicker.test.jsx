import { expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import FilePicker from './FilePicker'

it('uses the native accessible picker and displays the selected filename', async () => {
  const changed = vi.fn()
  const view = render(<FilePicker label="Tài liệu PDF" accept=".pdf" file={null} onChange={changed} />)
  expect(screen.getByText('Chọn tệp')).toBeVisible()
  const file = new File(['pdf'], 'Bài học.pdf', { type: 'application/pdf' })
  await userEvent.upload(screen.getByLabelText('Tài liệu PDF'), file)
  expect(changed.mock.calls[0][0].target.files[0]).toBe(file)
  view.rerender(<FilePicker label="Tài liệu PDF" accept=".pdf" file={file} onChange={changed} />)
  expect(screen.getByText('Bài học.pdf')).toBeVisible()
  view.rerender(<FilePicker label="Tài liệu PDF" accept=".pdf" file={null} onChange={changed} disabled />)
  expect(screen.getByLabelText('Tài liệu PDF')).toBeDisabled()
  expect(screen.getByLabelText('Tài liệu PDF').files).toHaveLength(0)
})
