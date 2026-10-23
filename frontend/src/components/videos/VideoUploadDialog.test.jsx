import { expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import VideoUploadDialog from './VideoUploadDialog'

it('releases metadata readers after success and when closing before metadata arrives', async () => {
  vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(() => {})
  URL.createObjectURL = vi.fn(() => 'blob:metadata')
  URL.revokeObjectURL = vi.fn()
  const create = document.createElement.bind(document)
  let reader
  vi.spyOn(document, 'createElement').mockImplementation((tag, options) => {
    const element = create(tag, options)
    if (tag === 'video') reader = element
    return element
  })
  const { unmount } = render(<VideoUploadDialog onSave={vi.fn()} onClose={vi.fn()} />)
  fireEvent.change(screen.getByLabelText('Tệp video'), { target: { files: [new File(['video'], 'lesson.mp4', { type: 'video/mp4' })] } })
  Object.defineProperty(reader, 'duration', { value: 30 })
  await act(async () => reader.onloadedmetadata())
  expect(reader.onloadedmetadata).toBeNull()
  expect(reader.onerror).toBeNull()
  expect(URL.revokeObjectURL).toHaveBeenCalledTimes(1)
  fireEvent.change(screen.getByLabelText('Tệp video'), { target: { files: [new File(['video'], 'other.mp4', { type: 'video/mp4' })] } })
  unmount()
  expect(reader.onloadedmetadata).toBeNull()
  expect(URL.revokeObjectURL).toHaveBeenCalledTimes(2)
})
