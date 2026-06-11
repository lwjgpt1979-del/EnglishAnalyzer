// src/utils/request.ts

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string) || 'http://localhost:8000'

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  data?: unknown
  header?: Record<string, string>
}

/** 底层请求：不做 401 续期，仅回传原始 uni.request 结果。 */
function rawRequest(url: string, options: RequestOptions): Promise<UniApp.RequestSuccessCallbackResult> {
  return new Promise((resolve, reject) => {
    const token = uni.getStorageSync('access_token') as string | undefined
    const header: Record<string, string> = {
      'Content-Type': 'application/json',
      ...options.header,
    }
    if (token) header['Authorization'] = `Bearer ${token}`

    uni.request({
      url: `${BASE_URL}${url}`,
      method: options.method || 'GET',
      data: options.data,
      header,
      success: resolve,
      fail: (err) => reject(new Error(err.errMsg || '网络请求失败')),
    })
  })
}

// 并发锁：多个请求同时 401 时只触发一次刷新，其余等待同一个 Promise。
let refreshPromise: Promise<boolean> | null = null

/** 用 refresh_token 静默换取新 access_token，成功写入存储并返回 true。 */
function refreshAccessToken(): Promise<boolean> {
  if (refreshPromise) return refreshPromise
  refreshPromise = (async () => {
    const rt = uni.getStorageSync('refresh_token') as string | undefined
    if (!rt) return false
    try {
      const res = await rawRequest('/api/v1/auth/refresh', {
        method: 'POST',
        data: { refresh_token: rt },
      })
      const body = res.data as { code?: number; data?: { access_token?: string; refresh_token?: string } }
      if (res.statusCode !== 200 || body?.code !== 200 || !body?.data?.access_token) return false
      uni.setStorageSync('access_token', body.data.access_token)
      if (body.data.refresh_token) uni.setStorageSync('refresh_token', body.data.refresh_token)
      return true
    } catch {
      return false
    }
  })()
  refreshPromise.finally(() => { refreshPromise = null })
  return refreshPromise
}

function clearSessionAndNotify() {
  uni.removeStorageSync('access_token')
  uni.removeStorageSync('refresh_token')
  uni.showToast({ title: '登录已过期，请回首页登录', icon: 'none', duration: 3000 })
}

export async function request<T>(url: string, options: RequestOptions = {}): Promise<T> {
  let res = await rawRequest(url, options)

  // 401 且非刷新接口本身 → 尝试静默续期并重试一次
  if (res.statusCode === 401 && !url.includes('/auth/refresh')) {
    const ok = await refreshAccessToken()
    if (ok) {
      res = await rawRequest(url, options)  // 带新 token 重试一次
    } else {
      clearSessionAndNotify()
      throw new Error('未登录或登录已过期')
    }
  }

  // 重试后仍 401（或刷新接口自身 401）→ 判定会话失效
  if (res.statusCode === 401) {
    clearSessionAndNotify()
    throw new Error('未登录或登录已过期')
  }

  if (typeof res.data !== 'object' || res.data === null) {
    throw new Error(`无法解析响应 (HTTP ${res.statusCode})`)
  }
  const body = res.data as { code: number; message: string; data: T }
  if (res.statusCode < 200 || res.statusCode >= 300) {
    throw new Error(body.message || `HTTP ${res.statusCode}`)
  }
  if (body.code !== 200) {
    throw new Error(body.message || '请求失败')
  }
  return body.data
}
