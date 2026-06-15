<!-- 统一会员墙：顶档配额用尽→买加量包；否则引导升级 -->
<template>
  <view v-if="open" class="pw-mask" @tap.self="$emit('close')">
    <view class="pw-card">
      <text class="pw-emoji">{{ emoji }}{{ isAddon ? '⚡' : '🔒' }}</text>
      <text class="pw-title">{{ isAddon ? '本周期次数已用完' : (title || feature?.title || '会员专享功能') }}</text>
      <text class="pw-desc">{{ desc }}</text>
      <button v-if="isAddon" class="pw-btn" :loading="paying" @tap="buyAddon">
        购买加量包 {{ feature?.addon_pack?.pack_size }} 次 · ¥{{ ((feature?.addon_pack?.price_fen || 0) / 100).toFixed(1) }}
      </button>
      <button v-else class="pw-btn" @tap="goMembership">{{ ctaText }}</button>
      <text class="pw-close" @tap="$emit('close')">暂不</text>
    </view>

    <PayConfirm :open="showConfirm" :plan="addonPlan" @close="showConfirm = false" @confirmed="onConfirmed" />
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { requiredTierText, useEntitlementsStore } from '@/stores/entitlements'
import type { FeatureEntitlement } from '@/api/entitlements'
import { createOrder, payOrder } from '@/api/orders'
import PayConfirm from '@/components/PayConfirm.vue'

const props = defineProps<{
  open: boolean
  feature?: FeatureEntitlement | null
  title?: string
  emoji?: string
}>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'purchased'): void }>()

const ent = useEntitlementsStore()
const paying = ref(false)
const showConfirm = ref(false)
const isAddon = computed(() => !!props.feature?.can_buy_addon && !!props.feature?.addon_pack)
const addonPlan = computed(() => ({
  name: `${props.feature?.title || '功能'}加量包 ${props.feature?.addon_pack?.pack_size || ''} 次`,
  amountFen: props.feature?.addon_pack?.price_fen || 0,
}))
const tierText = computed(() => requiredTierText(props.feature?.required_tiers))
const ctaText = computed(() => `去开通${tierText.value}会员`)
const emoji = computed(() => props.emoji || '✨')
const desc = computed(() => {
  if (isAddon.value) return '已是最高档会员，购买加量包即可继续使用（余额永久有效）。'
  const q = props.feature
  if (q && q.mode === 'quota' && (q.quota_left ?? 0) <= 0) {
    return `本周期次数已用完，升级到 ${tierText.value} 可获更多次数。`
  }
  return `开通 ${tierText.value} 会员后即可使用此功能。`
})

function goMembership() {
  uni.navigateTo({ url: '/pages/membership/buy' })
}

function buyAddon() {
  if (!props.feature || paying.value) return
  showConfirm.value = true
}

async function onConfirmed(logId: string) {
  showConfirm.value = false
  if (!props.feature || paying.value) return
  paying.value = true
  try {
    const order = await createOrder({
      tier: ent.tier, order_type: 'new', addon_feature_key: props.feature.key,
      payment_confirm_log_id: logId,
    })
    // #ifdef MP-WEIXIN
    const params = await payOrder(order.id)
    await new Promise<void>((resolve, reject) => {
      wx.requestPayment({
        timeStamp: params.timeStamp, nonceStr: params.nonceStr, package: params.package,
        signType: params.signType as 'RSA', paySign: params.paySign,
        success: () => resolve(), fail: (e: unknown) => reject(e),
      })
    })
    uni.showToast({ title: '购买成功', icon: 'success' })
    await ent.fetch()
    emit('purchased')
    emit('close')
    // #endif
    // #ifndef MP-WEIXIN
    uni.showToast({ title: '请在微信小程序内购买', icon: 'none' })
    // #endif
  } catch (e) {
    uni.showToast({ title: (e as Error).message || '购买失败', icon: 'none' })
  } finally {
    paying.value = false
  }
}
</script>

<style scoped>
.pw-mask { position: fixed; inset: 0; background: rgba(0,0,0,.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.pw-card { width: 560rpx; background: var(--c-bg-card); border-radius: var(--r-lg); padding: 44rpx 32rpx; display: flex; flex-direction: column; align-items: center; gap: 16rpx; }
.pw-emoji { font-size: 72rpx; }
.pw-title { font-size: 34rpx; font-weight: 800; color: var(--c-ink); text-align: center; }
.pw-desc { font-size: 26rpx; color: var(--c-text-second); text-align: center; line-height: 1.6; }
.pw-btn { width: 100%; margin-top: 8rpx; background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-pill); font-size: 30rpx; font-weight: 700; height: 80rpx; line-height: 80rpx; }
.pw-close { font-size: 26rpx; color: var(--c-text-hint); padding: 8rpx; }
</style>
