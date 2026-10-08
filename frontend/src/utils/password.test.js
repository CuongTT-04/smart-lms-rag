import { describe, expect, it } from 'vitest'
import { passwordError, PASSWORD_REQUIREMENTS } from './password'

describe('shared password policy', () => {
  it.each(['', 'Ab1!xyz', 'abcdefgh1!', 'Abcdefgh!', 'Abcdefg1', 'Abcdef1 ', 'Abcdef1\t', 'Abcdef1\u200b', 'Abcdef1\u0301', 'Đ1!😀😀😀😀'])('rejects invalid password %j', (password) => {
    expect(passwordError(password)).toBe(PASSWORD_REQUIREMENTS)
  })
  it.each(['Abcdef1!', 'ABCDEF1!', 'Password1!', 'Đabcdef1!', 'Abcdef1_', 'Abcdef1😀', '  Abcdef1!  ', 'Đ1!😀😀😀😀😀'])('accepts valid password %j', (password) => {
    expect(passwordError(password)).toBe('')
  })
})
