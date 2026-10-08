import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import CustomSelect from './CustomSelect'

function Harness({ disabled = false, onChange = () => {} }) {
  const [value, setValue] = useState('PRIVATE')
  return <><label>Mức hiển thị<CustomSelect aria-label="Mức hiển thị" value={value} disabled={disabled} onChange={(event) => { setValue(event.target.value); onChange(event) }}><option value="PRIVATE">Riêng tư</option><option value="PUBLIC">Công khai</option><option value="LOCKED" disabled>Không khả dụng</option></CustomSelect></label><button type="button">Bên ngoài</button></>
}
describe('custom select', () => {
  it('renders custom options in a portal and updates the selected value', async () => {
    const change = vi.fn()
    const { container } = render(<Harness onChange={change} />)
    const control = screen.getByRole('combobox', { name: 'Mức hiển thị' })
    expect(control).toHaveTextContent('Riêng tư')
    expect(container.querySelector('select')).toBeNull()
    await userEvent.click(control)
    expect(control).toHaveAttribute('aria-expanded', 'true')
    expect(container.querySelector('[role=listbox]')).toBeNull()
    expect(screen.getByRole('option', { name: 'Riêng tư' })).toHaveAttribute('aria-selected', 'true')
    await userEvent.click(screen.getByRole('option', { name: 'Công khai' }))
    expect(change).toHaveBeenCalledWith({ target: { value: 'PUBLIC', name: undefined } })
    expect(control).toHaveTextContent('Công khai')
    expect(control).toHaveFocus()
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })
  it('supports keyboard selection, skips disabled options and closes with Escape', async () => {
    render(<Harness />)
    const control = screen.getByRole('combobox')
    control.focus()
    await userEvent.keyboard('{ArrowDown}{End}{Enter}')
    expect(control).toHaveTextContent('Công khai')
    await userEvent.keyboard('{Enter}{Home}{Escape}')
    expect(control).toHaveTextContent('Công khai')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    expect(control).toHaveFocus()
  })
  it('supports type-ahead and Tab without committing a highlighted option', async () => {
    render(<Harness />)
    const control = screen.getByRole('combobox')
    control.focus()
    await userEvent.keyboard('c{Enter}')
    expect(control).toHaveTextContent('Công khai')
    await userEvent.keyboard('{Enter}{Home}{Tab}')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    expect(control).toHaveTextContent('Công khai')
    expect(screen.getByRole('button', { name: 'Bên ngoài' })).toHaveFocus()
  })
  it('closes on outside clicks and never selects disabled options', async () => {
    const change = vi.fn()
    render(<Harness onChange={change} />)
    await userEvent.click(screen.getByRole('combobox'))
    await userEvent.click(screen.getByRole('option', { name: 'Không khả dụng' }))
    expect(change).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Bên ngoài' }))
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })
  it('does not open a disabled control', async () => {
    render(<Harness disabled />)
    await userEvent.click(screen.getByRole('combobox'))
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })
  it('positions the menu above a trigger near the bottom of the viewport', async () => {
    render(<Harness />)
    const control = screen.getByRole('combobox')
    vi.spyOn(control, 'getBoundingClientRect').mockReturnValue({ top: 720, bottom: 764, left: 900, width: 200 })
    await userEvent.click(control)
    const popup = screen.getByRole('listbox').parentElement
    expect(Number.parseFloat(popup.style.top)).toBeLessThan(720)
    expect(Number.parseFloat(popup.style.left) + Number.parseFloat(popup.style.width)).toBeLessThanOrEqual(window.innerWidth - 12)
    fireEvent.resize(window)
    expect(screen.getByRole('listbox')).toBeVisible()
  })
})
