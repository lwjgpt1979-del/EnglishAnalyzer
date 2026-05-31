import { defineStore } from 'pinia'
import { ref } from 'vue'
import { wxLogin } from '@/api/auth'
import { getMyProfile } from '@/api/users'
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
          success: (res) => {
            if (!res.code) {
              reject(new Error('微信未返回 code：可能未在开发者工具登录微信账号'))
            } else {
              resolve(res.code)
            }
          },
          fail: (err) => reject(new Error(err.errMsg || '微信登录失败')),
        })
      })
      // Step 2: 换取 JWT (TokenResponse has access_token + refresh_token)
      const tokenResp = await wxLogin(code)
      token.value = tokenResp.access_token
      uni.setStorageSync('access_token', tokenResp.access_token)
      uni.setStorageSync('refresh_token', tokenResp.refresh_token)
      uni.showToast({ title: '登录成功', icon: 'success' })
      // Step 3: 拉 /me 填 auth.user（profile_completed 等首页拦截器要用）
      try {
        user.value = await getMyProfile()
        // 新用户 profile_completed=false → 立即跳完善资料（不依赖首页 onMounted）
        if (user.value && !user.value.profile_completed) {
          setTimeout(() => uni.redirectTo({ url: '/pages/auth/complete-profile' }), 600)
        }
      } catch (e) {
        console.warn('[auth.login] fetch /me failed:', e)
        // 不抛——token 有但 user 拉失败，下次 API 调用 401 时再处理
      }
    } catch (e) {
      // 把错误用 toast 暴露出来——之前用 try/finally 静默吞，调试困难
      const msg = (e as Error).message || '登录失败'
      console.error('[auth.login] failed:', e)
      uni.showToast({ title: msg, icon: 'none', duration: 4000 })
      throw e  // 仍然抛出给调用方
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
