// src/utils/request.ts

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string) || 'http://localhost:8000'

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  data?: unknown
  header?: Record<string, string>
}

export function request<T>(url: string, options: RequestOptions = {}): Promise<T> {
  return new Promise((resolve, reject) => {
    const token = uni.getStorageSync('access_token') as string | undefined
    const header: Record<string, string> = {
      'Content-Type': 'application/json',
      ...options.header,
    }
    if (token) {
      header['Authorization'] = `Bearer ${token}`
    }

    uni.request({
      url: `${BASE_URL}${url}`,
      method: options.method || 'GET',
      data: options.data,
      header,
      success(res) {
        if (res.statusCode === 401) {
          // 401：清 token + toast；不主动 reLaunch（避免在 tab 页面触发路由冲突
          // 导致 "routeDone with a webviewId X is not found"）。由用户主动点登录。
          uni.removeStorageSync('access_token')
          uni.removeStorageSync('refresh_token')
          uni.showToast({ title: '登录已过期，请回首页登录', icon: 'none', duration: 3000 })
          reject(new Error('未登录或登录已过期'))
          return
        }
        if (typeof res.data !== 'object' || res.data === null) {
          reject(new Error(`无法解析响应 (HTTP ${res.statusCode})`))
          return
        }
        const body = res.data as { code: number; message: string; data: T }
        if (res.statusCode < 200 || res.statusCode >= 300) {
          reject(new Error(body.message || `HTTP ${res.statusCode}`))
          return
        }
        if (body.code !== 200) {
          reject(new Error(body.message || '请求失败'))
          return
        }
        resolve(body.data)
      },
      fail(err) {
        reject(new Error(err.errMsg || '网络请求失败'))
      },
    })
  })
}
