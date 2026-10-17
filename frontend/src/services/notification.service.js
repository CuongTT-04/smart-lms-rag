import { apiRequest } from './api'

export const listNotifications = (page = 1, unread = false, signal) => apiRequest(`/notifications/?page=${page}&unread=${unread}`, { signal })
export const readNotification = (id, signal) => apiRequest(`/notifications/${id}/read/`, { method: 'POST', signal })
export const readAllNotifications = (signal) => apiRequest('/notifications/read-all/', { method: 'POST', signal })
export const notificationTicket = (signal) => apiRequest('/notifications/ws-ticket/', { method: 'POST', signal })
export const notificationTarget = (id, signal) => apiRequest(`/notifications/${id}/target/`, { signal })

