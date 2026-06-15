<!-- 支付前合规确认弹窗（§4.6）：两项必须勾选 → payment-confirm 留存 → 放行支付 -->
<template>
  <view v-if="open" class="pc-mask">
    <view class="pc-card">
      <view class="pc-head">
        <text class="pc-title">购买确认</text>
        <text class="pc-x" @tap="$emit('close')">×</text>
      </view>

      <!-- 套餐信息 -->
      <view class="pc-plan">
        <text class="pc-plan-name">{{ plan?.name || '会员套餐' }}</text>
        <text v-if="plan?.months" class="pc-plan-sub">有效期：购买当日起 {{ plan.months }} 个月</text>
        <text class="pc-plan-price">实付金额：¥{{ ((plan?.amountFen || 0) / 100).toFixed(2) }}</text>
      </view>

      <text class="pc-tip">请仔细阅读并勾选以下内容，方可完成支付：</text>

      <!-- 勾选 1 -->
      <view class="pc-check" @tap="c1 = !c1">
        <view class="pc-box" :class="{ on: c1 }">{{ c1 ? '✓' : '' }}</view>
        <text class="pc-text">我已了解退款规则：购买后 7 天内未使用可全额退款；7 天内已使用按剩余天数比例退款（退款金额 = 实付金额 × 剩余天数 / 总购买天数）；超过 7 天不支持无理由退款。</text>
      </view>

      <!-- 勾选 2 -->
      <view class="pc-check" @tap="c2 = !c2">
        <view class="pc-box" :class="{ on: c2 }">{{ c2 ? '✓' : '' }}</view>
        <text class="pc-text">我已了解：本服务为虚拟数字会员服务，一经使用（首次 AI 分析）即视为开始享受服务。如遇平台故障、服务描述不符、误操作重复购买或未成年人未经授权购买，可通过「我的 → 订单记录 → 申诉」提交申诉。</text>
      </view>

      <view class="pc-btns">
        <text class="pc-cancel" @tap="$emit('close')">取消，不购买</text>
        <view class="pc-go" :class="{ disabled: !ready, shake: shaking }" @tap="onGo">
          {{ loading ? '处理中…' : '已阅读，去支付' }}
        </view>
      </view>
      <text v-if="!ready" class="pc-hint">请先阅读并勾选上方内容</text>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { paymentConfirm } from '@/api/orders'

const props = defineProps<{
  open: boolean
  // 套餐快照（展示 + 服务端留存防"描述不符"纠纷）
  plan?: { name?: string; months?: number; amountFen?: number; tier?: string; quantity?: number } | null
}>()
const emit = defineEmits<{
  (e: 'close'): void
  // 确认成功 → 回传 log_id，由父组件携此 id 下单并发起支付
  (e: 'confirmed', logId: string): void
}>()

const c1 = ref(false)
const c2 = ref(false)
const loading = ref(false)
const shaking = ref(false)
const ready = computed(() => c1.value && c2.value)

// 每次打开重置（不得预置已勾选，《电子商务法》§49）
watch(() => props.open, (v) => {
  if (v) { c1.value = false; c2.value = false; loading.value = false }
})

function _shake() {
  shaking.value = true
  setTimeout(() => { shaking.value = false }, 400)
}

async function onGo() {
  if (!ready.value) { _shake(); return }
  if (loading.value) return
  loading.value = true
  try {
    const res = await paymentConfirm({
      plan_snapshot: props.plan ? { ...props.plan } : undefined,
      checkbox_refund_policy: true,
      checkbox_digital_service: true,
    })
    emit('confirmed', res.log_id)
  } catch (e) {
    // 留存失败 → 不得放行支付
    uni.showToast({ title: (e as Error).message || '网络异常，请重试', icon: 'none' })
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.pc-mask { position: fixed; inset: 0; background: rgba(0,0,0,.5); display: flex; align-items: center; justify-content: center; z-index: 1100; }
.pc-card { width: 600rpx; background: var(--c-bg-card); border-radius: var(--r-lg); padding: 32rpx 28rpx; max-height: 80vh; overflow-y: auto; }
.pc-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20rpx; }
.pc-title { font-size: 34rpx; font-weight: 800; color: var(--c-ink); }
.pc-x { font-size: 44rpx; color: var(--c-text-hint); line-height: 1; padding: 0 8rpx; }
.pc-plan { background: var(--c-bg-soft); border-radius: var(--r-md); padding: 22rpx; display: flex; flex-direction: column; gap: 8rpx; margin-bottom: 20rpx; }
.pc-plan-name { font-size: 30rpx; font-weight: 700; color: var(--c-ink); }
.pc-plan-sub { font-size: 24rpx; color: var(--c-text-second); }
.pc-plan-price { font-size: 30rpx; font-weight: 800; color: var(--c-danger); }
.pc-tip { display: block; font-size: 26rpx; color: var(--c-text-body); margin-bottom: 16rpx; }
.pc-check { display: flex; align-items: flex-start; gap: 14rpx; margin-bottom: 18rpx; }
.pc-box { flex: none; width: 40rpx; height: 40rpx; border-radius: 8rpx; border: 2rpx solid var(--c-border); display: flex; align-items: center; justify-content: center; font-size: 28rpx; color: var(--c-on-primary); background: var(--c-bg-card); }
.pc-box.on { background: var(--c-primary); border-color: var(--c-primary); }
.pc-text { flex: 1; font-size: 24rpx; color: var(--c-text-second); line-height: 1.55; }
.pc-btns { display: flex; gap: 16rpx; margin-top: 12rpx; }
.pc-cancel { flex: 1; text-align: center; height: 80rpx; line-height: 80rpx; font-size: 28rpx; color: var(--c-text-second); background: var(--c-bg-soft); border-radius: var(--r-pill); }
.pc-go { flex: 1.4; text-align: center; height: 80rpx; line-height: 80rpx; font-size: 28rpx; font-weight: 700; color: var(--c-on-primary); background: var(--c-primary); border-radius: var(--r-pill); }
.pc-go.disabled { background: var(--c-text-hint); opacity: .6; }
.pc-go.shake { animation: pcshake .4s; }
.pc-hint { display: block; text-align: center; font-size: 22rpx; color: var(--c-danger); margin-top: 12rpx; }
@keyframes pcshake { 0%,100%{transform:translateX(0)} 25%{transform:translateX(-8rpx)} 75%{transform:translateX(8rpx)} }
</style>
