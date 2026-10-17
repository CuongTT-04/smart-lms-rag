export function parseVideoTime(value) {
  if (!/^\d+(?::\d{1,2}){0,2}$/.test(value.trim())) return null
  const parts = value.trim().split(':').map(Number)
  if (parts.slice(1).some((part) => part >= 60)) return null
  const result = parts.reduce((total, part) => total * 60 + part, 0)
  return Number.isSafeInteger(result) ? result : null
}
export function formatVideoTime(value = 0) {
  const seconds = Math.max(0, Math.floor(value))
  const minutes = Math.floor(seconds / 60)
  return minutes >= 60 ? `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}` : `${String(minutes).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`
}
export function seekTarget(target, seekableUntil, duration, canManage) {
  return Math.max(0, Math.min(Number(target) || 0, duration, canManage ? duration : seekableUntil))
}
export function firstCheckpoint(questions, passed) {
  return questions.find((question) => !passed.has(question.id))
}
