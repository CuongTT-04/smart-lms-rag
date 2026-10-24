import { render, screen } from '@testing-library/react'
import { it, expect, vi, beforeEach } from 'vitest'
import CitationViewer from './CitationViewer'
import { documentStatus } from '../../services/document.service'
vi.mock('../../services/document.service', () => ({documentStatus:vi.fn()}))
vi.mock('../documents/PdfViewer', () => ({default:({initialPage,expectedVersionId}) => <div>PDF {expectedVersionId} trang {initialPage}</div>}))
const citation={document_id:'d1',version_id:'v1',page_number:3,document_title:'Tài liệu'}
beforeEach(() => documentStatus.mockResolvedValue({document_id:'d1',version_id:'v1',published_version_id:'v1',page_count:5}))
it('opens the exact cited version and page',async () => {
  render(<CitationViewer citation={citation} onClose={vi.fn()} />)
  expect(await screen.findByText('PDF v1 trang 3')).toBeVisible()
})
it.each([{published_version_id:'v2'}, {page_count:2}])('rejects changed versions and out of range pages: %j',async (change) => {
  documentStatus.mockResolvedValue({document_id:'d1',version_id:'v1',published_version_id:'v1',page_count:5,...change})
  render(<CitationViewer citation={citation} onClose={vi.fn()} />)
  expect(await screen.findByRole('alert')).toHaveTextContent('Nguồn trích dẫn không còn khả dụng')
  expect(screen.queryByText('PDF v1 trang 3')).not.toBeInTheDocument()
})
