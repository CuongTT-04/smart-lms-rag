import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import PdfViewer from './PdfViewer'
import { materialPdf, documentStatus } from '../../services/document.service'
vi.mock('../../services/document.service',()=>({materialPdf:vi.fn(),documentStatus:vi.fn()}))
vi.mock('./PdfCanvas', () => ({ default: ({url, title}) => <div title={`PDF ${title}`} data-source={url} /> }))
const row={document_id:'d',version_id:'v',published_version_id:'v',policy_revision:1,material_policy:'PROTECTED',title:'Lesson'}
it('replaces close with rename for a managed material and saves its new title', async () => {
  const rename = vi.fn(async () => {})
  render(<PdfViewer document={row} onRename={rename} onUnavailable={vi.fn()} />)
  expect(screen.queryByRole('button', { name: 'Đóng PDF' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Đổi tên' }))
  fireEvent.change(screen.getByLabelText('Tên học liệu mới'), { target: { value: 'Tên mới' } })
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Lưu tên' })))
  expect(rename).toHaveBeenCalledWith('Tên mới')
  expect(screen.queryByLabelText('Tên học liệu mới')).not.toBeInTheDocument()
})
beforeEach(()=>{
  vi.clearAllMocks();vi.useFakeTimers()
  URL.createObjectURL=vi.fn(()=> 'blob:protected-test');URL.revokeObjectURL=vi.fn()
  materialPdf.mockResolvedValue(new Blob(['pdf'],{type:'application/pdf'}))
  documentStatus.mockResolvedValue({...row})
})
afterEach(()=>vi.useRealTimers())
it('closes the viewer when a later check detects lost access and revokes the blob on unmount',async()=>{
  const unavailable=vi.fn()
  const view=render(<PdfViewer document={row} onClose={vi.fn()} onUnavailable={unavailable} />)
  await act(async()=>{await Promise.resolve();await Promise.resolve()})
  expect(screen.getByTitle('PDF Lesson')).toHaveAttribute('data-source','blob:protected-test')
  documentStatus.mockRejectedValue({status:404})
  await act(async()=>{await vi.advanceTimersByTimeAsync(2000)})
  expect(unavailable).toHaveBeenCalled()
  view.unmount();expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:protected-test')
})
it('refuses to display bytes if policy changes while the PDF is loading',async()=>{
  const unavailable=vi.fn()
  documentStatus.mockResolvedValue({...row,policy_revision:2,material_policy:'PUBLIC_DOWNLOAD'})
  render(<PdfViewer document={row} onClose={vi.fn()} onUnavailable={unavailable} />)
  await act(async()=>{await Promise.resolve();await Promise.resolve()})
  expect(unavailable).toHaveBeenCalled();expect(URL.createObjectURL).not.toHaveBeenCalled()
})

it('previews the current replacement version when the teacher is preparing publication', async () => {
  const replacement = { ...row, version_id: 'v2', published_version_id: 'v1' }
  documentStatus.mockResolvedValue(replacement)
  render(<PdfViewer document={replacement} preferCurrent onClose={vi.fn()} onUnavailable={vi.fn()} />)
  await act(async () => { await Promise.resolve(); await Promise.resolve() })
  expect(materialPdf).toHaveBeenCalledWith('d', false, expect.any(AbortSignal), 'v2')
  expect(documentStatus).toHaveBeenCalledWith('d', 'v2', expect.any(AbortSignal))
  expect(screen.getByTitle('PDF Lesson')).toBeVisible()
})
