<!-- src/pages/profile/index.vue -->
<template>
  <view class="profile-page">

    <!-- 用户信息 -->
    <view class="card user-card">
      <view v-if="auth.user" class="user-row">
        <image
          v-if="auth.user.avatar_url"
          class="avatar"
          :src="auth.user.avatar_url"
          mode="aspectFill"
        />
        <view v-else class="avatar-placeholder">👤</view>
        <text class="nickname">{{ auth.user.nickname || '英语学习者' }}</text>
      </view>
      <view v-else>
        <button class="btn-login" @tap="auth.login()">微信登录</button>
      </view>
    </view>

    <!-- 会员状态 + 升级 -->
    <view class="card">
      <view class="card-title">会员状态</view>

      <view v-if="loadingMembership" class="center-tip">加载中…</view>
      <view v-else-if="membership">
        <view class="member-tier" :class="`tier-${membership.tier}`">
          {{ tierLabel(membership.tier) }}
        </view>
        <text v-if="membership.expires_at" class="expires-tip">
          到期：{{ membership.expires_at.slice(0, 10) }}
        </text>
      </view>

      <!-- 档位选择 -->
      <view class="tier-list">
        <view
          v-for="plan in memberPlans"
          :key="plan.tier"
          class="tier-card"
          :class="{ selected: selectedPlan === plan.tier }"
          @tap="selectedPlan = plan.tier"
        >
          <text class="tier-name">{{ plan.label }}</text>
          <text class="tier-price">¥{{ plan.price }}/月</text>
        </view>
      </view>

      <!-- 时长选择 -->
      <view class="duration-row">
        <view
          v-for="d in [1, 3, 12]"
          :key="d"
          class="duration-btn"
          :class="{ selected: selectedDuration === d }"
          @tap="selectedDuration = d"
        >
          <text>{{ d }}个月</text>
          <text v-if="d === 12" class="discount-tag">8折</text>
        </view>
      </view>

      <button
        class="btn-pay"
        :disabled="paying || !auth.isLoggedIn()"
        @tap="onPay"
      >
        {{ paying ? '支付中…' : `立即升级 ¥${currentPrice}` }}
      </button>
    </view>

    <!-- 教师中心 -->
    <view class="card" style="margin-top:16rpx;">
      <view class="card-title">教师中心</view>
      <text class="menu-desc">教师功能：生成邀请码、查看学生错题、添加批注；学生功能：绑定老师</text>
      <button class="btn-menu" @tap="goTeacher">进入教师中心</button>
    </view>

  </view>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getMyMembership } from '@/api/memberships'
import { createOrder, payOrder } from '@/api/orders'
import { useAuthStore } from '@/stores/auth'
import type { CurrentMembershipOut } from '@/types/api'

const auth = useAuthStore()
const membership = ref<CurrentMembershipOut | null>(null)
const loadingMembership = ref(false)
const paying = ref(false)
const selectedPlan = ref('basic')
const selectedDuration = ref(1)

const memberPlans = [
  { tier: 'basic', label: '基础版', price: 9 },
  { tier: 'pro', label: '专业版', price: 19 },
  { tier: 'promax', label: '旗舰版', price: 39 },
]

// 12个月享8折
const currentPrice = computed(() => {
  const plan = memberPlans.find((p) => p.tier === selectedPlan.value)
  if (!plan) return 0
  const base = plan.price * selectedDuration.value
  return selectedDuration.value === 12 ? Math.round(base * 0.8) : base
})

onMounted(async () => {
  if (!auth.isLoggedIn()) return
  loadingMembership.value = true
  try {
    membership.value = await getMyMembership()
  } finally {
    loadingMembership.value = false
  }
})

function tierLabel(tier: string): string {
  const map: Record<string, string> = {
    free: '免费版',
    basic: '基础版',
    pro: '专业版',
    promax: '旗舰版',
  }
  return map[tier] || tier
}

