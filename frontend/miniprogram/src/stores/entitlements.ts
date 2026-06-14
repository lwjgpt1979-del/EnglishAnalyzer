import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getMyEntitlements, type FeatureEntitlement } from '@/api/entitlements'

const LOCKED: FeatureEntitlement = { key: '', allowed: false, mode: 'deny', required_tiers: [] }

export const useEntitlementsStore = defineStore('entitlements', () => {
  const tier = ref('free')
  const map = ref<Record<string, FeatureEntitlement>>({})
  const loaded = ref(false)
  let _inflight: Promise<void> | null = null

  async function fetch(): Promise<void> {
    try {
      const r = await getMyEntitlements()
      tier.value = r.tier
      map.value = r.features || {}
      loaded.value = true
    } catch { /* 失败时保持默认(锁) */ }
  }
  /** 确保已加载（并发去重）；登录后或进受限页前调用 */
  async function ensure(): Promise<void> {
    if (loaded.value) return
    if (!_inflight) _inflight = fetch().finally(() => { _inflight = null })
    return _inflight
  }
  function feature(key: string): FeatureEntitlement {
    return map.value[key] || { ...LOCKED, key }
  }
  function can(key: string): boolean {
    return !!map.value[key]?.allowed
  }
  function reset(): void {
    map.value = {}; loaded.value = false; tier.value = 'free'
  }
  return { tier, map, loaded, fetch, ensure, feature, can, reset }
})

const TIER_LABEL: Record<string, string> = { basic: '基础', pro: 'Pro', promax: 'ProMax' }
/** 把 required_tiers 显示成「升级到 X」文案（取最低可解锁档位）。 */
export function requiredTierText(tiers?: string[]): string {
  const t = (tiers || []).filter(x => x !== 'free')
  if (!t.length) return '会员'
  return TIER_LABEL[t[0]] || t[0]
}
