<!-- src/pages/membership/semester-purchase.vue -->
<!-- V2 学期购买页（D-079 / M1）-->
<template>
  <view class="page">

    <!-- 学期上下文 -->
    <view class="context-card">
      <text class="context-label">购买学期</text>
      <text class="context-value">{{ textbook }} · {{ grade }} · {{ semester }}学期</text>
    </view>

    <!-- 档位选择 -->
    <view class="section-title">选择档位</view>
    <view class="tier-row">
      <view
        v-for="t in tiers"
        :key="t.key"
        class="tier-card"
        :class="{ selected: selectedTier === t.key }"
        @tap="selectedTier = t.key"
      >
        <text class="tier-name">{{ t.label }}</text>
        <text class="tier-price">¥{{ t.price }}</text>
        <text class="tier-unit">/学期</text>
      </view>
    </view>

    <!-- 总价 -->
    <view class="total-row">
      <text class="total-label">合计</text>
      <text class="total-price">¥{{ totalPrice }}</text>
    </view>

    <!-- 说明 -->
    <view class="desc-card">
      <text class="desc-text">· 购买后解锁该学期全部单元课程内容</text>
      <text class="desc-text">· 有效期一学期（约 6 个月）</text>
      <text class="desc-text">· 档位说明：基础含知识点讲解；Pro 含仿真练习；ProMax 含模拟考 + 排名</text>
    </view>

    <!-- 支付按钮 -->
    <button
      class="btn-pay"
      :disabled="paying"
      @tap="onPay"
    >
      {{ paying ? '支付中…' : '微信支付 ¥' + totalPrice }}
    </button>

  </view>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { createOrder, payOrder } from '@/api/orders'
import type { SemesterItem } from '@/types/api'

// ── 解码 ──────────────────────────────────────────────────────────────────────
function safeDecode(s: string | undefined): string {
  if (!s) return ''
  try { return decodeURIComponent(s) } catch { return s }
}

// ── 页面参数 ──────────────────────────────────────────────────────────────────
const textbook = ref('译林版')
const grade = ref('小学5年级')
const semester = ref('上')

onLoad((q: any) => {
  textbook.value = safeDecode(q?.textbook) || '译林版'
  grade.value = safeDecode(q?.grade) || '小学5年级'
  semester.value = safeDecode(q?.semester) || '上'
})

// ── 档位 ─────────────────────────────────────────────────────────────────────
type TierKey = 'basic' | 'pro' | 'promax'

const tiers: { key: TierKey; label: string; price: number }[] = [
  { key: 'basic',  label: '基础版', price: 39  },
  { key: 'pro',    label: 'Pro',    price: 79  },
  { key: 'promax', label: 'ProMax', price: 159 },
]

const selectedTier = ref<TierKey>('basic')

// ── 总价（M1 单学期购买）─────────────────────────────────────────────────────
const totalPrice = computed(() => {
  return tiers.find(t => t.key === selectedTier.value)?.price ?? 39
})

// ── 支付 ─────────────────────────────────────────────────────────────────────
const paying = ref(false)

async function onPay() {
  if (paying.value) return
  paying.value = true
  try {
    // M1 单学期购买：semesters 仅含当前一个 (教材, 年级, 学期)
    const semItem: SemesterItem = {
      textbook_version: textbook.value,
      grade: grade.value,
      semester: semester.value as '上' | '下',
    }

    const order = await createOrder({
      tier: selectedTier.value,
      order_type: 'new',
      semesters: [semItem],
    })

    const params = await payOrder(order.id)

    await new Promise<void>((resolve, reject) => {
      wx.requestPayment({
        timeStamp: params.timeStamp,
        nonceStr: params.nonceStr,
        package: params.package,
        signType: params.signType as 'RSA' | 'MD5',
        paySign: params.paySign,
        success: () => resolve(),
        fail: (err: any) => reject(err),
      })
    })

    uni.showToast({ title: '支付成功', icon: 'success' })
    setTimeout(() => uni.navigateBack(), 1500)
  } catch (err: any) {
    const msg: string = err?.errMsg || err?.message || ''
    if (msg.includes('cancel')) {
      // 用户主动取消，静默处理
      return
    }
    uni.showToast({ title: msg || '支付失败，请重试', icon: 'none' })
  } finally {
    paying.value = false
  }
}
</script>

<style scoped>
.page {
  padding: 24rpx;
  background: var(--c-bg-page);
  min-height: 100vh;
}

.context-card {
  background: var(--c-bg-card);
  border-radius: var(--r-lg);
  padding: var(--sp-4);
  margin-bottom: 24rpx;
  display: flex;
  align-items: center;
  gap: 16rpx;
  box-shadow: 0 4rpx 24rpx rgba(0, 0, 0, 0.04);
}
.context-label {
  font-size: 24rpx;
  color: var(--c-text-hint);
}
.context-value {
  font-size: 30rpx;
  font-weight: 700;
  color: var(--c-ink);
}

.section-title {
  font-size: 28rpx;
  font-weight: 700;
  color: var(--c-ink);
  margin-bottom: 16rpx;
  margin-top: 8rpx;
}

/* 档位卡片 */
.tier-row {
  display: flex;
  gap: 16rpx;
  margin-bottom: 32rpx;
}
.tier-card {
  flex: 1;
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-md);
  padding: 24rpx 12rpx;
  text-align: center;
  background: var(--c-bg-card);
}
.tier-card.selected {
  border-color: var(--c-gold);
  background: var(--c-primary-faint);
}
.tier-name {
  display: block;
  font-size: 26rpx;
  color: var(--c-text-body);
  margin-bottom: 8rpx;
  font-weight: 600;
}
.tier-price {
  display: block;
  font-size: 36rpx;
  font-weight: 800;
  color: var(--c-ink);
}
.tier-unit {
  display: block;
  font-size: 20rpx;
  color: var(--c-text-hint);
  margin-top: 4rpx;
}

/* 总价 */
.total-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--c-bg-card);
  border-radius: var(--r-md);
  padding: 20rpx var(--sp-4);
  margin-bottom: 24rpx;
}
.total-label {
  font-size: 28rpx;
  color: var(--c-text-second);
  font-weight: 600;
}
.total-price {
  font-size: 40rpx;
  font-weight: 800;
  color: var(--c-ink);
}

/* 说明 */
.desc-card {
  background: var(--c-bg-card);
  border-radius: var(--r-md);
  padding: 20rpx var(--sp-4);
  margin-bottom: 40rpx;
  display: flex;
  flex-direction: column;
  gap: 10rpx;
}
.desc-text {
  font-size: 22rpx;
  color: var(--c-text-hint);
  line-height: 1.6;
}

/* 支付按钮 */
.btn-pay {
  background: var(--c-primary);
  color: var(--c-ink);
  border-radius: var(--r-btn);
  font-size: 32rpx;
  font-weight: 700;
  height: 96rpx;
  line-height: 96rpx;
  text-align: center;
  width: 100%;
}
.btn-pay[disabled] {
  background: var(--c-primary-soft);
  color: #b9a94e;
}
</style>
