import { beforeEach, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import MaterialActions from './MaterialActions'
import { publishDocument, changeMaterialPolicy, removeDocument, replaceDocument } from '../../services/document.service'
vi.mock('../../services/document.service',()=>({publishDocument:vi.fn(),changeMaterialPolicy:vi.fn(),removeDocument:vi.fn(),replaceDocument:vi.fn(),materialPdf:vi.fn(),documentStatus:vi.fn()}))
const row={document_id:'d',version_id:'v',title:'Lesson',extraction_status:'EXTRACTED',watermark_status:'READY',material_policy:'PROTECTED',policy_revision:1,is_published:false}
beforeEach(()=>vi.clearAllMocks())
it('publishes the selected extracted version',async()=>{
  publishDocument.mockResolvedValue({document_id:'d',is_published:true})
  render(<MaterialActions document={row} canManage onUpdated={vi.fn()} onRemoved={vi.fn()} />)
  await userEvent.click(screen.getByRole('button',{name:'Công bố phiên bản này'}))
  expect(publishDocument).toHaveBeenCalledWith('d','v',true)
})
it('changes policy only through the material setting with its revision',async()=>{
  changeMaterialPolicy.mockResolvedValue({document_id:'d',material_policy:'PUBLIC_DOWNLOAD',policy_revision:2})
  render(<MaterialActions document={row} canManage onUpdated={vi.fn()} onRemoved={vi.fn()} />)
  await userEvent.click(screen.getByRole('button',{name:'Cho phép tải bản sạch'}))
  expect(changeMaterialPolicy).toHaveBeenCalledWith('d','PUBLIC_DOWNLOAD',1)
  expect(screen.getByRole('button',{name:'Tải PDF'})).toBeInTheDocument()
})
it('does not expose management or download controls to protected students',()=>{
  render(<MaterialActions document={{...row,is_published:true}} onUpdated={vi.fn()} onRemoved={vi.fn()} />)
  expect(screen.queryByRole('button',{name:'Gỡ học liệu'})).not.toBeInTheDocument()
  expect(screen.queryByRole('button',{name:'Cho phép tải bản sạch'})).not.toBeInTheDocument()
  expect(screen.queryByRole('button',{name:'Tải PDF'})).not.toBeInTheDocument()
})
it('requires a modal removal confirmation and then informs the parent',async()=>{
  const removed=vi.fn();removeDocument.mockResolvedValue(null)
  render(<MaterialActions document={row} canManage onUpdated={vi.fn()} onRemoved={removed} />)
  await userEvent.click(screen.getByRole('button',{name:'Gỡ học liệu'}))
  const dialog = screen.getByRole('dialog', { name: 'Gỡ học liệu?' })
  expect(dialog).toHaveAttribute('aria-modal', 'true')
  expect(within(dialog).getByRole('button', { name: 'Hủy' })).toHaveFocus()
  expect(removeDocument).not.toHaveBeenCalled()
  await userEvent.click(screen.getByRole('button',{name:'Xác nhận gỡ'}))
  expect(removeDocument).toHaveBeenCalledWith('d');expect(removed).toHaveBeenCalledWith('d')
})
it('cancels removal with Escape and restores focus without removing anything', async () => {
  render(<MaterialActions document={row} canManage onUpdated={vi.fn()} onRemoved={vi.fn()} />)
  const trigger = screen.getByRole('button', { name: 'Gỡ học liệu' })
  expect(trigger).toHaveClass('material-danger-button')
  await userEvent.click(trigger)
  await userEvent.keyboard('{Escape}')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(trigger).toHaveFocus()
  expect(removeDocument).not.toHaveBeenCalled()
})
it('keeps the dialog open with a visible error if removal fails', async () => {
  removeDocument.mockRejectedValueOnce({ status: 500 })
  render(<MaterialActions document={row} canManage onUpdated={vi.fn()} onRemoved={vi.fn()} />)
  await userEvent.click(screen.getByRole('button', { name: 'Gỡ học liệu' }))
  await userEvent.click(screen.getByRole('button', { name: 'Xác nhận gỡ' }))
  const dialog = screen.getByRole('dialog')
  expect(await within(dialog).findByRole('alert')).toBeVisible()
  expect(within(dialog).getByRole('button', { name: 'Xác nhận gỡ' })).toBeEnabled()
})
it('keeps the replacement key after an uncertain network result',async()=>{
  replaceDocument.mockRejectedValueOnce({status:0}).mockResolvedValueOnce({document_id:'d',version_id:'v2',extraction_status:'QUEUED'})
  render(<MaterialActions document={row} canManage onUpdated={vi.fn()} onRemoved={vi.fn()} />)
  await userEvent.upload(screen.getByLabelText('PDF thay thế cho Lesson'),new File(['pdf'],'new.pdf',{type:'application/pdf'}))
  await userEvent.click(screen.getByRole('button',{name:'Thay bằng PDF này'}));await screen.findByRole('alert')
  await userEvent.click(screen.getByRole('button',{name:'Thay bằng PDF này'}))
  expect(replaceDocument.mock.calls[0][2]).toBe(replaceDocument.mock.calls[1][2])
})

it('shows only revoke for the published current version', async () => {
  render(<MaterialActions document={{...row,is_published:true,published_version_id:'v'}} canManage onUpdated={vi.fn()} onRemoved={vi.fn()} />)
  expect(screen.queryByRole('button',{name:'Công bố phiên bản này'})).not.toBeInTheDocument()
  publishDocument.mockResolvedValue({document_id:'d',is_published:false})
  await userEvent.click(screen.getByRole('button',{name:'Thu hồi công bố'}))
  expect(publishDocument).toHaveBeenCalledWith('d',null,false)
})
it('can publish a replacement without showing both publication actions', () => {
  render(<MaterialActions document={{...row,is_published:true,published_version_id:'old'}} canManage onUpdated={vi.fn()} onRemoved={vi.fn()} />)
  expect(screen.getByRole('button',{name:'Công bố phiên bản này'})).toBeEnabled()
  expect(screen.queryByRole('button',{name:'Thu hồi công bố'})).not.toBeInTheDocument()
})
it('allows teacher downloads immediately after upload while processing', () => {
  render(<MaterialActions document={{...row,extraction_status:'QUEUED',watermark_status:'NOT_STARTED'}} canManage />)
  expect(screen.getByRole('button',{name:'Tải PDF'})).toBeEnabled()
})
it('offers a compact student download only for published permitted documents', () => {
  const {rerender}=render(<MaterialActions document={{...row,is_published:true,material_policy:'PUBLIC_DOWNLOAD'}} downloadOnly />)
  expect(screen.getByRole('button',{name:'Tải PDF'})).toBeEnabled()
  expect(screen.queryByRole('button',{name:'Xem PDF'})).not.toBeInTheDocument()
  rerender(<MaterialActions document={{...row,is_published:true}} downloadOnly />)
  expect(screen.queryByRole('button',{name:'Tải PDF'})).not.toBeInTheDocument()
})
