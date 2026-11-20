import { useCallback, useEffect, useRef, useState } from 'react'
import { courseErrorMessage, getClassroomProgress } from '../services/course.service'

export function useClassroomProgress(courseId, classroomId, enabled = true) {
  const [state, setState] = useState({ scope: '', progress: null, loading: false, error: '' })
  const requestEpoch = useRef(0)
  const controllerRef = useRef(null)
  const activeScope = enabled && courseId && classroomId ? `${courseId}:${classroomId}` : ''

  const fetchProgress = useCallback(async () => {
    controllerRef.current?.abort()
    if (!activeScope) return null
    const epoch = ++requestEpoch.current
    const controller = new AbortController()
    controllerRef.current = controller
    setState((prev) => ({
      scope: activeScope,
      progress: prev.scope === activeScope ? prev.progress : null,
      loading: true,
      error: '',
    }))
    try {
      const data = await getClassroomProgress(courseId, classroomId, controller.signal)
      if (controller.signal.aborted || requestEpoch.current !== epoch) return null
      setState({ scope: activeScope, progress: data, loading: false, error: '' })
      return data
    } catch (err) {
      if (controller.signal.aborted || requestEpoch.current !== epoch) return null
      setState((prev) => ({
        scope: activeScope,
        progress: prev.scope === activeScope ? prev.progress : null,
        loading: false,
        error: courseErrorMessage(err),
      }))
      return null
    }
  }, [activeScope, courseId, classroomId])

  useEffect(() => {
    if (!activeScope) return undefined
    const timer = setTimeout(() => { fetchProgress() }, 0)
    return () => {
      clearTimeout(timer)
      controllerRef.current?.abort()
    }
  }, [activeScope, fetchProgress])

  const applyProgress = useCallback((nextProgress) => {
    if (!activeScope || !nextProgress) return
    setState({ scope: activeScope, progress: nextProgress, loading: false, error: '' })
  }, [activeScope])

  if (!activeScope) {
    return { progress: null, loading: false, error: '', reload: fetchProgress, applyProgress }
  }
  const current = state.scope === activeScope
  return {
    progress: current ? state.progress : null,
    loading: current ? state.loading : true,
    error: current ? state.error : '',
    reload: fetchProgress,
    applyProgress,
  }
}
