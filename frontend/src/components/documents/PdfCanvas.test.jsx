import { beforeEach, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import PdfCanvas from './PdfCanvas'
import { getDocument, TextLayer } from 'pdfjs-dist'
const page = { getTextContent: vi.fn(async () => ({items:[],styles:{}})), getViewport: vi.fn(({ scale }) => ({ width: 600 * scale, height: 900 * scale })), render: vi.fn(() => ({ promise: Promise.resolve(), cancel: vi.fn() })) }
vi.mock('../../services/document.service', () => ({ readStudyNotes: vi.fn(async () => ({items:[],notes:''})), writeStudyNotes: vi.fn(async () => {}) }))
vi.mock('pdfjs-dist', () => ({ GlobalWorkerOptions: {}, getDocument: vi.fn(), TextLayer: vi.fn(class { constructor({container}) { this.container=container } render() { this.container.textContent='Selectable PDF text';return Promise.resolve() } cancel() {} }) }))
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
it('zooms with the wheel only inside the PDF, prevents page scrolling and respects zoom limits', async () => {
  render(<PdfCanvas url="blob:test" title="Lesson" />)
  const slider = screen.getByRole('slider', { name: 'Thu phóng tài liệu' })
  await waitFor(() => expect(Number(slider.value)).toBeCloseTo(568 / 900))
  const initial = Number(slider.value)
  const viewport = screen.getByLabelText('PDF Lesson')
  expect(fireEvent.wheel(viewport, { deltaY: -100, cancelable: true })).toBe(false)
  await waitFor(() => expect(Number(slider.value)).toBeGreaterThan(initial))
  fireEvent.wheel(viewport, { deltaY: 100, cancelable: true })
  await waitFor(() => expect(Number(slider.value)).toBeCloseTo(initial))
  expect(fireEvent.wheel(document.body, { deltaY: -100, cancelable: true })).toBe(true)
  expect(Number(slider.value)).toBeCloseTo(initial)
  fireEvent.change(slider, { target: { value: '4' } })
  await waitFor(() => expect(Number(slider.value)).toBe(4))
  fireEvent.wheel(viewport, { deltaY: -100, cancelable: true })
  expect(Number(slider.value)).toBe(4)
  fireEvent.change(slider, { target: { value: '0.05' } })
  await waitFor(() => expect(Number(slider.value)).toBe(0.05))
  fireEvent.wheel(viewport, { deltaY: 100, cancelable: true })
  expect(Number(slider.value)).toBe(0.05)
})

it('renders a text selection layer at the page scale and blocks protected copy without disabling selection', async () => {
  const {rerender}=render(<PdfCanvas url="blob:test" title="Lesson" />)
  const text=await screen.findByText('Selectable PDF text')
  expect(TextLayer).toHaveBeenCalledWith(expect.objectContaining({container:text,viewport:expect.objectContaining({width:expect.any(Number)})}))
  const selection=window.getSelection(), range=document.createRange()
  range.selectNodeContents(text);selection.removeAllRanges();selection.addRange(range)
  const clipboardData={setData:vi.fn()}
  expect(fireEvent.copy(document,{clipboardData,cancelable:true})).toBe(false)
  expect(selection.toString()).toBe('Selectable PDF text')
  rerender(<PdfCanvas url="blob:test" title="Lesson" allowCopy />)
  expect(fireEvent.copy(document,{clipboardData,cancelable:true})).toBe(true)
  selection.removeAllRanges()
  expect(fireEvent.copy(document,{clipboardData,cancelable:true})).toBe(true)
})

it('pans in hand mode without drawing and restores selection in pointer mode', async () => {
  vi.stubGlobal('PointerEvent', MouseEvent)
  render(<PdfCanvas url="blob:test" title="Lesson" annotatable documentId="d" versionId="v" />)
  const hand=screen.getByRole('button',{name:'Bàn tay'})
  await waitFor(()=>expect(hand).toBeEnabled())
  const viewport=screen.getByLabelText('PDF Lesson')
  viewport.scrollLeft=150;viewport.scrollTop=200
  await userEvent.click(hand)
  fireEvent.pointerDown(viewport,{button:0,clientX:100,clientY:100})
  expect(viewport).toHaveClass('is-dragging')
  fireEvent.pointerMove(viewport,{clientX:140,clientY:160})
  expect(viewport.scrollLeft).toBe(110)
  expect(viewport.scrollTop).toBe(140)
  fireEvent.pointerUp(viewport)
  expect(viewport).not.toHaveClass('is-dragging')
  await userEvent.click(screen.getByRole('button',{name:'Con trỏ'}))
  expect(screen.getByLabelText('Văn bản PDF').style.pointerEvents).toBe('auto')
  fireEvent.pointerDown(viewport,{button:0,clientX:100,clientY:100})
  fireEvent.pointerMove(viewport,{clientX:200,clientY:200})
  expect(viewport.scrollLeft).toBe(110)
  vi.unstubAllGlobals()
})
