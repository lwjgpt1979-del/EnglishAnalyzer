import { reactive } from 'vue'
import { getBranding } from './api/admin'

// 项目名唯一真源在后端；此处为响应式缓存 + 兜底默认
export const branding = reactive({ app_name: 'engGramer', slogan: '' })

export async function loadBranding(): Promise<void> {
  try {
    const d = await getBranding()
    if (d?.app_name) branding.app_name = d.app_name
    branding.slogan = d?.slogan || ''
    document.title = branding.app_name + ' 运营后台'
  } catch { /* 失败保留默认 */ }
}
