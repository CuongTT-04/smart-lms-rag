import { useEffect, useState } from 'react'
import { GraduationCap, UsersRound } from 'lucide-react'
import { courseErrorMessage, listClassroomPeople } from '../services/course.service'

export default function StudentClassroomPeople({ courseId, roomId }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    listClassroomPeople(courseId, roomId, controller.signal).then((people) => { if (!controller.signal.aborted) setData(people) }).catch((err) => { if (!controller.signal.aborted) setError(courseErrorMessage(err)) })
    return () => controller.abort()
  }, [courseId, roomId])
  return <section className="class-people-panel" aria-label="Thành viên lớp học">
    {error && <div className="error-banner" role="alert">{error}</div>}
    {!data && !error && <p role="status">Đang tải thành viên...</p>}
    {data && <>{[['owners', 'Giáo viên phụ trách', GraduationCap], ['students', 'Học viên', UsersRound]].map(([key, label, Icon]) => <section className="class-people-group" key={key} aria-label={label}><h2><Icon size={24} />{label}<span className="join-count">{data[key].length}</span></h2><ul>{data[key].map((person) => <li key={person.id}><span className="member-avatar" aria-hidden="true">{person.name.trim().split(/\s+/).slice(-2).map((word) => word[0]).join('').toUpperCase()}</span><strong>{person.name}</strong>{key === 'owners' && <span className="class-owner-badge">Chủ lớp</span>}</li>)}</ul>{!data[key].length && <p>Chưa có thành viên.</p>}</section>)}</>}
  </section>
}
