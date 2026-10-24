import { beforeEach, expect, it, vi } from 'vitest'
import { openNotificationTarget } from './notificationNavigation'
vi.mock('../../services/course.service', () => ({ getCourse: vi.fn(async () => ({ id: 'c' })), listClassrooms: vi.fn(async () => [{ id: 'r' }]) }))
beforeEach(() => { window.history.replaceState(null, '', '/'); vi.spyOn(window, 'scrollTo').mockImplementation(() => {}) })
it('opens the exact attempt and changes a navigation revision to reload cached lists', async () => {
  await openNotificationTarget({ course_id: 'c', classroom_id: 'r', session_id: 's', assessment_id: 'a', attempt_id: 'attempt' }, { id: 't', role: 'TEACHER' })
  const values = window.history.state.ohayoNavigation.values
  expect(values['assessment.a.attempt']).toBe('attempt')
  expect(values['notifications.navigation']).toBeTruthy()
})
it('carries course-scope PDF selection to a real document destination', async () => {
  await openNotificationTarget({ course_id: 'c', document_id: 'pdf' }, { id: 's', role: 'STUDENT' })
  expect(window.history.state.ohayoNavigation.values['notifications.document']).toEqual({ course_id: 'c', document_id: 'pdf' })
})
