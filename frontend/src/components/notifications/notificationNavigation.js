import { getCourse, listClassrooms } from '../../services/course.service'

export async function openNotificationTarget(target, user, signal) {
  if (signal?.aborted) return
  if (target.admin) {
    return
  }
  const base = window.history.state?.ohayoNavigation
  const values = { ...(base?.owner === user.id ? base.values : {}) }
  values['notifications.navigation'] = crypto.randomUUID()
  values['notifications.document'] = target.document_id && !target.session_id ? target : null
  const teacher = user.role === 'TEACHER'
  const role = teacher ? 'teacher' : 'student'
  if (target.enrollment) {
    values['student.view'] = 'join'; values['student.classroom'] = null; values['student.course'] = null
  } else if (target.course_id) {
    const course = await getCourse(target.course_id, signal)
    if (target.classroom_id) {
      if (teacher) {
        const rooms = await listClassrooms(course.id, signal)
        const room = rooms.find((row) => row.id === target.classroom_id)
        if (!room) throw new Error('Lớp học không còn khả dụng.')
        values['teacher.view'] = 'classrooms'; values['teacher.classroom'] = { course, room }; values['teacher.course'] = null
      } else {
        values['student.view'] = 'join'; values['student.course'] = null
        values['student.classroom'] = { course_id: course.id, classroom_id: target.classroom_id, classroom_name: target.classroom_name || '' }
      }
      values[`classroom.${target.classroom_id}.tab`] = target.session_id ? 'sessions' : 'news'
      values[`classroom.${target.classroom_id}.session`] = target.session_id || null
      values[`classroom.${target.classroom_id}.focus`] = target.announcement_id ? target : null
    } else {
      values[`${role}.view`] = 'courses'; values[`${role}.course`] = course.id; values[`${role}.classroom`] = null
      if (target.document_id && !teacher) values[`student.course.${course.id}.classroom`] = null
    }
    if (target.session_id) {
      const prefix = `session.${target.session_id}`
      values[`${prefix}.section`] = target.video_id ? 'videos' : target.assessment_id ? 'assignments' : 'materials'
      if (target.video_id) values[`${prefix}.video`] = target.video_id
      if (target.assessment_id) values[`${prefix}.assessment`] = target.assessment_id
      if (target.assessment_id) values[`assessment.${target.assessment_id}.attempt`] = target.attempt_id || null
      if (target.document_id) values[`${prefix}.document`] = target.document_id
    }
    // Fetching the target itself is authoritative; no external URL is accepted.
  }
  if (signal?.aborted) return
  const navigation = { owner: user.id, values }
  window.history.pushState({ ...window.history.state, ohayoNavigation: navigation }, '')
  try { window.sessionStorage.setItem(`ohayo.navigation.${user.id}`, JSON.stringify(navigation)) } catch { /* History still works. */ }
  window.dispatchEvent(new PopStateEvent('popstate'))
  window.scrollTo({ top: 0, behavior: 'instant' })
}

