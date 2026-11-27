import { useCallback, useEffect, useState } from 'react'
import { adminRequest } from '../services/admin.service'

export default function useAdminData(path) {
  const [revision, setRevision] = useState(0)
  const [state, setState] = useState({ path: null, data: null, loading: true, error: null })
  const refresh = useCallback(() => setRevision(value => value + 1), [])
  useEffect(() => {
    if (!path) return
    const controller = new AbortController()
    adminRequest(path, { signal: controller.signal }).then(
      data => { if (!controller.signal.aborted) setState({ path, data, loading: false, error: null }) },
      error => { if (!controller.signal.aborted) setState({ path, data: null, loading: false, error }) },
    )
    return () => controller.abort()
  }, [path, revision])
  // A new query never displays rows from the previous filter or account.
  return { ...((state.path === path) ? state : { data: null, error: null, loading: true }), refresh }
}
