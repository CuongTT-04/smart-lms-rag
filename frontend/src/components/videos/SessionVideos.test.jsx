import { useState } from 'react'
import { beforeEach, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import SessionVideos from './SessionVideos'
import { getSessionVideo, getVideoFile } from '../../services/video.service'

vi.mock('../../services/video.service', () => ({ getSessionVideo: vi.fn(), getVideoFile: vi.fn() }))
vi.mock('./InteractiveVideoPlayer', () => ({ default: () => <div>Trình phát đã sẵn sàng</div> }))
const info = { id: 'v1', title: 'Video mẫu', duration: 60, questions: [], is_published: true, progress: { position: 0, passed_ids: [] } }
beforeEach(() => {
  vi.clearAllMocks()
  URL.createObjectURL = vi.fn(() => 'blob:video')
  URL.revokeObjectURL = vi.fn()
  getSessionVideo.mockResolvedValue(info)
})
it('shares the upload dialog state with its parent and can close and reopen it', async () => {
  function Panel() {
    const [uploading, setUploading] = useState(true)
    return <><button onClick={() => setUploading(true)}>Mở tải video từ sidebar</button><SessionVideos path="/videos/" rows={[]} canManage uploading={uploading} onUploadingChange={setUploading} onRefresh={vi.fn()} onSelect={vi.fn()} /></>
  }
  render(<Panel />)
  expect(screen.getByRole('dialog')).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Hủy', exact: true }))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Thêm video', exact: true })).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Mở tải video từ sidebar', exact: true }))
  expect(screen.getByRole('dialog')).toBeVisible()
})
it('retries a failed video file request with Refresh and keeps its error until retry', async () => {
  getVideoFile.mockRejectedValueOnce(new Error('Mất kết nối')).mockResolvedValueOnce(new Blob(['video']))
  render(<SessionVideos path="/videos/" rows={[info]} selectedId="v1" canManage={false} onRefresh={vi.fn()} onSelect={vi.fn()} />)
  await screen.findByRole('alert')
  await userEvent.click(screen.getByRole('button', { name: 'Làm mới video' }))
  await waitFor(() => expect(getVideoFile).toHaveBeenCalledTimes(2))
  expect(await screen.findByText('Trình phát đã sẵn sàng')).toBeVisible()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})
