<!-- 我的优惠券（SP-4）：列表 + 兑换码领取 -->
<template>
  <view class="cp-page">
    <view class="redeem-card">
      <input v-model="code" class="redeem-ipt" placeholder="输入兑换码" maxlength="20" />
      <button class="redeem-btn" :disabled="redeeming || !code.trim()" @tap="doRedeem">{{ redeeming ? '兑换中…' : '兑换' }}</button>
    </view>

    <view class="tabs">
      <view class="tab" :class="{ on: tab === 'unused' }" @tap="switchTab('unused')">未使用</view>
      <view class="tab" :class="{ on: tab === 'used' }" @tap="switchTab('used')">已使用</view>
    </view>

    <view v-if="!items.length" class="empty">{{ tab === 'unused' ? '暂无可用优惠券' : '暂无已使用优惠券' }}</view>
    <view v-for="c in items" :key="c.grant_id" class="cp-card" :class="{ dim: c.status === 'used' || c.expired }">
      <view class="cp-left">
        <text class="cp-desc">{{ c.desc }}</text>
        <text class="cp-name">{{ c.name }}</text>
        <text class="cp-cond">{{ c.min_amount_fen ? '满' + (c.min_amount_fen / 100) + '元可用' : '无门槛' }}<text v-if="c.valid_until"> · {{ c.valid_until.slice(0, 10) }}到期</text></text>
      </view>
      <view class="cp-right">
        <text v-if="c.status === 'used'" class="cp-tag used">已使用</text>
        <text v-else-if="c.expired" class="cp-tag exp">已过期</text>
        <text v-else class="cp-tag ok">可用</text>
      </view>
    </view>

    <view class="hint">下单结算时可选择适用的优惠券抵扣。</view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { myCoupons, redeemCoupon, type MyCoupon } from '@/api/coupons'

const tab = ref('unused')
const items = ref<MyCoupon[]>([])
const code = ref('')
const redeeming = ref(false)

async function load() {
  try { items.value = (await myCoupons(tab.value)).items } catch { /* ignore */ }
}
function switchTab(t: string) { tab.value = t; load() }
async function doRedeem() {
  if (!code.value.trim()) return
  redeeming.value = true
  try {
    const r = await redeemCoupon(code.value.trim().toUpperCase())
    uni.showToast({ title: `领取成功：${r.desc}`, icon: 'none' })
    code.value = ''; tab.value = 'unused'; await load()
  } catch (e: any) { uni.showToast({ title: e?.message || '兑换失败', icon: 'none' }) }
  finally { redeeming.value = false }
}

onShow(load)
</script>

<style scoped>
.cp-page { padding: 24rpx; background: #f5f6f8; min-height: 100vh; }
.redeem-card { display: flex; gap: 16rpx; background: #fff; border-radius: 16rpx; padding: 20rpx; margin-bottom: 24rpx; }
.redeem-ipt { flex: 1; background: #f0f2f5; border-radius: 12rpx; padding: 16rpx 24rpx; font-size: 28rpx; }
.redeem-btn { background: #409eff; color: #fff; border-radius: 999rpx; font-size: 28rpx; padding: 0 36rpx; }
.tabs { display: flex; gap: 32rpx; margin-bottom: 20rpx; }
.tab { font-size: 28rpx; color: #888; padding-bottom: 8rpx; }
.tab.on { color: #409eff; font-weight: 600; border-bottom: 4rpx solid #409eff; }
.empty { color: #999; text-align: center; padding: 80rpx 0; font-size: 28rpx; }
.cp-card { display: flex; background: #fff; border-radius: 16rpx; padding: 28rpx; margin-bottom: 16rpx; align-items: center; }
.cp-card.dim { opacity: 0.55; }
.cp-left { flex: 1; }
.cp-desc { font-size: 34rpx; font-weight: 700; color: #ff6b35; display: block; }
.cp-name { font-size: 28rpx; color: #333; display: block; margin: 6rpx 0; }
.cp-cond { font-size: 24rpx; color: #999; display: block; }
.cp-tag { font-size: 24rpx; padding: 8rpx 20rpx; border-radius: 999rpx; }
.cp-tag.ok { background: #ecf5ff; color: #409eff; }
.cp-tag.used, .cp-tag.exp { background: #f0f0f0; color: #999; }
.hint { color: #999; font-size: 24rpx; text-align: center; margin-top: 24rpx; }
</style>
