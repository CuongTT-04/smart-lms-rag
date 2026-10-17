import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'

const NavigationOwner = createContext('standalone')
let pending = null

const storageKey = (owner) => `ohayo.navigation.${owner}`

function saveNavigation(navigation) {
  try { window.sessionStorage.setItem(storageKey(navigation.owner), JSON.stringify(navigation)) }
  catch { /* History navigation still works when browser storage is unavailable. */ }
}

function navigationFor(owner, restoreSaved = true) {
  const stored = window.history.state?.ohayoNavigation
  if (stored && stored.owner === owner && stored.values) return stored
  if (restoreSaved) {
    try {
      const saved = JSON.parse(window.sessionStorage.getItem(storageKey(owner)))
      if (saved && saved.owner === owner && saved.values && typeof saved.values === 'object' && !Array.isArray(saved.values)) return saved
    } catch { /* Ignore missing, invalid or unavailable session storage. */ }
  }
  return { owner, values: {} }
}

// eslint-disable-next-line react-refresh/only-export-components
export function clearNavigation(owner) {
  pending = null
  try { window.sessionStorage.removeItem(storageKey(owner)) } catch { /* Storage can be disabled. */ }
  window.history.replaceState({ ...window.history.state, ohayoNavigation: { owner, values: {} } }, '')
}

function queueNavigation(owner, key, value) {
  if (!pending || pending.owner !== owner) {
    const batch = { owner, values: { ...navigationFor(owner).values }, base: window.history.state }
    pending = batch
    queueMicrotask(() => {
      if (pending !== batch) return
      pending = null
      const navigation = { owner, values: batch.values }
      saveNavigation(navigation)
      window.history.pushState({ ...batch.base, ohayoNavigation: navigation }, '')
    })
  }
  pending.values[key] = value
}

export function NavigationProvider({ owner, children }) {
  useEffect(() => {
    if (window.history.state?.ohayoNavigation?.owner !== owner) {
      pending = null
      window.history.replaceState({ ...window.history.state, ohayoNavigation: navigationFor(owner) }, '')
    }
  }, [owner])
  return <NavigationOwner.Provider value={owner}>{children}</NavigationOwner.Provider>
}

// Only screen selection belongs here; form drafts and fetched data remain local.
// Batch updates made by one click into a single browser-history entry.
// eslint-disable-next-line react-refresh/only-export-components
export function useHistoryState(key, initialValue) {
  const owner = useContext(NavigationOwner)
  const initial = useRef(initialValue)
  const read = useCallback(() => {
    const values = navigationFor(owner, false).values
    return Object.hasOwn(values, key) ? values[key] : initial.current
  }, [owner, key])
  const [value, setValue] = useState(() => {
    const values = navigationFor(owner).values
    return Object.hasOwn(values, key) ? values[key] : initialValue
  })
  const current = useRef(value)
  useEffect(() => {
    function restore() {
      pending = null
      const restored = read()
      saveNavigation(navigationFor(owner, false))
      current.current = restored
      setValue(restored)
    }
    window.addEventListener('popstate', restore)
    return () => window.removeEventListener('popstate', restore)
  }, [read, owner])
  const navigate = useCallback((next) => {
    const updated = typeof next === 'function' ? next(current.current) : next
    if (Object.is(current.current, updated)) return
    current.current = updated
    setValue(updated)
    queueNavigation(owner, key, updated)
  }, [owner, key])
  return [value, navigate]
}
