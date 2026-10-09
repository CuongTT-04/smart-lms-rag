import { expect, it, vi } from 'vitest'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import CourseDocuments from './CourseDocuments'
import { documentExtraction, listDocuments } from '../../services/document.service'
vi.mock('../../services/document.service', async (original) => ({ ...await original(), listDocuments: vi.fn(async () => []), documentExtraction: vi.fn() }))
it('retains the session filter when refreshing materials', async () => {
  render(<CourseDocuments courseId="c1" sessionId="s1" />)
  await waitFor(() => expect(listDocuments).toHaveBeenCalledWith('c1', expect.any(AbortSignal), 's1'))
  await userEvent.click(screen.getByRole('button', { name: 'Làm mới danh sách' }))
  await waitFor(() => expect(listDocuments).toHaveBeenLastCalledWith('c1', undefined, 's1'))
})

vi.mock('./PdfViewer', () => ({ default: () => <div>Bản xem PDF</div> }))
it('does not display late extraction results under a different selected material', async () => {
  const rows = ['d1', 'd2'].map((id) => ({ document_id: id, version_id: id, title: id, extraction_status: 'EXTRACTED', watermark_status: 'READY' }))
  listDocuments.mockResolvedValueOnce(rows)
  let finish
  documentExtraction.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
  const view = render(<CourseDocuments courseId="c1" sessionId="s1" workspace canManage selectedDocumentId="d1" />)
  await userEvent.click(await screen.findByRole('button', { name: 'Kiểm tra trích xuất' }))
  view.rerender(<CourseDocuments courseId="c1" sessionId="s1" workspace canManage selectedDocumentId="d2" />)
  await act(async () => finish({ pages: [{ page_number: 1, text: 'Text from d1' }] }))
  expect(screen.queryByText('Text from d1')).not.toBeInTheDocument()
  expect(screen.queryByRole('region', { name: 'Kết quả trích xuất' })).not.toBeInTheDocument()
})

it('waits for the replacement view to be ready despite an older published version', async () => {
  const queued = { document_id: 'd1', version_id: 'v2', published_version_id: 'v1', title: 'Replacement', is_published: true, extraction_status: 'QUEUED', watermark_status: 'NOT_STARTED' }
  listDocuments.mockResolvedValueOnce([queued]).mockResolvedValueOnce([{ ...queued, extraction_status: 'EXTRACTED', watermark_status: 'READY' }])
  render(<CourseDocuments courseId="c1" sessionId="s1" workspace canManage selectedDocumentId="d1" />)
  await screen.findByRole('heading', { name: 'Replacement' })
  expect(screen.queryByText('Bản xem PDF')).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Làm mới danh sách' }))
  expect(await screen.findByText('Bản xem PDF')).toBeVisible()
})
