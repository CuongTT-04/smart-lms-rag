import { apiRequest } from './api'

export async function listDocuments(courseId, signal) {
  const documents = []
  let page = 1
  let data
  do {
    data = await apiRequest(`/courses/${courseId}/documents/?page=${page}`, { signal })
    documents.push(...(data?.results || []))
    page += 1
  } while (data?.next)
  return documents
}

export function uploadDocument(courseId, file, title, key) {
  const body = new FormData()
  body.append('file', file)
  body.append('title', title || file.name)
  return apiRequest(`/courses/${courseId}/documents/`, {
    method: 'POST', headers: { 'Idempotency-Key': key }, body,
  })
}

export function documentStatus(documentId, versionId, signal) {
  return apiRequest(`/documents/${documentId}/status/?version_id=${encodeURIComponent(versionId)}`, { signal })
}

export function retryDocument(documentId, versionId, key) {
  return apiRequest(`/documents/${documentId}/retry/`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key },
    body: JSON.stringify({ version_id: versionId }),
  })
}

export function documentExtraction(documentId, versionId) {
  return apiRequest(`/documents/${documentId}/extraction/?version_id=${encodeURIComponent(versionId)}`)
}
