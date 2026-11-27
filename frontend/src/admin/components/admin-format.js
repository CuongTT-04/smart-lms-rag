export const dateText = value => value ? new Intl.DateTimeFormat('vi-VN', { dateStyle: 'short', timeStyle: 'short', timeZone: 'Asia/Ho_Chi_Minh' }).format(new Date(value)) : 'Chưa có'
export const ROLES = [['STUDENT', 'Học viên'], ['TEACHER', 'Giáo viên'], ['ADMIN', 'Quản trị viên']]
export const STATUSES = [['ACTIVE', 'Đang hoạt động'], ['INACTIVE', 'Ngừng hoạt động'], ['BLOCKED', 'Đã khóa']]
export const APPROVALS = [['PENDING', 'Chờ duyệt'], ['APPROVED', 'Đã duyệt'], ['REJECTED', 'Từ chối'], ['REVOKED', 'Thu hồi']]
export const labelOf = (rows, value) => rows.find(([key]) => key === value)?.[1] || value || 'Chưa có'
export const approvalSource = value => ({ AUTO_EDU_VN: 'Email trường đã xác minh', ADMIN: 'Quản trị viên duyệt', LEGACY: 'Giáo viên hiện hữu' })[value] || 'Chưa có nguồn duyệt'