async function onPay() {
  if (!auth.isLoggedIn()) {
    await auth.login()
    return
  }
  if (paying.value) return  // prevent double-tap
  paying.value = true
  try {
    const orderType = membership.value?.tier === 'free' ? 'new' : 'renew'
    const order = await createOrder({
      tier: selectedPlan.value,
      duration_months: selectedDuration.value,
      order_type: orderType,
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
        fail: (err) => reject(new Error(err.errMsg || '支付取消')),
      })
    })

    uni.showToast({ title: '支付成功！', icon: 'success' })
    membership.value = await getMyMembership()
  } catch (e) {
    const msg = (e as Error).message
    // 用户主动取消不提示错误
    if (msg && !msg.includes('cancel')) {
      uni.showToast({ title: msg || '支付失败', icon: 'error' })
    }
  } finally {
    paying.value = false
  }
}

function goTeacher() {
  uni.navigateTo({ url: '/pages/teacher/students' })
}
</script>

<style scoped>
.profile-page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin-bottom: 20rpx; box-shadow: 0 4rpx 24rpx rgba(0, 0, 0, 0.04); }
.card-title { font-size: var(--fs-h2); font-weight: 700; margin-bottom: 20rpx; color: var(--c-ink); }
.user-row { display: flex; align-items: center; }
.avatar { width: 100rpx; height: 100rpx; border-radius: 50%; margin-right: 24rpx; }
.avatar-placeholder {
  width: 100rpx;
  height: 100rpx;
  background: var(--c-bg-soft);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 48rpx;
  margin-right: 24rpx;
}
.nickname { font-size: 32rpx; font-weight: 700; color: var(--c-ink); }
.btn-login { background: var(--c-primary); color: var(--c-ink); border-radius: var(--r-btn); font-weight: 700; }
.member-tier {
  display: inline-block;
  padding: 8rpx 24rpx;
  border-radius: var(--r-pill);
  font-size: 28rpx;
  font-weight: 700;
  margin-bottom: 12rpx;
}
.tier-free { background: var(--c-bg-soft); color: var(--c-text-hint); }
.tier-basic { background: var(--c-primary-soft); color: #8a7212; }
.tier-pro { background: #fcecd2; color: var(--c-orange); }
.tier-promax { background: var(--c-danger-bg); color: var(--c-danger); }
.expires-tip { font-size: 24rpx; color: var(--c-text-hint); display: block; margin-bottom: 20rpx; }
.tier-list { display: flex; gap: 16rpx; margin: 24rpx 0; }
.tier-card {
  flex: 1;
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-md);
  padding: 20rpx;
  text-align: center;
}
.tier-card.selected { border-color: var(--c-gold); background: var(--c-primary-faint); }
.tier-name { font-size: 26rpx; color: var(--c-text-body); display: block; margin-bottom: 8rpx; }
.tier-price { font-size: 24rpx; color: var(--c-ink); font-weight: 600; }
.duration-row { display: flex; gap: 16rpx; margin-bottom: 24rpx; }
.duration-btn {
  flex: 1;
  text-align: center;
  padding: 16rpx;
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-md);
  font-size: 26rpx;
  position: relative;
}
.duration-btn.selected { border-color: var(--c-gold); color: var(--c-ink); background: var(--c-primary-faint); font-weight: 600; }
.discount-tag {
  position: absolute;
  top: -14rpx;
  right: -8rpx;
  background: var(--c-orange);
  color: #fff;
  font-size: 18rpx;
  padding: 2rpx 8rpx;
  border-radius: var(--r-sm);
}
.btn-pay {
  background: var(--c-primary);
  color: var(--c-ink);
  border-radius: var(--r-btn);
  font-size: 32rpx;
  font-weight: 700;
  height: 96rpx;
  line-height: 96rpx;
}
.btn-pay[disabled] { background: var(--c-primary-soft); color: #b9a94e; }
.center-tip { color: var(--c-text-hint); font-size: 28rpx; }
.menu-desc { font-size: 24rpx; color: var(--c-text-second); margin-bottom: 12rpx; display: block; }
.btn-menu { background: var(--c-primary-faint); color: var(--c-ink); border: 2rpx solid var(--c-gold); border-radius: var(--r-md); padding: 16rpx; font-size: 28rpx; font-weight: 600; text-align: center; }
</style>
