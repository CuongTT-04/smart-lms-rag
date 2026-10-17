import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import NotificationProvider from './NotificationProvider'
import NotificationBell from './NotificationBell'
import { listNotifications, readAllNotifications, notificationTicket } from '../../services/notification.service'

vi.mock('../../services/notification.service', () => ({
  listNotifications: vi.fn(), readAllNotifications: vi.fn(), readNotification: vi.fn(),
  notificationTicket: vi.fn(), notificationTarget: vi.fn(),
}))
const page = { count: 1, next: null, unread_count: 1, results: [{ id: 'n1', title: 'Buổi học mới', body: '', created_at: '2026-10-17T10:00:00Z', read_at: null }] }
beforeEach(() => {
  vi.clearAllMocks()
  listNotifications.mockResolvedValue(page)
  readAllNotifications.mockResolvedValue({ unread_count: 0 })
  notificationTicket.mockRejectedValue(new Error('offline'))
})
afterEach(() => vi.unstubAllGlobals())
it('deduplicates realtime toasts and closes the socket on logout', async () => {
  const sockets = []
  class Socket {
    constructor() { this.close = vi.fn(); sockets.push(this) }
  }
  vi.stubGlobal('WebSocket', Socket)
  notificationTicket.mockResolvedValue({ticket:'single-use'})
  const {unmount} = render(<NotificationProvider user={{id:'s1'}}><NotificationBell /></NotificationProvider>)
  await waitFor(() => expect(sockets).toHaveLength(1))
  act(() => sockets[0].onopen())
  await screen.findByLabelText('1 thông báo chưa đọc')
  await act(async () => sockets[0].onmessage({data:JSON.stringify({type:'notifications.changed',reason:'created',notification_id:'n1'})}))
  expect(await screen.findByRole('status')).toHaveTextContent('Buổi học mới')
  await act(async () => sockets[0].onmessage({data:JSON.stringify({type:'notifications.changed',reason:'created',notification_id:'n1'})}))
  expect(screen.getAllByRole('status')).toHaveLength(1)
  unmount()
  expect(sockets[0].close).toHaveBeenCalledOnce()
})
it('loads offline history without toasting it and marks all read', async () => {
  const user = userEvent.setup()
  render(<NotificationProvider user={{ id: 's1', role: 'STUDENT' }}><NotificationBell /></NotificationProvider>)
  await screen.findByLabelText('1 thông báo chưa đọc')
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Thông báo' }))
  expect(await screen.findByText('Buổi học mới')).toBeVisible()
  listNotifications.mockResolvedValue({ ...page, unread_count: 0, results: [{ ...page.results[0], read_at: '2026-10-17T11:00:00Z' }] })
  await user.click(screen.getByRole('button', { name: 'Đọc tất cả' }))
  expect(readAllNotifications).toHaveBeenCalledOnce()
  expect(screen.queryByLabelText('1 thông báo chưa đọc')).not.toBeInTheDocument()
})
it('cleans up late requests from a previous account', async () => {
  let resolve
  listNotifications.mockReturnValueOnce(new Promise((done) => { resolve = done }))
  const { unmount } = render(<NotificationProvider user={{ id: 'old' }}><NotificationBell /></NotificationProvider>)
  unmount()
  resolve(page)
  expect(screen.queryByText('Buổi học mới')).not.toBeInTheDocument()
})
