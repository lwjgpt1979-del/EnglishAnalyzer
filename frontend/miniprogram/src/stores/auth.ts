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
    // 仅检查 token 是否存在，不校验过期。
    // 过期(401)由 utils/request 拦截层用 refresh_token 静默续期并重试一次，
    // 续期失败才清会话并提示重新登录。
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
      // 携带获客渠道（§5.5）：仅新用户后端首次写入，老用户忽略
      const channel = (uni.getStorageSync('acq_channel') as string) || undefined
      const tokenResp = await wxLogin(code, channel)
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

  /**
   * 冷启动 / 刷新时恢复用户：已有 token 但 user 为空则拉 /me 填充。
   * token 失效则静默忽略，后续业务接口 401 时再统一处理。
   */
  async function restore(): Promise<void> {
    if (!token.value || user.value) return
    try {
      user.value = await getMyProfile()
    } catch (e) {
      console.warn('[auth.restore] fetch /me failed:', e)
    }
  }

  function logout(): void {
    token.value = ''
    user.value = null
    uni.removeStorageSync('access_token')
    uni.removeStorageSync('refresh_token')
  }

  return { token, user, loginLoading, isLoggedIn, login, restore, logout }
})
