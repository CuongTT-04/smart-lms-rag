import { beforeEach, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import PdfCanvas from './PdfCanvas'
import { getDocument } from 'pdfjs-dist'
const page = { getViewport: vi.fn(({ scale }) => ({ width: 600 * scale, height: 900 * scale })), render: vi.fn(() => ({ promise: Promise.resolve(), cancel: vi.fn() })) }
vi.mock('pdfjs-dist', () => ({ GlobalWorkerOptions: {}, getDocument: vi.fn() }))
beforeEach(() => {
  vi.clearAllMocks()
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({})
  vi.stubGlobal('ResizeObserver', class { constructor(callback) { this.callback = callback } observe() { this.callback([{ contentRect: { width: 800, height: 600 } }]) } disconnect() {} })
  getDocument.mockReturnValue({ promise: Promise.resolve({ numPages: 2, getPage: vi.fn(async () => page) }), destroy: vi.fn() })
})
it('fits a portrait page inside the viewport and provides zoom, fit and page controls', async () => {
  render(<PdfCanvas url="blob:test" title="Lesson" />)
  await waitFor(() => expect(page.render).toHaveBeenCalled())
  const viewport = page.render.mock.calls.at(-1)[0].viewport
  expect(viewport.height).toBeLessThanOrEqual(568)
  expect(viewport.width).toBeLessThanOrEqual(768)
  expect(screen.getByLabelText('Trang PDF hiện tại')).toHaveTextContent('1 / 2')
  // page.render can run before React commits the fitted scale to the slider.
  await waitFor(() => expect(Number(screen.getByRole('slider', { name: 'Thu phóng tài liệu' }).value)).toBeCloseTo(568 / 900))
  const before = screen.getByRole('slider', { name: 'Thu phóng tài liệu' }).value
  await userEvent.click(screen.getByRole('button', { name: 'Phóng to tài liệu' }))
  await waitFor(() => expect(screen.getByRole('slider', { name: 'Thu phóng tài liệu' }).value).not.toBe(before))
  await userEvent.click(screen.getByRole('button', { name: 'Mặc định' }))
  await waitFor(() => expect(screen.getByRole('slider', { name: 'Thu phóng tài liệu' }).value).toBe(before))
  fireEvent.change(screen.getByRole('slider', { name: 'Thu phóng tài liệu' }), { target: { value: '1.2' } })
  await waitFor(() => expect(screen.getByRole('slider', { name: 'Thu phóng tài liệu' }).value).not.toBe(before))
  await userEvent.click(screen.getByRole('button', { name: 'Trang sau' }))
  expect(screen.getByLabelText('Trang PDF hiện tại')).toHaveTextContent('2 / 2')
  expect(screen.getByRole('button', { name: 'Trang sau' })).toBeDisabled()
})
