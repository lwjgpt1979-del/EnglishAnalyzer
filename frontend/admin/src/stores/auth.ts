import { defineStore } from 'pinia'
import { ref } from 'vue'
import request, { unwrap } from '../api/request'
import type { TokenResponse } from '../types'

// 解码 JWT payload 取 role（payload 形如 {sub, role, exp}）
function decodeRole(t: string): string {
  try {
    const seg = t.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    const payload = JSON.parse(decodeURIComponent(escape(atob(seg))))
    return payload.role || ''
  } catch {
    return ''
  }
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string>(localStorage.getItem('admin_token') || '')
  const role = ref<string>(localStorage.getItem('admin_role') || '')

  function isLoggedIn(): boolean {
    return !!token.value
  }

  async function login(username: string, password: string): Promise<void> {
    const data = await unwrap<TokenResponse>(
      request.post('/admin/auth/login', { username, password }),
    )
    token.value = data.access_token
    localStorage.setItem('admin_token', data.access_token)
    role.value = decodeRole(data.access_token)
    localStorage.setItem('admin_role', role.value)
  }

  function logout(): void {
    token.value = ''
    role.value = ''
    localStorage.removeItem('admin_token')
    localStorage.removeItem('admin_role')
  }

  return { token, role, isLoggedIn, login, logout }
})
