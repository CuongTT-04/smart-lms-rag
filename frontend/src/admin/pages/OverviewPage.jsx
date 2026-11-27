import { useState } from 'react'
import { ArrowUpRight, BookOpen, GraduationCap, UsersRound, ClipboardCheck } from 'lucide-react'
import useAdminData from '../hooks/useAdminData'
import { Feedback, Field } from '../components/AdminControls'
import { dateText, ROLES, STATUSES, labelOf } from '../components/admin-format'

export default function OverviewPage({ onNavigate, capabilities }) {
  const [period, setPeriod] = useState({ start_date: '', end_date: '' })
  const [draft, setDraft] = useState(period)
  const resource = useAdminData('overview/?' + new URLSearchParams(Object.entries(period).filter(([, value]) => value)))
  const data = resource.data
  return <><div className="adm-page-heading"><div><p className="adm-eyebrow">TOÀN CẢNH HỆ THỐNG</p><h1>Tổng quan</h1><p>Theo dõi tài khoản, lớp học và hoạt động học tập.</p></div></div>
    <form className="adm-toolbar" onSubmit={event => { event.preventDefault(); setPeriod(draft); resource.refresh() }}><Field label="Từ ngày" type="date" value={draft.start_date} onChange={e => setDraft({ ...draft, start_date: e.target.value })} /><Field label="Đến ngày" type="date" value={draft.end_date} onChange={e => setDraft({ ...draft, end_date: e.target.value })} /><button className="solid-button">Áp dụng</button></form>
    <Feedback resource={resource}>{data && <><div className="adm-stat-grid">{[[UsersRound, 'Tài khoản', data.accounts.total, 'accounts'], [BookOpen, 'Khóa học', data.courses], [GraduationCap, 'Lớp học', data.classrooms], [ClipboardCheck, 'Lượt nộp trong kỳ', data.submitted_attempts]].map(([Icon, label, count, target]) => <article className="adm-stat" key={label}><div><span>{label}</span><Icon size={20} /></div><strong>{count.toLocaleString('vi-VN')}</strong><small>{target ? 'Hiện có trên hệ thống' : label.includes('trong kỳ') ? 'Theo khoảng ngày đã chọn' : 'Số lượng hiện tại'}</small>{target && capabilities.accounts && <button aria-label="Xem danh sách tài khoản" onClick={() => onNavigate(target)}>Xem danh sách <ArrowUpRight size={15} /></button>}</article>)}</div>
      <div className="adm-two-columns"><section className="adm-panel"><h2>Cơ cấu tài khoản</h2><p>Số lượng hiện tại theo vai trò.</p>{ROLES.map(([role, label]) => { const count = data.accounts.by_role.find(row => row.role === role)?.count || 0; return <div className="adm-meter-row" key={role}><button disabled={!capabilities.accounts} onClick={() => onNavigate('accounts', { role })}>{label} <ArrowUpRight size={14} /></button><strong>{count}</strong><div className="adm-meter"><span style={{ width: `${data.accounts.total ? count / data.accounts.total * 100 : 0}%` }} /></div></div> })}</section>
        <section className="adm-panel"><h2>Trạng thái tài khoản</h2><p>Chọn một nhóm để xem danh sách tương ứng.</p>{data.accounts.by_status.map(row => <button className="adm-summary-row" disabled={!capabilities.accounts} key={row.status} onClick={() => onNavigate('accounts', { status: row.status })}><span>{labelOf(STATUSES, row.status)}</span><strong>{row.count}</strong></button>)}</section></div>
      <div className="adm-info">Cập nhật {dateText(data.as_of)} · Giờ Việt Nam. Lượt nộp: {dateText(data.period.start)} đến trước {dateText(data.period.end_exclusive)}. Các số tài khoản, khóa và lớp là hiện trạng, không lọc theo kỳ.</div></>}</Feedback></>
}
