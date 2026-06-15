import { defineStore } from 'pinia'
import { ref } from 'vue'
import { request } from '@/utils/request'

// 兜底默认（后端取价失败时用）；项目名唯一真源在后端 system_configs.branding
export const APP_NAME_DEFAULT = 'engGramer'

export const useBrandingStore = defineStore('branding', () => {
  const appName = ref(APP_NAME_DEFAULT)
  const slogan = ref('')

  async function fetch() {
    try {
      const d = await request<{ app_name: string; slogan: string }>(
        '/api/v1/config/branding', { method: 'GET' },
      )
      if (d?.app_name) appName.value = d.app_name
      slogan.value = d?.slogan || ''
    } catch { /* 失败保留默认，不影响使用 */ }
  }

  return { appName, slogan, fetch }
})
