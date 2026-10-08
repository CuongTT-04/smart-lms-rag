import { describe, it, expect, vi, beforeEach } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
vi.mock('../../services/document.service', () => ({ listDocuments:vi.fn(), uploadDocument:vi.fn(), documentStatus:vi.fn(), retryDocument:vi.fn(), documentExtraction:vi.fn() }))
import { listDocuments, uploadDocument, retryDocument, documentStatus, documentExtraction } from '../../services/document.service'
import CourseDocuments from './CourseDocuments'

describe('course materials', () => {
  beforeEach(() => { vi.clearAllMocks();listDocuments.mockResolvedValue([]) })
  it('ignores a status response carrying a different version identity', async () => {
    vi.useFakeTimers()
    try {
      listDocuments.mockResolvedValue([{document_id:'d1',version_id:'v2',title:'Lesson',file_name:'new.pdf',extraction_status:'QUEUED'}])
      documentStatus.mockResolvedValue({document_id:'d1',version_id:'v1',file_name:'old.pdf',extraction_status:'FAILED'})
      render(<CourseDocuments courseId="course" canManage />)
      await act(async () => { await Promise.resolve() })
      await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
      expect(screen.getByText('new.pdf')).toBeVisible()
      expect(screen.getByText('Đang chờ xử lý')).toBeVisible()
    } finally { vi.useRealTimers() }
  })
  it('does not overwrite a refreshed version with an outstanding old status', async () => {
    vi.useFakeTimers()
    try {
      let resolveRefresh, resolveOldStatus
      listDocuments.mockResolvedValueOnce([{document_id:'d1',version_id:'v1',title:'Lesson',file_name:'old.pdf',extraction_status:'QUEUED'}])
        .mockImplementationOnce(() => new Promise((resolve) => { resolveRefresh=resolve }))
      documentStatus.mockImplementationOnce(() => new Promise((resolve) => { resolveOldStatus=resolve }))
      render(<CourseDocuments courseId="course" canManage />)
      await act(async () => { await Promise.resolve() })
      await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
      await act(async () => {
        fireEvent.click(screen.getByRole('button',{name:'Làm mới danh sách'}))
        resolveRefresh([{document_id:'d1',version_id:'v2',title:'Lesson',file_name:'new.pdf',extraction_status:'EXTRACTED'}])
        resolveOldStatus({document_id:'d1',version_id:'v1',file_name:'old.pdf',extraction_status:'EXTRACTED'})
      })
      expect(screen.getByText('new.pdf')).toBeVisible()
      expect(screen.queryByText('old.pdf')).not.toBeInTheDocument()
    } finally { vi.useRealTimers() }
  })
  it('lets the owner inspect extraction with physical page numbers', async () => {
    listDocuments.mockResolvedValue([{document_id:'d1',version_id:'v1',title:'Lesson',extraction_status:'EXTRACTED'}])
    documentExtraction.mockResolvedValue({pages:[{page_number:1,text:'Nội dung trang một'},{page_number:2,text:'Nội dung trang hai'}]})
    render(<CourseDocuments courseId="course" canManage />)
    await userEvent.click(await screen.findByRole('button',{name:'Kiểm tra trích xuất'}))
    expect(documentExtraction).toHaveBeenCalledWith('d1','v1')
    expect(await screen.findByText('Nội dung trang hai')).toBeVisible()
    expect(screen.getByText('Trang PDF 2')).toBeVisible()
  })
  it('clears inspected text and metadata when a refresh detects revoked access', async () => {
    listDocuments.mockResolvedValueOnce([{document_id:'d1',version_id:'v1',title:'Lesson',extraction_status:'EXTRACTED'}]).mockRejectedValueOnce({status:404})
    documentExtraction.mockResolvedValue({pages:[{page_number:1,text:'Private extracted text'}]})
    render(<CourseDocuments courseId="course" canManage />)
    await userEvent.click(await screen.findByRole('button',{name:'Kiểm tra trích xuất'}))
    await screen.findByText('Private extracted text')
    await userEvent.click(screen.getByRole('button',{name:'Làm mới danh sách'}))
    await screen.findByRole('alert')
    expect(screen.queryByText('Private extracted text')).not.toBeInTheDocument()
    expect(screen.queryByText('Lesson')).not.toBeInTheDocument()
  })
  it('uploads a PDF and displays queued status without claiming RAG is ready', async () => {
    uploadDocument.mockResolvedValue({ document_id:'d1', version_id:'v1', extraction_status:'QUEUED' })
    render(<CourseDocuments courseId="course" canManage />)
    await screen.findByText('Chưa có học liệu.')
    await userEvent.upload(screen.getByLabelText('Tài liệu PDF'),new File(['pdf'],'sample.pdf',{type:'application/pdf'}))
    await userEvent.click(screen.getByRole('button',{name:'Tải tài liệu lên'}))
    await waitFor(() => expect(uploadDocument).toHaveBeenCalled())
    expect(await screen.findByText('Đang chờ xử lý')).toBeVisible()
    expect(screen.queryByText('RAG sẵn sàng')).not.toBeInTheDocument()
  })
  it('keeps the upload key when a network error leaves the result uncertain', async () => {
    uploadDocument.mockRejectedValueOnce({status:0}).mockResolvedValueOnce({document_id:'d1',version_id:'v1',extraction_status:'EXTRACTED'})
    render(<CourseDocuments courseId="course" canManage />)
    await screen.findByText('Chưa có học liệu.')
    await userEvent.upload(screen.getByLabelText('Tài liệu PDF'),new File(['pdf'],'sample.pdf',{type:'application/pdf'}))
    await userEvent.click(screen.getByRole('button',{name:'Tải tài liệu lên'}))
    await screen.findByRole('alert')
    await userEvent.click(screen.getByRole('button',{name:'Tải tài liệu lên'}))
    await waitFor(() => expect(uploadDocument).toHaveBeenCalledTimes(2))
    expect(uploadDocument.mock.calls[0][3]).toBe(uploadDocument.mock.calls[1][3])
  })
  it('allows teacher retry for failed extraction using its version', async () => {
    listDocuments.mockResolvedValue([{document_id:'d1',version_id:'v1',title:'Lesson',extraction_status:'FAILED',error_code:'OCR_REQUIRED'}])
    retryDocument.mockResolvedValue({document_id:'d1',version_id:'v1',extraction_status:'QUEUED'})
    render(<CourseDocuments courseId="course" canManage />)
    await userEvent.click(await screen.findByRole('button',{name:'Thử xử lý lại'}))
    expect(retryDocument).toHaveBeenCalledWith('d1','v1',expect.any(String))
  })
  it('shows metadata to students without upload or clean download controls', async () => {
    listDocuments.mockResolvedValue([{document_id:'d1',title:'Lesson',extraction_status:'EXTRACTED',page_count:3}])
    render(<CourseDocuments courseId="course" />)
    expect(await screen.findByText('Lesson')).toBeVisible()
    expect(screen.queryByLabelText('Tài liệu PDF')).not.toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })
  it('stops polling after extraction finishes and on unmount', async () => {
    vi.useFakeTimers()
    try {
      listDocuments.mockResolvedValue([{document_id:'d1',version_id:'v1',title:'Lesson',extraction_status:'QUEUED'}])
      documentStatus.mockResolvedValue({document_id:'d1',version_id:'v1',extraction_status:'EXTRACTED'})
      const view=render(<CourseDocuments courseId="course" canManage />)
      await act(async () => { await Promise.resolve() })
      await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
      expect(screen.getByText('Đã trích xuất')).toBeVisible()
      await act(async () => { await vi.advanceTimersByTimeAsync(6000) })
      expect(documentStatus).toHaveBeenCalledTimes(1)
      view.unmount()
      await vi.advanceTimersByTimeAsync(6000)
      expect(documentStatus).toHaveBeenCalledTimes(1)
    } finally { vi.useRealTimers() }
  })
  it('clears cached metadata when access is revoked during polling', async () => {
    vi.useFakeTimers()
    try {
      listDocuments.mockResolvedValue([{document_id:'d1',version_id:'v1',title:'Private Lesson',extraction_status:'QUEUED'}])
      documentStatus.mockRejectedValue({status:404})
      render(<CourseDocuments courseId="course" />)
      await act(async () => { await Promise.resolve() })
      await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
      expect(screen.queryByText('Private Lesson')).not.toBeInTheDocument()
      expect(screen.getByRole('alert')).toHaveTextContent('không có quyền')
    } finally { vi.useRealTimers() }
  })

  it('blocks upload while initial metadata is loading to avoid a late list overwriting it', async () => {
    let resolveList
    listDocuments.mockReturnValue(new Promise((resolve) => { resolveList=resolve }))
    render(<CourseDocuments courseId="course" canManage />)
    expect(screen.getByRole('button',{name:'Tải tài liệu lên'})).toBeDisabled()
    expect(screen.getByLabelText('Tài liệu PDF')).toBeDisabled()
    await act(async () => { resolveList([]) })
    expect(screen.getByRole('button',{name:'Tải tài liệu lên'})).toBeEnabled()
  })

})
