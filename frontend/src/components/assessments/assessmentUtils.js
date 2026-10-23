export const dateLabel = (value) => value ? new Date(value).toLocaleString('vi-VN') : '—'
export const correctIds = (question) => question.correct_ids || (question.correct_id ? [question.correct_id] : [])
export const answerIds = (answer) => Array.isArray(answer) ? answer : typeof answer === 'string' ? [answer] : []
