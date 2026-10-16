import axios from 'axios'

const http = axios.create({
  baseURL: '/api/v1',
  timeout: 30000
})

http.interceptors.request.use((config) => {
  const token = localStorage.getItem('opc_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 统一解包 {code, message, data}
http.interceptors.response.use(
  (response) => {
    const body = response.data
    if (body && typeof body === 'object' && 'code' in body) {
      if (body.code !== 0) {
        return Promise.reject(new Error(body.message || '请求失败'))
      }
      return body.data
    }
    return body
  },
  (error) => {
    const body = error.response && error.response.data
    if (body && body.message) {
      error.message = body.message
    }
    if (error.response && error.response.status === 401) {
      localStorage.removeItem('opc_token')
    }
    return Promise.reject(error)
  }
)

// 文件下载专用客户端（不走解包拦截；asset.url 为含 /api/v1 的完整路径，故不设 baseURL）
const fileClient = axios.create({ timeout: 120000 })

export async function fetchFileBlob(path) {
  const token = localStorage.getItem('opc_token')
  const response = await fileClient.get(path, {
    responseType: 'blob',
    headers: token ? { Authorization: `Bearer ${token}` } : {}
  })
  return response.data
}

export async function downloadFile(path, filename) {
  const blob = await fetchFileBlob(path)
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename || 'download'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

// ---------- 认证 ----------
export async function login(payload) {
  const response = await axios.post('/api/v1/auth/login', payload)
  return response.data.data
}

// ---------- 用户 ----------
export function getMe() {
  return http.get('/users/me')
}

// ---------- 管理后台（admin） ----------
export function listUsers(params) {
  return http.get('/users', { params })
}

export function createUser(payload) {
  return http.post('/users', payload)
}

export function updateUserStatus(userId, payload) {
  return http.patch(`/users/${userId}/status`, payload)
}

export function createCourse(payload) {
  return http.post('/courses', payload)
}

// ---------- 作品 ----------
export function listWorks(params) {
  return http.get('/works', { params })
}

export function createWork(payload) {
  return http.post('/works', payload)
}

export function getWork(id) {
  return http.get(`/works/${id}`)
}

export function generateWork(id, payload) {
  return http.post(`/works/${id}/generate`, payload)
}

export function uploadAsset(id, formData) {
  return http.post(`/works/${id}/assets`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

export function saveTextAsset(id, payload) {
  return http.post(`/works/${id}/text-assets`, payload)
}

export function submitAiDeclare(id, payload) {
  return http.post(`/works/${id}/ai-declare`, payload)
}

export function createPublishParams(id, payload) {
  return http.post(`/works/${id}/publish-params`, payload)
}

export function submitRevision(id, payload) {
  return http.post(`/works/${id}/revision`, payload)
}

// ---------- 异步任务 ----------
export function getTask(taskId) {
  return http.get(`/agent-tasks/${taskId}`)
}

// ---------- 实训任务 ----------
export function listTasks() {
  return http.get('/tasks')
}

export function createTask(payload) {
  return http.post('/tasks', payload)
}

export function getTaskDetail(taskId) {
  return http.get(`/tasks/${taskId}`)
}

export function submitTask(taskId, payload) {
  return http.post(`/tasks/${taskId}/submit`, payload)
}

export function closeTask(taskId) {
  return http.post(`/tasks/${taskId}/close`)
}

export function listSubmissions(taskId) {
  return http.get(`/tasks/${taskId}/submissions`)
}

// ---------- 批改与能力 ----------
export function reviewWork(workId, payload) {
  return http.post(`/works/${workId}/review`, payload)
}

export function getWorkReview(workId) {
  return http.get(`/works/${workId}/review`)
}

export function getStudentAbility(studentId) {
  return http.get(`/ability/students/${studentId}`)
}

export function getClassAbility(classId) {
  return http.get(`/ability/classes/${classId}`)
}

// ---------- 课程 ----------
export function listCourses() {
  return http.get('/courses')
}

// ---------- 工单 ----------
export function listOrders() {
  return http.get('/orders')
}

export function createOrder(payload) {
  return http.post('/orders', payload)
}

export function getOrder(orderId) {
  return http.get(`/orders/${orderId}`)
}

export function verifyOrder(orderId, payload) {
  return http.post(`/orders/${orderId}/verify`, payload)
}

export function bidOrder(orderId, payload) {
  return http.post(`/orders/${orderId}/bid`, payload)
}

export function listBids(orderId) {
  return http.get(`/orders/${orderId}/bids`)
}

export function awardOrder(orderId, bidId) {
  return http.post(`/orders/${orderId}/award`, { bid_id: bidId })
}

export default http
