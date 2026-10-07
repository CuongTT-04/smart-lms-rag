export const PASSWORD_REQUIREMENTS = 'Mật khẩu phải có ít nhất 8 ký tự, bao gồm ít nhất 1 chữ in hoa, 1 chữ số (0-9) và 1 ký tự đặc biệt (không tính khoảng trắng).'

export function passwordError(password) {
  return Array.from(password).length >= 8 && /\p{Lu}/u.test(password) && /[0-9]/.test(password) && /[\p{P}\p{S}]/u.test(password)
    ? '' : PASSWORD_REQUIREMENTS
}
