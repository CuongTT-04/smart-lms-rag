import { useId, useRef, useState } from 'react'
import { Plus, Upload } from 'lucide-react'
import FilePicker from '../../components/FilePicker'
import useAdminData from '../hooks/useAdminData'
import { adminError, adminRequest, writeAdmin } from '../services/admin.service'
import { Feedback, Field, Modal, SelectField, Status, ValidatedForm } from '../components/AdminControls'

const LEVELS = [['PRIMARY', 'Tiểu học'], ['LOWER_SECONDARY', 'THCS'], ['UPPER_SECONDARY', 'THPT'], ['COLLEGE', 'Cao đẳng'], ['UNIVERSITY', 'Đại học']]

export default function InstitutionsPage({ capabilities }) {
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState('')
  const [level, setLevel] = useState('')
  const [offset, setOffset] = useState(0)
  const [edit, setEdit] = useState(null)
  const [importing, setImporting] = useState(false)
  const resource = useAdminData('institutions/?' + new URLSearchParams({ q: query, ...(level ? { level } : {}), offset, limit: 20 }))
  const canEdit = edit && (edit.id ? capabilities.edit_institution : capabilities.create_institution)
  return <><div className="adm-page-heading"><div><p className="adm-eyebrow">DỮ LIỆU DÙNG CHUNG</p><h1>Danh mục trường</h1><p>Thông tin trường công tác và nguồn đối chiếu.</p></div><div className="adm-action-strip">{capabilities.import_institutions && <button className="secondary-button" onClick={() => setImporting(true)}><Upload size={17} />Nhập CSV / XLSX</button>}{capabilities.create_institution && <button className="solid-button" onClick={() => setEdit({})}><Plus size={17} />Thêm trường</button>}</div></div>
    <form className="adm-toolbar" onSubmit={e => { e.preventDefault(); setQuery(search); setOffset(0) }}><Field label="Tìm trường" placeholder="Tên, mã hoặc viết tắt" value={search} onChange={e => setSearch(e.target.value)} /><SelectField label="Cấp học" value={level} onChange={v => { setLevel(v); setOffset(0) }} options={[["", 'Tất cả cấp học'], ...LEVELS]} /><button className="secondary-button">Tìm kiếm</button></form>
    <div className="adm-panel adm-table-panel"><Feedback resource={resource} empty={!resource.data?.results.length}><div className="adm-table-scroll"><table><thead><tr><th>Trường</th><th>Địa phương</th><th>Nguồn đối chiếu</th><th>Trạng thái</th><th><span className="sr-only">Thao tác</span></th></tr></thead><tbody>{resource.data?.results.map(row => <tr key={row.id}><td><strong>{row.name}</strong><small>{row.code} · {row.aliases.join(', ')}</small></td><td>{row.province}<small>{row.campus || 'Không phân cơ sở'}</small></td><td><a href={row.source_url} target="_blank" rel="noreferrer">Website nguồn ↗</a><small>Kiểm ngày {row.source_checked_at}</small></td><td><Status tone={row.active ? 'good' : ''}>{row.active ? 'Hoạt động' : 'Ngừng hoạt động'}</Status></td><td>{capabilities.edit_institution && <button className="adm-text-button" onClick={() => setEdit(row)}>Chỉnh sửa</button>}</td></tr>)}</tbody></table></div></Feedback><div className="adm-pagination"><span>Trang {Math.floor(offset / 20) + 1}</span><div><button disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 20))}>Trước</button><button disabled={!resource.data?.has_more} onClick={() => setOffset(resource.data.next_offset)}>Sau</button></div></div></div>
    {canEdit && <InstitutionForm institution={edit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); resource.refresh() }} />}{importing && capabilities.import_institutions && <ImportForm onClose={() => setImporting(false)} onSaved={resource.refresh} />}</>
}

