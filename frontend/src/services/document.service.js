import { apiRequest } from './api'

export async function listDocuments(courseId, signal, sessionId) {
  const documents = []
  let page = 1
  let data
  do {
    data = await apiRequest(`/courses/${courseId}/documents/?page=${page}&${sessionId ? `session_id=${encodeURIComponent(sessionId)}` : 'scope=course'}`, { signal })
    documents.push(...(data?.results || []))
    page += 1
  } while (data?.next)
  return documents
}

export function uploadDocument(courseId, file, title, key, sessionId) {
  const body = new FormData()
  body.append('file', file)
  if (sessionId) body.append('session_id', sessionId)
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

export function publishDocument(documentId, versionId, published) {
  return apiRequest(`/documents/${documentId}/publication/`, { method:'PATCH',
    headers:{'Content-Type':'application/json'},body:JSON.stringify({is_published:published,...(published ? {version_id:versionId} : {})}) })
}
export function changeMaterialPolicy(documentId, materialPolicy, revision) {
  return apiRequest(`/documents/${documentId}/policy/`, {method:'PATCH',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({material_policy:materialPolicy,policy_revision:revision})})
}
export function replaceDocument(documentId,file,key) {
  const body=new FormData();body.append('file',file)
  return apiRequest(`/documents/${documentId}/versions/`,{method:'POST',headers:{'Idempotency-Key':key},body})
}
export function removeDocument(documentId) { return apiRequest(`/documents/${documentId}/`,{method:'DELETE'}) }
export function renameDocument(documentId, title) {
  return apiRequest(`/documents/${documentId}/`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title }) })
}
export function materialPdf(documentId,download=false,signal,versionId) {
  return apiRequest(`/documents/${documentId}/${download ? 'download' : 'view'}/${versionId && !download ? `?version_id=${encodeURIComponent(versionId)}` : ''}`,{
    responseType:'blob',headers:{Accept:'application/pdf, application/json'},signal,
  })
}

// Serialize writes across viewer mounts so re-entering a lesson reads the last edit.
const studyWrites = new Map()
const studyKey = (id, version) => `${id}:${version}`
export async function readStudyNotes(id, version, signal) {
  await studyWrites.get(studyKey(id, version))?.catch(() => {})
  return apiRequest(`/documents/${id}/study-notes/?version_id=${encodeURIComponent(version)}`, { signal })
}
export function writeStudyNotes(id, version, value) {
  const key = studyKey(id, version)
  const request = (studyWrites.get(key) || Promise.resolve()).catch(() => {}).then(() => apiRequest(`/documents/${id}/study-notes/?version_id=${encodeURIComponent(version)}`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value),
  }))
  studyWrites.set(key, request)
  request.finally(() => { if (studyWrites.get(key) === request) studyWrites.delete(key) }).catch(() => {})
  return request
}
