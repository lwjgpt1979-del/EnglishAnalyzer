<template>
  <view class="page">
    <view v-if="loading" class="tip">加载中…</view>
    <view v-else-if="!report" class="tip">暂无数据</view>
    <view v-else>
      <view class="card">
        <view class="stat-row">
          <view class="stat"><text class="num">{{ report.total_questions }}</text><text class="lbl">累计错题</text></view>
          <view class="stat"><text class="num">{{ report.total_analyzed }}</text><text class="lbl">已分析</text></view>
          <view class="stat"><text class="num">{{ Math.round(report.mastery_rate * 100) }}%</text><text class="lbl">掌握率</text></view>
        </view>
      </view>

      <view v-if="report.top_error_types.length" class="card">
        <view class="card-title">高频错误</view>
        <view v-for="e in report.top_error_types.slice(0, 5)" :key="e.error_type" class="row">
          <text>{{ e.error_type }}</text><text class="count">{{ e.count }}</text>
        </view>
      </view>

      <view v-if="report.top_suggestions?.length" class="card">
        <view class="card-title">AI 学习建议</view>
        <view v-for="(s, i) in report.top_suggestions" :key="i" class="sug">
          <text class="sug-num">{{ i + 1 }}</text>
          <text class="sug-text">{{ s }}</text>
        </view>
      </view>

      <view class="card">
        <view class="card-title">本月打卡日历</view>
        <view v-if="cal" class="cal-summary">
          本月打卡 {{ cal.checked_count }} 天 · 当前连续 {{ cal.current_streak }} 天 · 历史最高 {{ cal.longest_streak }} 天
        </view>
        <view class="cal-grid">
          <view v-for="(c, i) in cells" :key="i" class="cal-cell" :class="{ checked: c.checked, blank: !c.day }">
            <text v-if="c.day">{{ c.checked ? '🔥' : c.day }}</text>
          </view>
        </view>
      </view>

      <view class="card">
        <view class="card-title">为孩子续费 / 升级会员</view>
        <view class="tier-row">
          <text v-for="t in tiers" :key="t.tier" class="tier" :class="{ active: selectedTier === t.tier }" @tap="selectedTier = t.tier">
            {{ t.label }}<br>¥{{ t.price }}/月
          </text>
        </view>
        <button class="btn-primary" :disabled="paying" @tap="onPay">
          {{ paying ? '支付中…' : `代付 ¥${currentPrice}` }}
        </button>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { getStudentDiagnosisAsRelative, getStudentCheckinCalendar } from '@/api/relative'
import { createOrder, payOrder } from '@/api/orders'
import type { RelativeCheckinCalendar } from '@/types/api'

const studentId = ref('')
const report = ref<any>(null)
const loading = ref(true)
const paying = ref(false)
const selectedTier = ref('basic')
const tiers = [
  { tier: 'basic', label: '基础版', price: 9 },
  { tier: 'pro', label: '专业版', price: 19 },
  { tier: 'promax', label: '旗舰版', price: 39 },
]
const currentPrice = computed(() => tiers.find(t => t.tier === selectedTier.value)?.price || 0)

const cal = ref<RelativeCheckinCalendar | null>(null)
const checkedSet = computed(() => new Set(cal.value?.days.map(d => d.date) ?? []))
const cells = computed(() => {
  if (!cal.value) return [] as { day: number; date: string; checked: boolean }[]
  const { year, month } = cal.value
  const first = new Date(year, month - 1, 1).getDay()
  const daysIn = new Date(year, month, 0).getDate()
  const arr: { day: number; date: string; checked: boolean }[] = []
  for (let i = 0; i < first; i++) arr.push({ day: 0, date: '', checked: false })
  for (let d = 1; d <= daysIn; d++) {
    const date = `${year}-${String(month).padStart(2, '0')}-${String(d).padStart(2, '0')}`
    arr.push({ day: d, date, checked: checkedSet.value.has(date) })
  }
  return arr
})

onMounted(async () => {
  const pages = getCurrentPages()
  studentId.value = (pages[pages.length - 1] as any).options?.studentId || ''
  if (!studentId.value) { loading.value = false; return }
  try {
    report.value = await getStudentDiagnosisAsRelative(studentId.value)
    try { cal.value = await getStudentCheckinCalendar(studentId.value) } catch { /* 日历失败不阻塞 */ }
  } finally { loading.value = false }
})

async function onPay() {
  paying.value = true
  try {
    const order = await createOrder({
      tier: selectedTier.value,
      duration_months: 1,
      order_type: 'new',
      target_student_id: studentId.value,
    })
    const params = await payOrder(order.id)
    await new Promise<void>((resolve, reject) => {
      wx.requestPayment({
        timeStamp: params.timeStamp, nonceStr: params.nonceStr,
        package: params.package, signType: params.signType as 'RSA' | 'MD5',
        paySign: params.paySign,
        success: () => resolve(),
        fail: (err) => reject(new Error(err.errMsg || '支付取消')),
      })
    })
    uni.showToast({ title: '代付成功！', icon: 'success' })
  } catch (e: any) {
    const msg = e?.message || ''
    if (msg && !msg.includes('cancel')) uni.showToast({ title: msg || '支付失败', icon: 'error' })
  } finally { paying.value = false }
}
</script>

<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.tip { text-align: center; padding: 120rpx 0; color: var(--c-text-hint); }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin-bottom: 20rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.card-title { font-size: var(--fs-h2); font-weight: 700; color: var(--c-ink); margin-bottom: 16rpx; }
.stat-row { display: flex; justify-content: space-around; }
.stat { text-align: center; }
.num { font-size: 56rpx; font-weight: 800; color: var(--c-ink); display: block; }
.lbl { font-size: 24rpx; color: var(--c-text-hint); }
.row { display: flex; justify-content: space-between; padding: 8rpx 0; border-bottom: 1rpx solid var(--c-border); font-size: 26rpx; color: var(--c-text-body); }
.count { color: var(--c-gold); font-weight: 700; }
.sug { display: flex; margin-bottom: 16rpx; }
.sug-num { width: 44rpx; height: 44rpx; background: var(--c-primary); color: var(--c-ink); border-radius: 50%; font-size: 24rpx; font-weight: 700; line-height: 44rpx; text-align: center; margin-right: 16rpx; }
.sug-text { flex: 1; font-size: 28rpx; color: var(--c-text-body); line-height: 1.7; }
.tier-row { display: flex; gap: 16rpx; margin-bottom: 16rpx; }
.tier { flex: 1; text-align: center; padding: 16rpx 0; border: 2rpx solid var(--c-border); border-radius: var(--r-md); font-size: 24rpx; color: var(--c-text-body); }
.tier.active { border-color: var(--c-gold); background: var(--c-primary-faint); font-weight: 700; }
.btn-primary { background: var(--c-primary); color: var(--c-ink); border-radius: var(--r-btn); padding: 20rpx; font-weight: 700; font-size: 28rpx; }
.btn-primary[disabled] { background: var(--c-primary-soft); color: #b9a94e; }
.cal-summary { font-size: 24rpx; color: var(--c-text-hint); margin-bottom: 16rpx; }
.cal-grid { display: flex; flex-wrap: wrap; }
.cal-cell { width: 14.28%; height: 64rpx; display: flex; align-items: center; justify-content: center; font-size: 24rpx; color: var(--c-text-body); }
.cal-cell.checked { color: var(--c-gold); font-weight: 700; }
.cal-cell.blank { visibility: hidden; }
</style>
