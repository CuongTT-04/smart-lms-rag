import { expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import SessionWorkspace from './SessionWorkspace'
import { listDocuments, uploadDocument, renameDocument } from '../services/document.service'

vi.mock('../services/document.service', async (original) => ({ ...await original(), listDocuments: vi.fn(), uploadDocument: vi.fn(), renameDocument: vi.fn() }))
vi.mock('./documents/PdfViewer', () => ({ default: ({ document, onRename }) => <div>Preview {document.title}<button onClick={() => onRename('Tên đã đổi')}>Test rename</button></div> }))
vi.mock('./documents/MaterialActions', () => ({ default: () => null }))
const older = { document_id: 'old', version_id: 'v1', title: 'Học liệu cũ', extraction_status: 'EXTRACTED', watermark_status: 'READY' }
const newer = { ...older, document_id: 'new', version_id: 'v2', title: 'Học liệu mới' }
function open() {
  listDocuments.mockResolvedValue([newer, older])
  render(<SessionWorkspace course={{ id: 'c1' }} room={{ id: 'r1' }} session={{ id: 's1', title: '' }} />)
}
it('updates the selected material title in its preview and sidebar after server rename', async () => {
  open()
  await screen.findByText('Preview Học liệu cũ')
  renameDocument.mockResolvedValueOnce({ document_id: 'old', title: 'Tên đã đổi' })
  await userEvent.click(screen.getByRole('button', { name: 'Test rename' }))
  expect(await screen.findByRole('button', { name: 'Tên đã đổi' })).toBeVisible()
  expect(screen.getByText('Preview Tên đã đổi')).toBeVisible()
  expect(renameDocument).toHaveBeenCalledWith('old', 'Tên đã đổi')
})
it('appends a blank card, uploads one PDF and hides its form without reordering existing cards', async () => {
  open()
  const nav = screen.getByRole('navigation', { name: 'Nội dung buổi học' })
  await screen.findByRole('button', { name: 'Học liệu cũ' })
  expect(within(nav).getAllByRole('button').filter((b) => b.querySelector('span')).map((b) => b.textContent)).toEqual(['Học liệu cũ', 'Học liệu mới'])
  expect(screen.queryByRole('button', { name: 'Tải tài liệu lên' })).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Thêm học liệu' }))
  expect(within(nav).getAllByRole('button').filter((b) => b.querySelector('span')).at(-1)).toHaveTextContent('Học liệu chưa đặt tên')
  await userEvent.type(screen.getByLabelText('Tên học liệu'), 'PDF thứ ba')
  fireEvent.change(screen.getByLabelText('Tài liệu PDF'), { target: { files: [new File(['pdf'], 'third.pdf', { type: 'application/pdf' })] } })
  uploadDocument.mockResolvedValueOnce({ ...older, document_id: 'third', version_id: 'v3', title: 'PDF thứ ba' })
  await userEvent.click(screen.getByRole('button', { name: 'Tải tài liệu lên' }))
  await screen.findByText('Preview PDF thứ ba')
  expect(screen.queryByLabelText('Tài liệu PDF')).not.toBeInTheDocument()
  expect(within(nav).getAllByRole('button').filter((b) => b.querySelector('span')).map((b) => b.textContent)).toEqual(['Học liệu cũ', 'Học liệu mới', 'PDF thứ ba'])
  listDocuments.mockResolvedValueOnce([{ ...older, document_id: 'third', title: 'PDF thứ ba' }, newer, older])
  await userEvent.click(screen.getByRole('button', { name: 'Làm mới danh sách' }))
  await waitFor(() => expect(within(nav).getAllByRole('button').filter((b) => b.querySelector('span')).map((b) => b.textContent)).toEqual(['Học liệu cũ', 'Học liệu mới', 'PDF thứ ba']))
  await userEvent.click(screen.getByRole('button', { name: 'Học liệu cũ' }))
  expect(await screen.findByText('Preview Học liệu cũ')).toBeVisible()
  expect(screen.queryByText('Preview PDF thứ ba')).not.toBeInTheDocument()
})
it('keeps a failed draft and retries with the same upload key', async () => {
  open()
  await screen.findByRole('button', { name: 'Học liệu cũ' })
  await userEvent.click(screen.getByRole('button', { name: 'Thêm học liệu' }))
  await userEvent.type(screen.getByLabelText('Tên học liệu'), 'Retry draft')
  fireEvent.change(screen.getByLabelText('Tài liệu PDF'), { target: { files: [new File(['pdf'], 'retry.pdf')] } })
  uploadDocument.mockRejectedValueOnce({ status: 500 })
  await userEvent.click(screen.getByRole('button', { name: 'Tải tài liệu lên' }))
  expect(await screen.findByRole('alert')).toBeVisible()
  const previous = uploadDocument.mock.calls.at(-1)
  expect(screen.getByLabelText('Tên học liệu')).toHaveValue('Retry draft')
  uploadDocument.mockResolvedValueOnce({ ...older, document_id: 'retried', title: 'Retry draft' })
  await userEvent.click(screen.getByRole('button', { name: 'Tải tài liệu lên' }))
  await screen.findByText('Preview Retry draft')
  expect(uploadDocument.mock.calls.at(-1)[3]).toBe(previous[3])
  expect(screen.queryByRole('button', { name: 'Học liệu chưa đặt tên' })).not.toBeInTheDocument()
})
it('keeps drafts separate and assigns a pending upload to its original card', async () => {
  open()
  await screen.findByRole('button', { name: 'Học liệu cũ' })
  await userEvent.click(screen.getByRole('button', { name: 'Thêm học liệu' }))
  await userEvent.type(screen.getByLabelText('Tên học liệu'), 'Draft A')
  fireEvent.change(screen.getByLabelText('Tài liệu PDF'), { target: { files: [new File(['pdf'], 'a.pdf')] } })
  let finish
  uploadDocument.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
  await userEvent.click(screen.getByRole('button', { name: 'Tải tài liệu lên' }))
  await userEvent.click(screen.getByRole('button', { name: 'Thêm học liệu' }))
  expect(screen.getByLabelText('Tên học liệu')).toHaveValue('')
  await act(async () => finish({ ...older, document_id: 'a', title: 'Draft A' }))
  expect(screen.getByLabelText('Tên học liệu')).toHaveValue('')
  expect(screen.queryByText('Preview Draft A')).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Draft A' }))
  expect(await screen.findByText('Preview Draft A')).toBeVisible()
})
it('toggles every sidebar category and its expanded state', async () => {
  open()
  for (const name of ['Bài học', 'Video', 'Bài tập']) {
    const button = screen.getByRole('button', { name, exact: true })
    const initiallyOpen = button.getAttribute('aria-expanded') === 'true'
    await userEvent.click(button)
    expect(button).toHaveAttribute('aria-expanded', String(!initiallyOpen))
    expect(button.querySelector(initiallyOpen ? '.lucide-chevron-right' : '.lucide-chevron-down')).toBeInTheDocument()
    await userEvent.click(button)
    await waitFor(() => expect(button).toHaveAttribute('aria-expanded', String(initiallyOpen)))
  }
})
