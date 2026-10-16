import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it } from 'vitest'
import { clearNavigation, NavigationProvider, useHistoryState } from './useHistoryState'

function Screen() {
  const [view, setView] = useHistoryState('view', 'overview')
  const [course, setCourse] = useHistoryState('course', null)
  return <><h1>{view}:{course || 'list'}</h1><button onClick={() => { setView('courses'); setCourse('python') }}>Open</button></>
}
it('records one browser entry per navigation and restores Back and Forward', async () => {
  render(<NavigationProvider owner="u1"><Screen /></NavigationProvider>)
  const length = window.history.length
  await userEvent.click(screen.getByText('Open'))
  expect(window.history.length).toBe(length + 1)
  act(() => window.history.back())
  await waitFor(() => expect(screen.getByRole('heading')).toHaveTextContent('overview:list'))
  act(() => window.history.forward())
  await waitFor(() => expect(screen.getByRole('heading')).toHaveTextContent('courses:python'))
})
it('restores navigation on remount but isolates another account', async () => {
  const first = render(<NavigationProvider owner="u1"><Screen /></NavigationProvider>)
  await userEvent.click(screen.getByText('Open'))
  first.unmount()
  const second = render(<NavigationProvider owner="u1"><Screen /></NavigationProvider>)
  expect(screen.getByRole('heading')).toHaveTextContent('courses:python')
  second.unmount()
  render(<NavigationProvider owner="u2"><Screen /></NavigationProvider>)
  expect(screen.getByRole('heading')).toHaveTextContent('overview:list')
})

it('restores the current screen after a reload loses browser history state', async () => {
  const first = render(<NavigationProvider owner="u1"><Screen /></NavigationProvider>)
  await userEvent.click(screen.getByText('Open'))
  first.unmount()
  window.history.replaceState(null, '', '/')
  const reloaded = render(<NavigationProvider owner="u1"><Screen /></NavigationProvider>)
  expect(screen.getByRole('heading')).toHaveTextContent('courses:python')
  reloaded.unmount()
  clearNavigation('u1')
  window.history.replaceState(null, '', '/')
  render(<NavigationProvider owner="u1"><Screen /></NavigationProvider>)
  expect(screen.getByRole('heading')).toHaveTextContent('overview:list')
})

it('persists the destination of Back rather than the last opened detail', async () => {
  const first = render(<NavigationProvider owner="u1"><Screen /></NavigationProvider>)
  await userEvent.click(screen.getByText('Open'))
  act(() => window.history.back())
  await waitFor(() => expect(screen.getByRole('heading')).toHaveTextContent('overview:list'))
  first.unmount()
  window.history.replaceState(null, '', '/')
  render(<NavigationProvider owner="u1"><Screen /></NavigationProvider>)
  expect(screen.getByRole('heading')).toHaveTextContent('overview:list')
})
