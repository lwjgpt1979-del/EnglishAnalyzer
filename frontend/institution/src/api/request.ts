import axios from 'axios'
import { ElMessage } from 'element-plus'
import type { ApiResponse } from '../types'

const request = axios.create({
  baseURL: '/api/v1',
  timeout: 20000,
})

// 请求拦截：注入 Bearer token
request.interceptors.request.use((config) => {
  const token = localStorage.getItem('institution_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截：解包 {code,message,data}；401 → 清 token 跳登录
request.interceptors.response.use(
  (resp) => {
    const body = resp.data as ApiResponse<unknown>
    if (body && typeof body.code === 'number' && body.code !== 200) {
      ElMessage.error(body.message || '请求失败')
      return Promise.reject(new Error(body.message || '请求失败'))
    }
    return resp
  },
  (error) => {
    const status = error?.response?.status
    const url: string = error?.config?.url || ''
    const serverMsg = error?.response?.data?.message
    const isLoginReq = url.includes('/admin/auth/login')
    if (status === 401 && !isLoginReq) {
      // 已登录态的请求被拒 → 会话过期，清 token 跳登录
      localStorage.removeItem('institution_token')
      if (location.hash !== '#/login') location.hash = '#/login'
      ElMessage.error('登录已过期，请重新登录')
    } else {
      // 登录失败 或 其它错误 → 展示后端真实信息（如"用户名或密码错误"）
      ElMessage.error(serverMsg || error.message || '网络错误')
    }
    return Promise.reject(error)
  },
)

// 解包辅助：返回 data 字段
export async function unwrap<T>(p: Promise<{ data: ApiResponse<T> }>): Promise<T> {
  const resp = await p
  return resp.data.data
}

export default request
