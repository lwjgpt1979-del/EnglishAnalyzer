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
    <!-- 限时活动横幅（§5.7）-->
    <view v-if="campaign" class="promo-banner">
      <text class="promo-tag">限时</text>
      <text class="promo-name">{{ campaign.name }}</text>
      <text v-if="campaign.ends_at" class="promo-end">至 {{ campaign.ends_at.replace('T', ' ').slice(5, 16) }}</text>
    </view>

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
        <text v-if="t.listPrice > t.price" class="tier-list">¥{{ t.listPrice }}</text>
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
      <text class="desc-text">· 开通后解锁该学期全部单元的知识点讲解与练习资料</text>
      <text class="desc-text">· 有效期一学期（约 6 个月）</text>
      <text class="desc-text">· 档位说明：基础含知识点讲解；Pro 含仿真练习；ProMax 含模拟考 + 排名</text>
    </view>

    <!-- 监护人同意（14-17 岁首次购买必选；成年人可不勾，后端按年龄判定）-->
    <view class="consent-row" @tap="agreeMinor = !agreeMinor">
      <view class="cbox" :class="{ on: agreeMinor }">{{ agreeMinor ? '✓' : '' }}</view>
      <text class="consent-text">我已告知监护人并获得同意（14-17 岁用户首次购买必选）</text>
    </view>

    <!-- 支付按钮 -->
    <button
      class="btn-pay"
      :disabled="paying"
      @tap="onPay"
    >
      {{ paying ? '支付中…' : '微信支付 ¥' + totalPrice }}
    </button>

    <PayConfirm :open="showConfirm" :plan="planSnapshot" @close="showConfirm = false" @confirmed="onConfirmed" />
  </view>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { createOrder, payOrder, getSemesterPricing } from '@/api/orders'
import type { SemesterItem } from '@/types/api'
import PayConfirm from '@/components/PayConfirm.vue'

// ── 解码 ──────────────────────────────────────────────────────────────────────
function safeDecode(s: string | undefined): string {
  if (!s) return ''
  try { return decodeURIComponent(s) } catch { return s }
}

// ── 页面参数 ──────────────────────────────────────────────────────────────────
const textbook = ref('译林版')
const grade = ref('小学5年级')
const semester = ref('上')

onLoad(async (q: any) => {
  textbook.value = safeDecode(q?.textbook) || '译林版'
  grade.value = safeDecode(q?.grade) || '小学5年级'
  semester.value = safeDecode(q?.semester) || '上'
  // 价格从后台定价配置读取（运营可改），不写死
  try {
    const p = await getSemesterPricing()
    tiers.value = [
      { key: 'basic',  label: '基础版', price: p.basic,  listPrice: p.list_basic || 0 },
      { key: 'pro',    label: 'Pro',    price: p.pro,    listPrice: p.list_pro || 0 },
      { key: 'promax', label: 'ProMax', price: p.promax, listPrice: p.list_promax || 0 },
    ]
    campaign.value = p.campaign || null
  } catch { /* 取价失败保留默认 */ }
})

// ── 档位 ─────────────────────────────────────────────────────────────────────
type TierKey = 'basic' | 'pro' | 'promax'

const tiers = ref<{ key: TierKey; label: string; price: number; listPrice: number }[]>([
  { key: 'basic',  label: '基础版', price: 39,  listPrice: 0 },
  { key: 'pro',    label: 'Pro',    price: 79,  listPrice: 0 },
  { key: 'promax', label: 'ProMax', price: 159, listPrice: 0 },
])
const campaign = ref<{ id: string; name: string; ends_at: string | null; is_promotional: boolean } | null>(null)

const selectedTier = ref<TierKey>('basic')

// ── 总价（M1 单学期购买）─────────────────────────────────────────────────────
const totalPrice = computed(() => {
  return tiers.value.find(t => t.key === selectedTier.value)?.price ?? 39
})

// ── 支付 ─────────────────────────────────────────────────────────────────────
const paying = ref(false)
const showConfirm = ref(false)
const agreeMinor = ref(false)
const planSnapshot = computed(() => ({
  name: `${tiers.value.find(t => t.key === selectedTier.value)?.label || ''}会员 · ${semester.value}学期`,
  months: 6,
  amountFen: totalPrice.value * 100,
  tier: selectedTier.value,
}))

// 点支付 → 先弹合规确认弹窗（§4.6），确认成功拿 log_id 再下单
function onPay() {
  if (paying.value) return
  showConfirm.value = true
}

async function onConfirmed(logId: string) {
  showConfirm.value = false
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
      minor_consent: agreeMinor.value,
      payment_confirm_log_id: logId,
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
.tier-list {
  display: block;
  font-size: 22rpx;
  color: var(--c-text-hint);
  text-decoration: line-through;
  margin-top: 2rpx;
}
.tier-unit {
  display: block;
  font-size: 20rpx;
  color: var(--c-text-hint);
  margin-top: 4rpx;
}

/* 限时活动横幅 */
.promo-banner {
  display: flex;
  align-items: center;
  gap: 12rpx;
  background: linear-gradient(90deg, #fff1e6, #ffe9d6);
  border-radius: 12rpx;
  padding: 16rpx 20rpx;
  margin-bottom: 16rpx;
}
.promo-tag {
  background: #ff6b35;
  color: #fff;
  font-size: 22rpx;
  padding: 4rpx 12rpx;
  border-radius: 6rpx;
}
.promo-name { font-size: 26rpx; color: #d2691e; font-weight: 600; flex: 1; }
.promo-end { font-size: 22rpx; color: #b8860b; }

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

/* 监护人同意 */
.consent-row {
  display: flex;
  align-items: flex-start;
  gap: 14rpx;
  padding: 0 8rpx;
  margin-bottom: 24rpx;
}
.cbox {
  flex: none;
  width: 36rpx;
  height: 36rpx;
  border-radius: 8rpx;
  border: 2rpx solid var(--c-border);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24rpx;
  color: var(--c-on-primary);
  background: var(--c-bg-card);
}
.cbox.on {
  background: var(--c-primary);
  border-color: var(--c-primary);
}
.consent-text {
  flex: 1;
  font-size: 24rpx;
  color: var(--c-text-second);
  line-height: 1.5;
}

/* 支付按钮 */
.btn-pay {
  background: var(--c-primary);
  color: var(--c-on-primary);
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
  color: #9aa7b8;
}
</style>
