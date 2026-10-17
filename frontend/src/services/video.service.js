import { apiRequest } from './api'
export const videoPath = (courseId, roomId, sessionId) => `/courses/${courseId}/classrooms/${roomId}/sessions/${sessionId}/videos/`
const write = (path, method, data) => apiRequest(path, { method, headers: { 'Content-Type': 'application/json' }, body: data === undefined ? undefined : JSON.stringify(data) })
export async function listSessionVideos(path, signal) {
  const results = []
  let page = 1
  let next
  do {
    const data = await apiRequest(`${path}?page=${page++}`, { signal })
    results.push(...data.results)
    next = data.next
  } while (next)
  return results
}
export const getSessionVideo = (path, id, signal) => apiRequest(`${path}${id}/`, { signal })
export const getVideoFile = (path, id, signal) => apiRequest(`${path}${id}/file/`, { signal, responseType: 'video', timeoutMs: 120000 })
export function uploadSessionVideo(path, values) {
  const body = new FormData()
  Object.entries(values).forEach(([key, value]) => body.append(key, value))
  return apiRequest(path, { method: 'POST', body, timeoutMs: 120000 })
}
export const updateSessionVideo = (path, id, values) => write(`${path}${id}/`, 'PATCH', values)
export const deleteSessionVideo = (path, id) => write(`${path}${id}/`, 'DELETE')
export const createVideoQuestion = (path, id, values) => write(`${path}${id}/questions/`, 'POST', values)
export const updateVideoQuestion = (path, id, questionId, values) => write(`${path}${id}/questions/${questionId}/`, 'PATCH', values)
export const deleteVideoQuestion = (path, id, questionId) => write(`${path}${id}/questions/${questionId}/`, 'DELETE')
export const saveVideoProgress = (path, id, position) => apiRequest(`${path}${id}/progress/`, { method: 'PUT', keepalive: true, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ position }) })
export const answerVideoQuestion = (path, id, questionId, values) => write(`${path}${id}/questions/${questionId}/answers/`, 'POST', values)
export async function getMyVideoAnswers(path, id, signal) {
  const results = []
  let page = 1
  let next
  do {
    const data = await apiRequest(`${path}${id}/answers/mine/?page=${page++}`, { signal })
    results.push(...data.results)
    next = data.next
  } while (next)
  return results
}
export async function getVideoResponses(path, id, signal) {
  const first = await apiRequest(`${path}${id}/responses/`, { signal })
  const results = [...first.results]
  let next = first.next
  let page = 2
  while (next) {
    const data = await apiRequest(`${path}${id}/responses/?page=${page++}`, { signal })
    results.push(...data.results); next = data.next
  }
  return { ...first, results }
}
