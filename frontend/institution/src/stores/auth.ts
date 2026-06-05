import { defineStore } from 'pinia'
import { ref } from 'vue'
import request, { unwrap } from '../api/request'
import type { TokenResponse } from '../types'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string>(localStorage.getItem('institution_token') || '')

  function isLoggedIn(): boolean {
    return !!token.value
  }

  async function login(username: string, password: string): Promise<void> {
    const data = await unwrap<TokenResponse>(
      request.post('/institution/auth/login', { username, password }),
    )
    token.value = data.access_token
    localStorage.setItem('institution_token', data.access_token)
  }

  function logout(): void {
    token.value = ''
    localStorage.removeItem('institution_token')
  }

  return { token, isLoggedIn, login, logout }
})
