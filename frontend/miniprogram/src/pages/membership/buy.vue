<!-- src/pages/membership/buy.vue 通用会员购买（选档位 + 份数，每份6个月）-->
<template>
  <view class="buy-page">
    <view class="head">
      <text class="h-title">开通会员</text>
      <text class="h-sub">每份 {{ pricing?.unit_months || 6 }} 个月 · 买 N 份 = {{ pricing?.unit_months || 6 }}×N 个月</text>
    </view>

    <view v-if="loading" class="tip">加载中…</view>
    <view v-else>
      <!-- 档位 -->
      <view class="tier-row">
        <view v-for="t in tiers" :key="t.key" class="tier" :class="{ active: tier === t.key }" @tap="tier = t.key">
          <text class="tier-name">{{ t.name }}</text>
          <text class="tier-price">¥{{ (t.unit_price_fen / 100).toFixed(0) }}<text class="tier-unit"> /份</text></text>
        </view>
      </view>

      <!-- 份数 -->
      <view class="card qty-card">
        <text class="qty-label">购买份数</text>
        <view class="stepper">
          <text class="step-btn" :class="{ disabled: qty <= 1 }" @tap="dec">−</text>
          <text class="step-val">{{ qty }}</text>
          <text class="step-btn" @tap="inc">＋</text>
        </view>
      </view>

      <!-- 合计 -->
      <view class="card sum-card">
        <view class="sum-row"><text>会员时长</text><text class="sum-v">{{ months }} 个月</text></view>
        <view class="sum-row"><text>合计</text><text class="sum-price">¥{{ (totalFen / 100).toFixed(2) }}</text></view>
      </view>

      <button class="btn-primary" :disabled="paying" @tap="onPay">
        {{ paying ? '支付中…' : `立即开通 · ¥${(totalFen / 100).toFixed(2)}` }}
      </button>
      <text class="note">购买后会员时长自动累加；高档优先生效，到期自动顺延低档。</text>
    </view>

    <PayConfirm :open="showConfirm" :plan="planSnapshot" @close="showConfirm = false" @confirmed="onConfirmed" />
  </view>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getTierPricing, createOrder, payOrder, type TierPricing } from '@/api/orders'
import { useAuthStore } from '@/stores/auth'
import { useEntitlementsStore } from '@/stores/entitlements'
import PayConfirm from '@/components/PayConfirm.vue'

const auth = useAuthStore()
const ent = useEntitlementsStore()
const loading = ref(true)
const paying = ref(false)
const showConfirm = ref(false)
const pricing = ref<TierPricing | null>(null)
const tier = ref('pro')
const qty = ref(1)

const tiers = computed(() => pricing.value?.tiers || [])
const unitFen = computed(() => tiers.value.find(t => t.key === tier.value)?.unit_price_fen || 0)
const months = computed(() => (pricing.value?.unit_months || 6) * qty.value)
const totalFen = computed(() => unitFen.value * qty.value)
const planSnapshot = computed(() => ({
  name: `${tiers.value.find(t => t.key === tier.value)?.name || ''}会员 ×${qty.value} 份`,
  months: months.value, amountFen: totalFen.value, tier: tier.value, quantity: qty.value,
}))

function inc() { if (qty.value < 24) qty.value++ }
function dec() { if (qty.value > 1) qty.value-- }

// 点击购买 → 先弹合规确认弹窗（§4.6），确认成功拿到 log_id 再下单支付
function onPay() {
  if (paying.value) return
  showConfirm.value = true
}

async function onConfirmed(logId: string) {
  showConfirm.value = false
  if (paying.value) return
  paying.value = true
  try {
    const order = await createOrder({
      tier: tier.value, quantity: qty.value, order_type: 'new',
      payment_confirm_log_id: logId,
    })
    // #ifdef MP-WEIXIN
    const p = await payOrder(order.id)
    await new Promise<void>((resolve, reject) => {
      wx.requestPayment({
        timeStamp: p.timeStamp, nonceStr: p.nonceStr, package: p.package,
        signType: p.signType as 'RSA', paySign: p.paySign,
        success: () => resolve(), fail: (e: unknown) => reject(e),
      })
    })
    uni.showToast({ title: '开通成功', icon: 'success' })
    await ent.fetch()
    setTimeout(() => uni.navigateBack(), 800)
    // #endif
    // #ifndef MP-WEIXIN
    uni.showToast({ title: '请在微信小程序内支付', icon: 'none' })
    // #endif
  } catch (e) {
    uni.showToast({ title: (e as Error).message || '开通失败', icon: 'none' })
  } finally {
    paying.value = false
  }
}

onMounted(async () => {
  if (!auth.isLoggedIn()) await auth.login()
  try { pricing.value = await getTierPricing() } catch (e) {
    uni.showToast({ title: (e as Error).message || '加载失败', icon: 'none' })
  } finally { loading.value = false }
})
</script>

<style scoped>
.buy-page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.tip { text-align: center; padding: 120rpx; color: var(--c-text-hint); }
.head { padding: 8rpx 4rpx 20rpx; }
.h-title { font-size: 40rpx; font-weight: 800; color: var(--c-ink); display: block; }
.h-sub { font-size: 24rpx; color: var(--c-text-hint); margin-top: 6rpx; display: block; }
.tier-row { display: flex; gap: 16rpx; margin-bottom: 20rpx; }
.tier { flex: 1; background: var(--c-bg-card); border-radius: var(--r-lg); padding: 28rpx 16rpx; display: flex; flex-direction: column; align-items: center; gap: 10rpx; border: 3rpx solid transparent; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.tier.active { border-color: var(--c-primary); background: var(--c-primary-faint); }
.tier-name { font-size: 30rpx; font-weight: 800; color: var(--c-ink); }
.tier-price { font-size: 38rpx; font-weight: 900; color: var(--c-primary-deep); }
.tier-unit { font-size: 22rpx; font-weight: 500; color: var(--c-text-hint); }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: 26rpx; margin-bottom: 20rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.qty-card { display: flex; align-items: center; justify-content: space-between; }
.qty-label { font-size: 30rpx; font-weight: 600; color: var(--c-text-body); }
.stepper { display: flex; align-items: center; background: var(--c-bg-soft); border-radius: var(--r-pill); overflow: hidden; }
.step-btn { width: 80rpx; height: 70rpx; line-height: 70rpx; text-align: center; font-size: 44rpx; color: var(--c-primary-deep); }
.step-btn.disabled { color: var(--c-text-hint); }
.step-val { width: 96rpx; text-align: center; font-size: 36rpx; font-weight: 800; color: var(--c-ink); }
.sum-card { display: flex; flex-direction: column; gap: 14rpx; }
.sum-row { display: flex; justify-content: space-between; font-size: 28rpx; color: var(--c-text-body); }
.sum-v { font-weight: 700; color: var(--c-ink); }
.sum-price { font-size: 40rpx; font-weight: 900; color: var(--c-danger); }
.btn-primary { background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-pill); font-size: 32rpx; font-weight: 700; height: 88rpx; line-height: 88rpx; }
.note { display: block; font-size: 22rpx; color: var(--c-text-hint); text-align: center; margin-top: 16rpx; line-height: 1.6; }
</style>
