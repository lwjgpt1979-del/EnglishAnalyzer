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

      <!-- 优惠券（SP-4）-->
      <view class="card coupon-card" @tap="openCoupon">
        <text class="coupon-label">优惠券</text>
        <view class="coupon-right">
          <text v-if="selectedCoupon" class="coupon-val">-¥{{ (selectedCoupon.discount_fen / 100).toFixed(2) }}</text>
          <text v-else class="coupon-hint">{{ coupons.length ? `${coupons.length} 张可用` : '暂无可用' }}</text>
          <text class="coupon-arrow">›</text>
        </view>
      </view>

      <!-- 合计 -->
      <view class="card sum-card">
        <view class="sum-row"><text>会员时长</text><text class="sum-v">{{ months }} 个月</text></view>
        <view v-if="discountFen > 0" class="sum-row"><text>优惠券抵扣</text><text class="sum-v">-¥{{ (discountFen / 100).toFixed(2) }}</text></view>
        <view class="sum-row"><text>合计</text><text class="sum-price">¥{{ (payFen / 100).toFixed(2) }}</text></view>
      </view>

      <button class="btn-primary" :disabled="paying" @tap="onPay">
        {{ paying ? '支付中…' : `立即开通 · ¥${(payFen / 100).toFixed(2)}` }}
      </button>
      <text class="note">购买后会员时长自动累加；高档优先生效，到期自动顺延低档。</text>
    </view>

    <PayConfirm :open="showConfirm" :plan="planSnapshot" @close="showConfirm = false" @confirmed="onConfirmed" />
  </view>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { getTierPricing, createOrder, payOrder, type TierPricing } from '@/api/orders'
import { applicableCoupons, type ApplicableCoupon } from '@/api/coupons'
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

// 优惠券（SP-4）
const coupons = ref<ApplicableCoupon[]>([])
const selectedCoupon = ref<ApplicableCoupon | null>(null)
const discountFen = computed(() => selectedCoupon.value?.discount_fen || 0)
const payFen = computed(() => Math.max(0, totalFen.value - discountFen.value))

const planSnapshot = computed(() => ({
  name: `${tiers.value.find(t => t.key === tier.value)?.name || ''}会员 ×${qty.value} 份`,
  months: months.value, amountFen: payFen.value, tier: tier.value, quantity: qty.value,
}))

async function loadCoupons() {
  if (totalFen.value <= 0) { coupons.value = []; return }
  try {
    coupons.value = (await applicableCoupons(totalFen.value, 'new')).items
    // 已选券若不再可用则清除
    if (selectedCoupon.value && !coupons.value.some(c => c.grant_id === selectedCoupon.value!.grant_id)) {
      selectedCoupon.value = null
    }
  } catch { coupons.value = [] }
}

function openCoupon() {
  if (!coupons.value.length) {
    uni.showToast({ title: '暂无可用优惠券', icon: 'none' }); return
  }
  const labels = coupons.value.map(c => `${c.name}（-¥${(c.discount_fen / 100).toFixed(2)}）`)
  const itemList = selectedCoupon.value ? ['不使用优惠券', ...labels] : labels
  uni.showActionSheet({
    itemList,
    success: (r) => {
      if (selectedCoupon.value && r.tapIndex === 0) { selectedCoupon.value = null; return }
      const idx = selectedCoupon.value ? r.tapIndex - 1 : r.tapIndex
      selectedCoupon.value = coupons.value[idx] || null
    },
  })
}

function inc() { if (qty.value < 24) { qty.value++; loadCoupons() } }
function dec() { if (qty.value > 1) { qty.value--; loadCoupons() } }

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
      coupon_grant_id: selectedCoupon.value?.grant_id,
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

watch(tier, () => loadCoupons())

onMounted(async () => {
  if (!auth.isLoggedIn()) await auth.login()
  try { pricing.value = await getTierPricing() } catch (e) {
    uni.showToast({ title: (e as Error).message || '加载失败', icon: 'none' })
  } finally { loading.value = false }
  await loadCoupons()
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
.coupon-card { display: flex; align-items: center; justify-content: space-between; }
.coupon-label { font-size: 28rpx; color: var(--c-ink); font-weight: 600; }
.coupon-right { display: flex; align-items: center; gap: 8rpx; }
.coupon-val { font-size: 28rpx; color: #ff6b35; font-weight: 700; }
.coupon-hint { font-size: 26rpx; color: var(--c-text-hint); }
.coupon-arrow { font-size: 32rpx; color: var(--c-text-hint); }
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