function InstitutionForm({ institution, onClose, onSaved }) {
  const levelsErrorId = useId()
  const [levelsError, setLevelsError] = useState('')
  const [form, setForm] = useState({ code: '', name: '', province: '', campus: '', aliases: [], levels: ['UNIVERSITY'], external_code: '', source_url: '', source_checked_at: '', active: true, ...institution })
  const [state, setState] = useState({ busy: false, error: '' })
  const lock = useRef(false)
  const set = (key, value) => setForm(old => ({ ...old, [key]: value }))
  function validate(element) {
    const error = form.levels.length ? '' : 'Vui lòng chọn ít nhất một cấp học.'
    setLevelsError(error)
    if (error) element.querySelector('input[type="checkbox"]')?.focus()
    return !error
  }
  async function submit(event) {
    event.preventDefault(); if (lock.current) return
    lock.current = true; setState({ busy: true, error: '' })
    const body = Object.fromEntries(['code', 'name', 'province', 'campus', 'aliases', 'levels', 'external_code', 'source_url', 'source_checked_at', 'active'].map(key => [key, form[key]]))
    if (institution.id) delete body.code
    body.aliases = body.aliases.map(value => value.trim()).filter(Boolean)
    try { await writeAdmin(`institutions/${institution.id ? institution.id + '/' : ''}`, body, institution.id ? 'PATCH' : 'POST'); onSaved() } catch (error) { setState({ busy: false, error: adminError(error) }) } finally { lock.current = false }
  }
  return <Modal title={institution.id ? 'Cập nhật trường' : 'Thêm trường'} busy={state.busy} onClose={onClose}><ValidatedForm className="adm-form" onSubmit={submit} validate={validate}><div className="adm-form-grid">{[['code', 'Mã nội bộ'], ['name', 'Tên trường'], ['province', 'Tỉnh / thành phố'], ['campus', 'Cơ sở'], ['external_code', 'Mã trường bên ngoài'], ['source_url', 'Đường dẫn nguồn HTTPS']].map(([key, label]) => <Field key={key} label={label} value={form[key]} required={['code', 'name', 'province', 'source_url'].includes(key)} type={key === 'source_url' ? 'url' : 'text'} data-https-only={key === 'source_url' ? 'true' : undefined} disabled={state.busy || (key === 'code' && !!institution.id)} onChange={e => set(key, e.target.value)} />)}</div><Field label="Tên viết tắt (phân cách bằng dấu phẩy)" value={form.aliases.join(', ')} onChange={e => set('aliases', e.target.value.split(',').map(v => v.trim()))} disabled={state.busy} /><fieldset className="adm-checks" aria-invalid={Boolean(levelsError)} aria-describedby={levelsError ? levelsErrorId : undefined}><legend>Cấp học</legend>{LEVELS.map(([key, label]) => <label key={key}><input type="checkbox" checked={form.levels.includes(key)} disabled={state.busy} onChange={e => { set('levels', e.target.checked ? [...form.levels, key] : form.levels.filter(v => v !== key)); setLevelsError('') }} />{label}</label>)}</fieldset>{levelsError && <p className="field-error" id={levelsErrorId}>{levelsError}</p>}<Field label="Ngày đối chiếu nguồn" type="date" required value={form.source_checked_at} disabled={state.busy} onChange={e => set('source_checked_at', e.target.value)} /><SelectField label="Trạng thái trường" value={form.active ? 'true' : 'false'} onChange={v => set('active', v === 'true')} disabled={state.busy} options={[["true", 'Hoạt động'], ['false', 'Ngừng hoạt động']]} /><p className="adm-info">Ngừng hoạt động giữ nguyên hồ sơ đã liên kết. Không xóa trường khỏi lịch sử.</p>{state.error && <p className="error-banner" role="alert">{state.error}</p>}<button className="solid-button" disabled={state.busy}>{state.busy ? 'Đang lưu…' : 'Lưu thông tin trường'}</button></ValidatedForm></Modal>
}

function ImportForm({ onClose, onSaved }) {
  const [file, setFile] = useState(null)
  const [report, setReport] = useState(null)
  const [state, setState] = useState({ busy: false, error: '', done: false })
  const lock = useRef(false)
  async function run(apply) {
    if (!file || lock.current || (apply && (!report?.valid || state.done))) return
    lock.current = true; setState({ busy: true, error: '', done: false })
    const body = new FormData(); body.append('file', file); body.append('dry_run', apply ? 'false' : 'true')
    try { const value = await adminRequest('institutions/import/', { method: 'POST', body }); setReport(value); setState({ busy: false, error: '', done: apply && value.valid }); if (apply && value.valid) onSaved() } catch (error) { setReport(null); setState({ busy: false, error: adminError(error), done: false }) } finally { lock.current = false }
  }
  return <Modal title="Nhập danh mục trường" onClose={onClose} busy={state.busy}><div className="adm-form"><p>CSV UTF-8 hoặc XLSX một sheet, tối đa 2 MiB và 500 dòng. Luôn xem trước trước khi nhập.</p><div className="adm-info">Cột bắt buộc: code, name, province, levels, source_url, source_checked_at. Các cấp học dùng dấu |, ngày YYYY-MM-DD. Mã cấp: PRIMARY, LOWER_SECONDARY, UPPER_SECONDARY, COLLEGE, UNIVERSITY.</div><div className="adm-import-file"><FilePicker label="File danh mục" file={file} accept=".csv,.xlsx" disabled={state.busy} onChange={e => { setFile(e.target.files?.[0] || null); setReport(null); setState({ busy: false, error: '', done: false }) }} />{file && <p className="adm-file-meta">{file.size < 1024 * 1024 ? `${Math.max(1, Math.ceil(file.size / 1024))} KB` : `${(file.size / (1024 * 1024)).toFixed(2)} MB`} · Đã chọn từ thiết bị</p>}</div>{report && <div className="adm-import-report" role="status"><h3>{state.done ? 'Đã nhập danh mục' : report.valid ? 'Bản xem trước hợp lệ' : 'Dữ liệu cần chỉnh sửa'}</h3><p>Thêm mới: {report.created} · Cập nhật: {report.updated} · Giữ nguyên: {report.unchanged} · Dòng lỗi: {report.rejected || 0}</p><ul>{report.errors?.map(row => <li key={row.row}>Dòng {row.row}: {Object.values(row.fields).flat().join(" ")}</li>)}</ul></div>}{state.error && <p className="error-banner" role="alert">{state.error}</p>}<div className="adm-action-strip"><button className="secondary-button" disabled={!file || state.busy || state.done} onClick={() => run(false)}>Kiểm tra và xem trước</button><button className="solid-button" disabled={!report?.valid || state.busy || state.done} onClick={() => run(true)}>{state.busy ? 'Đang xử lý…' : 'Xác nhận nhập'}</button></div></div></Modal>
}
