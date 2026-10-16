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

export async function login(payload) {
  const response = await axios.post('/api/v1/auth/login', payload)
  return response.data.data
}

export default http
