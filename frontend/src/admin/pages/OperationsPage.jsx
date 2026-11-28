import useAdminData from '../hooks/useAdminData'
import { Feedback, Status } from '../components/AdminControls'
import { dateText } from '../components/admin-format'

const generationErrors = {
  GENERATION_UNAVAILABLE: 'Dịch vụ mô hình chưa sẵn sàng',
  GENERATION_INCOMPLETE_ANSWER: 'Mô hình trả lời thiếu nội dung',
  GENERATION_TIMEOUT: 'Mô hình xử lý quá thời gian',
  GENERATION_CONFIG_MISMATCH: 'Cấu hình mô hình chưa đồng bộ',
  INVALID_GENERATION: 'Câu trả lời không hợp lệ',
  OUTPUT_LIMIT_REACHED: 'Câu trả lời vượt giới hạn độ dài',
  INCOMPLETE_GENERATION: 'Quá trình sinh chưa hoàn tất',
  AI_QUOTA_EXCEEDED: 'Vượt hạn mức sử dụng',
  AI_QUEUE_FULL: 'Hàng đợi đã đầy', AI_QUEUE_TIMEOUT: 'Hết thời gian chờ',
  AI_NOT_ALLOWED: 'Yêu cầu bị chặn theo quy tắc',
  SCOPE_CHANGED: 'Phạm vi học liệu đã thay đổi', NOT_FOUND: 'Nguồn không còn khả dụng',
}

export default function OperationsPage() {
  const resource = useAdminData('health/')
  const data = resource.data
  const ai = data?.ai || { gateway: { status: 'UNKNOWN' }, queue: { running: 'Chưa có dữ liệu', waiting: 'Chưa có dữ liệu' }, generation: {}, limits: {}, outcomes: {}, errors: {} }
  const status = ai?.gateway?.status
  return <><div className="adm-page-heading"><div><p className="adm-eyebrow">TÌNH TRẠNG DỊCH VỤ</p><h1>Vận hành</h1><p>Tín hiệu thực tế từ trợ lý Ayo và quá trình xử lý học liệu.</p></div><button className="secondary-button" onClick={resource.refresh}>Cập nhật trạng thái</button></div><Feedback resource={resource}>{data && <><div className="adm-two-columns"><section className="adm-panel"><h2>Trợ lý Ayo</h2><Status tone={status === 'READY' ? 'good' : 'muted'}>{({ READY: 'Sẵn sàng', DRAINING: 'Đang dừng tiếp nhận', UNAVAILABLE: 'Mất kết nối' })[status] || 'Chưa có dữ liệu'}</Status><dl className="adm-details"><div><dt>Đang xử lý</dt><dd>{ai.queue.running}</dd></div><div><dt>Đang chờ</dt><dd>{ai.queue.waiting}</dd></div><div><dt>Lượt gọi mô hình (24 giờ)</dt><dd>{ai.generation.gateway_calls ?? 'Chưa có dữ liệu'}</dd></div><div><dt>Lỗi kết nối</dt><dd>{ai.gateway.code ? generationErrors[ai.gateway.code] || 'Chưa kết nối được dịch vụ' : 'Không ghi nhận'}</dd></div></dl></section><section className="adm-panel"><h2>Giới hạn đang áp dụng</h2><dl className="adm-details">{Object.entries(ai.limits).map(([key, value]) => <div key={key}><dt>{({ hourly_student: 'Lượt / giờ / học viên', concurrent: 'Sinh đồng thời', waiting: 'Tác vụ chờ tối đa', queue_seconds: 'Thời gian chờ (giây)' })[key] || key}</dt><dd>{value}</dd></div>)}</dl><p className="adm-info">Mỗi bước sinh được tiếp nhận tính một lượt. Đọc lại kết quả không tạo thêm lượt sinh.</p></section></div><section className="adm-panel"><h2>Xử lý học liệu</h2>{data.ingestion === null ? <p>Chưa có quyền xem tín hiệu xử lý học liệu.</p> : !data.ingestion.states.length ? <p>Chưa có dữ liệu xử lý học liệu.</p> : <><div className="adm-mini-stats">{data.ingestion.states.map(row => <div key={row.status}><span>{({ QUEUED: 'Đang chờ', RUNNING: 'Đang xử lý', SUCCEEDED: 'Hoàn tất', FAILED: 'Thất bại', CANCELLED: 'Đã hủy' })[row.status] || row.status}</span><strong>{row.count}</strong></div>)}</div><p>Lượt được tạo gần nhất: {dateText(data.ingestion.latest)}</p></>}</section><section className="adm-panel"><h2>Kết quả gọi mô hình trong 24 giờ</h2><p>Lượt gọi mô hình có thể thất bại nhưng câu trả lời được phục hồi bằng học liệu. Hai kết quả được ghi nhận riêng.</p><div className="adm-summary-row"><span>Đã phục hồi từ học liệu</span><strong>{ai.generation.recovered_calls ?? 'Chưa có dữ liệu'}</strong></div><div className="adm-two-columns"><div>{Object.entries(ai.outcomes).length ? Object.entries(ai.outcomes).map(([key, count]) => <div className="adm-summary-row" key={key}><span>{({ COMPLETED: 'Hoàn tất', FAILED: 'Thất bại', REJECTED: 'Bị giới hạn', QUEUED: 'Đang chờ', RUNNING: 'Đang sinh' })[key] || key}</span><strong>{count}</strong></div>) : <p>{data.ai ? 'Chưa có lượt được ghi nhận.' : 'Chưa có dữ liệu kết quả.'}</p>}</div><div>{Object.entries(ai.errors).length ? Object.entries(ai.errors).map(([key, count]) => <div className="adm-summary-row" key={key}><span title={key}>{generationErrors[key] || 'Lỗi xử lý câu trả lời'}</span><strong>{count}</strong></div>) : <p>{data.ai ? 'Không có mã lỗi được ghi nhận.' : 'Chưa có dữ liệu lỗi.'}</p>}</div></div></section><p className="adm-info">Cập nhật {dateText(data.as_of)}. Không suy ra dịch vụ sẵn sàng khi thiếu tín hiệu.</p></>}</Feedback></>
}
