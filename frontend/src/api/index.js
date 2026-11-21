import axios from 'axios'

const http = axios.create({
  baseURL: '/api/v1',
  // 真实 AI 调用（剧本/分镜/翻译/发布参数）为同步接口，耗时 5-30s，
  // 叠加 JSON 修复重试可能翻倍——30s 会误报超时（mock 模式 <1s 故不易暴露）。
  timeout: 120000
})

http.interceptors.request.use((config) => {
  const token = localStorage.getItem('opc_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// ---------- P0-03：401 自动刷新（单飞）+ 原请求重放 ----------
// 并发 401 共享同一个刷新 Promise，只发一次 /auth/refresh；
// 刷新成功重放原请求，失败才清登录态跳登录页。
let refreshing = null

function getRefreshToken() {
  return localStorage.getItem('opc_refresh_token') || ''
}

function clearAuthAndRedirect() {
  localStorage.removeItem('opc_token')
  localStorage.removeItem('opc_refresh_token')
  if (!window.location.pathname.startsWith('/login')) {
    window.location.assign('/login')
  }
}

async function refreshAccessToken() {
  const refresh_token = getRefreshToken()
  if (!refresh_token) {
    throw new Error('no refresh token')
  }
  // POST /auth/refresh 走原生 axios，避免被本文件的 401 拦截器递归捕获
  const response = await axios.post('/api/v1/auth/refresh', { refresh_token })
  const body = response.data
  if (body && body.code === 0 && body.data && body.data.access_token) {
    localStorage.setItem('opc_token', body.data.access_token)
    return body.data.access_token
  }
  throw new Error('refresh rejected')
}

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
  async (error) => {
    const config = error.config || {}
    const body = error.response && error.response.data
    if (body && body.message) {
      error.message = body.message
    }
    // P0-10：后端响应自带 X-Request-ID，透出到提示里便于报障定位
    const requestId = error.response && error.response.headers && error.response.headers['x-request-id']
    if (requestId) {
      error.requestId = requestId
      error.message = `${error.message}（追踪码 ${requestId}）`
    }

    const isAuthRequest =
      typeof config.url === 'string' &&
      (config.url.includes('/auth/login') || config.url.includes('/auth/refresh'))

    if (error.response && error.response.status === 401 && !config._retried && !isAuthRequest) {
      if (!refreshing) {
        refreshing = refreshAccessToken().finally(() => {
          refreshing = null
        })
      }
      try {
        const newToken = await refreshing
        config._retried = true
        config.headers = { ...(config.headers || {}), Authorization: `Bearer ${newToken}` }
        return http.request(config)
      } catch {
        // 刷新失败（token 过期/账号被禁）→ 清登录态回登录页
        clearAuthAndRedirect()
        return Promise.reject(error)
      }
    }

    if (error.response && error.response.status === 401) {
      clearAuthAndRedirect()
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
  // 登录失败要透出后端中文 message（axios 默认 error.message 是英文状态码描述）
  try {
    const response = await axios.post('/api/v1/auth/login', payload)
    return response.data.data
  } catch (err) {
    const message = err.response && err.response.data && err.response.data.message
    throw new Error(message || '登录失败，请检查网络或稍后重试')
  }
}

// ---------- 系统健康（管理员，P0-10；/health 不在 /api/v1 下，走原生 axios 不解包） ----------
export async function getSystemHealth() {
  const response = await axios.get('/health')
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

// ---------- 用量分析（教师/管理员） ----------
export function getUsageStats(params) {
  return http.get('/analytics/usage', { params })
}

// ---------- 智能体会话（流水线运行记录） ----------
export function listAgentSessions(params) {
  return http.get('/agents/sessions', { params })
}

// ---------- 智能体直调（数据复盘/优化建议/人才匹配/AI 备课） ----------
export function invokeAgent(type, payload) {
  return http.post(`/agents/${type}/invoke`, payload)
}

// ---------- 能力预警（教师/管理员） ----------
export function getAbilityWarnings(params) {
  return http.get('/ability/warnings', { params })
}

// ---------- 作品集分享 ----------
export function createPortfolioShare() {
  return http.post('/portfolio/share')
}

export function getPublicPortfolio(token) {
  return http.get(`/portfolio/public/${token}`)
}

export default http
