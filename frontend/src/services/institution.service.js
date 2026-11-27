import { apiRequest } from './api'

export function listInstitutions(query = '', signal) {
  return apiRequest(`/users/institutions/?${new URLSearchParams({ q: query, limit: '20' })}`, { signal, skipRefresh: true })
}
