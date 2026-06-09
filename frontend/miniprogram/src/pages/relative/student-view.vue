<template>
  <view class="page">
    <view v-if="loading" class="tip">加载中…</view>
    <view v-else-if="!report" class="tip">暂无数据</view>
    <view v-else>
      <view class="card">
        <view class="stat-row">
          <view class="stat"><text class="num">{{ report.total_questions }}</text><text class="lbl">累计错题</text></view>
          <view class="stat"><text class="num">{{ report.total_analyzed }}</text><text class="lbl">已分析</text></view>
          <view class="stat"><text class="num">{{ report.mastered_count ?? 0 }}</text><text class="lbl">已掌握</text></view>
          <view class="stat"><text class="num">{{ Math.round(report.mastery_rate * 100) }}%</text><text class="lbl">掌握率</text></view>
        </view>
      </view>

      <!-- M45 知识点台账入口 -->
      <view class="card entry-card" @tap="goKpMastery">
        <text class="entry-text">🧠 知识点掌握图谱</text>
        <text class="entry-arrow">›</text>
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

      <!-- V2 学期代付卡片 -->
      <view class="card">
        <view class="card-title">为孩子购买学期会员</view>
        <!-- 教材版本 -->
        <view class="selector-row">
          <text class="selector-lbl">教材</text>
          <picker
            :range="textbookOptions"
            :value="textbookOptions.indexOf(textbook)"
            @change="(e: any) => textbook = textbookOptions[e.detail.value]"
          >
            <view class="selector-val">{{ textbook }} ▾</view>
          </picker>
        </view>
        <!-- 年级 -->
        <view class="selector-row">
          <text class="selector-lbl">年级</text>
          <picker
            :range="gradeOptions"
            :value="gradeOptions.indexOf(grade)"
            @change="(e: any) => grade = gradeOptions[e.detail.value]"
          >
            <view class="selector-val">{{ grade }} ▾</view>
          </picker>
        </view>
        <!-- 学期 -->
        <view class="selector-row">
          <text class="selector-lbl">学期</text>
          <picker
            :range="semesterOptions"
            :value="semesterOptions.indexOf(semester)"
            @change="(e: any) => semester = semesterOptions[e.detail.value]"
          >
            <view class="selector-val">{{ semester }}学期 ▾</view>
          </picker>
        </view>
        <!-- 档位 -->
        <view class="tier-row">
          <view
            v-for="t in tiers"
            :key="t.key"
            class="tier"
            :class="{ active: selectedTier === t.key }"
            @tap="selectedTier = t.key"
          >
            <text class="tier-label">{{ t.label }}</text>
            <text class="tier-price">¥{{ t.price }}/学期</text>
          </view>
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

// ── 学期选择选项（与 semester-purchase.vue 保持同步）──────────────────────────
const textbookOptions = ['译林版', '人教版', '北师大版']
const gradeOptions = [
  '小学3年级', '小学4年级', '小学5年级', '小学6年级',
  '初中7年级', '初中8年级', '初中9年级',
]
const semesterOptions = ['上', '下']

// ── 学期状态 ──────────────────────────────────────────────────────────────────
const textbook = ref('译林版')
const grade = ref('小学5年级')
const semester = ref('上')

// ── 档位（V2 学期定价）────────────────────────────────────────────────────────
type TierKey = 'basic' | 'pro' | 'promax'
const tiers: { key: TierKey; label: string; price: number }[] = [
  { key: 'basic',  label: '基础版', price: 39  },
  { key: 'pro',    label: 'Pro',    price: 79  },
  { key: 'promax', label: 'ProMax', price: 159 },
]
const selectedTier = ref<TierKey>('basic')
const currentPrice = computed(() => tiers.find(t => t.key === selectedTier.value)?.price ?? 39)

// ── 学生 / 诊断报告 ──────────────────────────────────────────────────────────
const studentId = ref('')
const report = ref<any>(null)
const loading = ref(true)
const paying = ref(false)

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

// ── M45 知识点台账 ───────────────────────────────────────────────────────────
function goKpMastery() {
  uni.navigateTo({ url: `/pages/relative/student-kp?studentId=${studentId.value}` })
}

// ── V2 学期代付 ───────────────────────────────────────────────────────────────
async function onPay() {
  paying.value = true
  try {
    const order = await createOrder({
      tier: selectedTier.value,
      order_type: 'new',
      semesters: [
        {
          textbook_version: textbook.value,
          grade: grade.value,
          semester: semester.value as '上' | '下',
        },
      ],
      target_student_id: studentId.value || undefined,
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
/* 学期选择器 */
.selector-row { display: flex; align-items: center; justify-content: space-between; padding: 14rpx 0; border-bottom: 1rpx solid var(--c-border); }
.selector-lbl { font-size: 26rpx; color: var(--c-text-hint); }
.selector-val { font-size: 26rpx; color: var(--c-ink); }
/* 档位 */
.tier-row { display: flex; gap: 16rpx; margin: 20rpx 0 16rpx; }
.tier { flex: 1; text-align: center; padding: 16rpx 8rpx; border: 2rpx solid var(--c-border); border-radius: var(--r-md); display: flex; flex-direction: column; gap: 4rpx; }
.tier.active { border-color: var(--c-gold); background: var(--c-primary-faint); }
.tier-label { font-size: 24rpx; font-weight: 700; color: var(--c-ink); }
.tier-price { font-size: 22rpx; color: var(--c-text-hint); }
.tier.active .tier-label { color: var(--c-gold); }
.tier.active .tier-price { color: var(--c-gold); }
/* 按钮 */
.btn-primary { background: var(--c-primary); color: var(--c-ink); border-radius: var(--r-btn); padding: 20rpx; font-weight: 700; font-size: 28rpx; }
.btn-primary[disabled] { background: var(--c-primary-soft); color: #b9a94e; }
/* 打卡日历 */
.cal-summary { font-size: 24rpx; color: var(--c-text-hint); margin-bottom: 16rpx; }
.cal-grid { display: flex; flex-wrap: wrap; }
.cal-cell { width: 14.28%; height: 64rpx; display: flex; align-items: center; justify-content: center; font-size: 24rpx; color: var(--c-text-body); }
.cal-cell.checked { color: var(--c-gold); font-weight: 700; }
.cal-cell.blank { visibility: hidden; }
/* M45 入口卡片 */
.entry-card { display: flex; justify-content: space-between; align-items: center; }
.entry-text { font-size: 28rpx; font-weight: 700; color: var(--c-ink); }
.entry-arrow { font-size: 32rpx; color: var(--c-text-hint); }
</style>
