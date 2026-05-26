import { defineStore } from 'pinia'
import { ref } from 'vue'
import { wxLogin } from '@/api/auth'
import type { UserProfileOut } from '@/types/api'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string>(uni.getStorageSync('access_token') || '')
  const user = ref<UserProfileOut | null>(null)

  function isLoggedIn(): boolean {
    return !!token.value
  }

  async function login(): Promise<void> {
    // Step 1: 获取微信 code
    const code = await new Promise<string>((resolve, reject) => {
      uni.login({
        provider: 'weixin',
        success: (res) => resolve(res.code),
        fail: (err) => reject(new Error(err.errMsg || '微信登录失败')),
      })
    })
    // Step 2: 换取 JWT (TokenResponse has access_token + refresh_token)
    const tokenResp = await wxLogin(code)
    token.value = tokenResp.access_token
    uni.setStorageSync('access_token', tokenResp.access_token)
    uni.setStorageSync('refresh_token', tokenResp.refresh_token)
    // user profile will be fetched separately when needed (GET /users/me)
  }

  function logout(): void {
    token.value = ''
    user.value = null
    uni.removeStorageSync('access_token')
    uni.removeStorageSync('refresh_token')
  }

  return { token, user, isLoggedIn, login, logout }
})
