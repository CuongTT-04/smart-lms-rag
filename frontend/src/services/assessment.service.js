import { apiRequest } from './api'
export const assessmentPath = (course, room, session) => `/courses/${course}/classrooms/${room}/sessions/${session}/assessments/`
export const assessmentWrite = (path, method, data) => apiRequest(path, { method, headers: { 'Content-Type': 'application/json' }, body: data === undefined ? undefined : JSON.stringify(data) })
export async function listAssessments(path, signal) {
  const rows = []
  let page = 1, next
  do {
    const data = await apiRequest(`${path}?page=${page++}`, { signal })
    rows.push(...data.results); next = data.next
  } while (next)
  return rows
}
export const getAssessment = (path, signal) => apiRequest(path, { signal })
export function saveAssessmentDraft(path, values) {
  if (!values.file) {
    const body = JSON.stringify(values)
    return apiRequest(path, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body, keepalive: new TextEncoder().encode(body).byteLength <= 60000 })
  }
  const body = new FormData()
  Object.entries(values).forEach(([key, value]) => body.append(key, value))
  return apiRequest(path, { method: 'PATCH', body, timeoutMs: 120000 })
}
export async function downloadAssessmentFile(path, name, type = 'submission') {
  const blob = await apiRequest(path, { responseType: type, timeoutMs: 120000 })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url; link.download = name; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
