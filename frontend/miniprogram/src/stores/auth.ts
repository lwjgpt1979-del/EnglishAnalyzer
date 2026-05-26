import { defineStore } from 'pinia'
import { ref } from 'vue'
import { wxLogin } from '@/api/auth'
import type { UserProfileOut } from '@/types/api'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string>(uni.getStorageSync('access_token') || '')
  const user = ref<UserProfileOut | null>(null)
  const loginLoading = ref(false)

  function isLoggedIn(): boolean {
    // NOTE: only checks for token existence, not expiry.
    // An expired token will cause a 401 → auto-reLaunch on first API call.
    // TODO: add silent refresh via refresh_token when token expiry check is added.
    return !!token.value
  }

  async function login(): Promise<void> {
    // Guard against concurrent login calls (e.g. double-tap)
    if (loginLoading.value) return
    loginLoading.value = true
    try {
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
      // user profile fetched separately when needed (GET /users/me)
    } finally {
      loginLoading.value = false
    }
  }

  function logout(): void {
    token.value = ''
    user.value = null
    uni.removeStorageSync('access_token')
    uni.removeStorageSync('refresh_token')
  }

  return { token, user, loginLoading, isLoggedIn, login, logout }
})
