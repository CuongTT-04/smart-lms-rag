import { expect, it } from 'vitest'
import { parseVideoTime, formatVideoTime, seekTarget, firstCheckpoint } from './videoTime'
it('parses manual timestamps and rejects invalid minutes or seconds', () => {
  expect(parseVideoTime('01:20')).toBe(80)
  expect(parseVideoTime('1:02:03')).toBe(3723)
  expect(parseVideoTime('45')).toBe(45)
  expect(parseVideoTime('1:60')).toBeNull()
  expect(parseVideoTime('')).toBeNull()
  expect(formatVideoTime(80)).toBe('01:20')
})
it('permits teacher seeks but only student rewind, with a pending-question ceiling', () => {
  expect(seekTarget(5, 40, 60, false)).toBe(5)
  expect(seekTarget(50, 40, 60, false)).toBe(40)
  expect(seekTarget(50, 40, 60, true)).toBe(50)
  expect(seekTarget(90, 40, 60, true)).toBe(60)
  expect(firstCheckpoint([{ id: 'q1', start_time: 10 }, { id: 'q2', start_time: 20 }], new Set(['q1']))?.id).toBe('q2')
})
