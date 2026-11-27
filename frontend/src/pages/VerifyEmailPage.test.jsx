import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import VerifyEmailPage from './VerifyEmailPage'
import { confirmEmailVerification } from '../services/auth.service'

vi.mock('../services/auth.service', async original => ({ ...await original(), confirmEmailVerification: vi.fn() }))
beforeEach(() => { vi.clearAllMocks(); window.history.replaceState(null, '', '/verify-email?token=fixture-token') })
it('removes token from address bar and waits for explicit confirmation', async () => {
  confirmEmailVerification.mockResolvedValue({ email_verified: true })
  render(<VerifyEmailPage />)
  expect(window.location.search).toBe('')
  expect(confirmEmailVerification).not.toHaveBeenCalled()
  await userEvent.click(screen.getByRole('button', { name: 'Xác minh email' }))
  expect(await screen.findByText('Xác minh email thành công.')).toBeVisible()
  expect(confirmEmailVerification).toHaveBeenCalledWith('fixture-token')
})
it('handles missing, expired and consumed tokens without exposing token text', async () => {
  confirmEmailVerification.mockRejectedValue({ status: 400 })
  render(<VerifyEmailPage />)
  await userEvent.click(screen.getByRole('button', { name: 'Xác minh email' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Liên kết không hợp lệ, đã hết hạn hoặc đã được sử dụng.')
  expect(screen.queryByText('fixture-token')).not.toBeInTheDocument()
})
it('does not submit duplicate clicks while pending', () => {
  confirmEmailVerification.mockImplementation(() => new Promise(() => {}))
  render(<VerifyEmailPage />)
  const button = screen.getByRole('button', { name: 'Xác minh email' })
  fireEvent.click(button); fireEvent.click(button)
  expect(confirmEmailVerification).toHaveBeenCalledTimes(1)
})
it('rejects a link without a token', () => {
  window.history.replaceState(null, '', '/verify-email')
  render(<VerifyEmailPage />)
  expect(screen.queryByRole('button', { name: 'Xác minh email' })).not.toBeInTheDocument()
})
