<!-- src/pages/orders/list.vue 订单记录（含退款 / 申诉，§4.2）-->
<template>
  <view class="orders-page">
    <view v-if="loading" class="tip">加载中…</view>
    <view v-else-if="!orders.length" class="tip">暂无订单</view>

    <view v-else>
      <view v-for="o in orders" :key="o.id" class="card">
        <view class="o-top">
          <text class="o-tier">{{ tierName(o.tier) }}会员</text>
          <text class="o-status" :class="statusClass(o)">{{ statusText(o) }}</text>
        </view>
        <view class="o-row"><text class="o-k">订单号</text><text class="o-v">{{ o.order_no }}</text></view>
        <view class="o-row"><text class="o-k">金额</text><text class="o-v">¥{{ (o.amount_fen / 100).toFixed(2) }}</text></view>
        <view class="o-row"><text class="o-k">时长</text><text class="o-v">{{ o.duration_months }} 个月</text></view>
        <view class="o-row"><text class="o-k">下单时间</text><text class="o-v">{{ fmt(o.created_at) }}</text></view>

        <!-- 退款/申诉处理信息 -->
        <view v-if="refundLine(o)" class="o-refund">{{ refundLine(o) }}</view>
        <!-- 发票状态 -->
        <view v-if="invLine(o)" class="o-invoice">{{ invLine(o) }}</view>

        <!-- 操作区 -->
        <view class="o-acts">
          <template v-if="canAct(o)">
            <text class="act act-refund" @tap="onRefund(o)">申请退款</text>
            <text class="act act-appeal" @tap="openAppeal(o)">申诉</text>
          </template>
          <text v-if="canInvoice(o)" class="act act-invoice" @tap="openInvoice(o)">申请开票</text>
        </view>
      </view>
    </view>

    <!-- 开票表单弹窗 -->
    <view v-if="invOpen" class="ap-mask">
      <view class="ap-card">
        <view class="ap-head">
          <text class="ap-title">申请开票</text>
          <text class="ap-x" @tap="invOpen = false">×</text>
        </view>
        <text class="ap-label">抬头类型</text>
        <view class="inv-types">
          <text class="inv-type" :class="{ on: invForm.title_type === 'personal' }" @tap="invForm.title_type = 'personal'">个人</text>
          <text class="inv-type" :class="{ on: invForm.title_type === 'company' }" @tap="invForm.title_type = 'company'">企业</text>
        </view>
        <text class="ap-label">发票抬头</text>
        <input v-model="invForm.title" class="ap-input" :placeholder="invForm.title_type === 'company' ? '公司全称' : '个人姓名'" />
        <template v-if="invForm.title_type === 'company'">
          <text class="ap-label">税号</text>
          <input v-model="invForm.tax_no" class="ap-input" placeholder="统一社会信用代码" />
        </template>
        <text class="ap-label">接收邮箱（选填）</text>
        <input v-model="invForm.email" class="ap-input" placeholder="电子发票发送至此邮箱" />
        <button class="ap-submit" :disabled="invSubmitting" @tap="submitInvoice">
          {{ invSubmitting ? '提交中…' : '提交开票申请' }}
        </button>
      </view>
    </view>

    <!-- 申诉表单弹窗 -->
    <view v-if="appealOpen" class="ap-mask">
      <view class="ap-card">
        <view class="ap-head">
          <text class="ap-title">提交申诉</text>
          <text class="ap-x" @tap="appealOpen = false">×</text>
        </view>
        <text class="ap-tip">超 7 天仅特定情形可申诉（每年限 1 次）。</text>

        <text class="ap-label">申诉类型</text>
        <picker :range="appealLabels" @change="onTypeChange">
          <view class="ap-picker">{{ appealLabels[appealTypeIdx] }}</view>
        </picker>

        <text class="ap-label">申诉说明</text>
        <textarea v-model="appealNote" class="ap-textarea" placeholder="请填写具体原因…" maxlength="500" />

        <text class="ap-label">证明截图（{{ evidence.length }}/3）</text>
        <view class="ap-imgs">
          <image v-for="(u, i) in evidence" :key="i" :src="u" class="ap-img" mode="aspectFill" @tap="removeImg(i)" />
          <view v-if="evidence.length < 3" class="ap-add" :class="{ busy: imgUploading }" @tap="addImg">
            {{ imgUploading ? '…' : '+' }}
          </view>
        </view>

        <button class="ap-submit" :disabled="submitting" @tap="submitAppealForm">
          {{ submitting ? '提交中…' : '提交申诉' }}
        </button>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { getMyOrders, requestRefund, submitAppeal, requestInvoice, getMyInvoices, type MyInvoice } from '@/api/orders'
import { uploadOneImage } from '@/composables/useUpload'
import type { OrderOut } from '@/types/api'

const loading = ref(true)
const orders = ref<OrderOut[]>([])
const invoices = ref<MyInvoice[]>([])   // 我的开票申请（按 order_id 映射状态）

const TIER: Record<string, string> = { basic: '基础', pro: 'Pro', promax: 'ProMax' }
function tierName(t: string) { return TIER[t] || t }

// 状态码 → 中文
const REFUND_TXT: Record<string, string> = {
  AUTO_FULL_REFUND: '已全额退款',
  MANUAL_REVIEW_PARTIAL: '退款审核中（按比例）',
  REFUND_PARTIAL_APPROVED: '已按比例退款',
  REJECT_BANNED: '退款被拒（账号封禁）',
  REJECT_PROMOTIONAL: '退款被拒（活动价）',
  REJECT_OVERTIME: '退款被拒（超7天）',
  REJECT_USED_HIGH_TIER: '退款被拒（已用高阶功能）',
}
const APPEAL_TXT: Record<string, string> = {
  MANUAL_REVIEW_APPEAL: '申诉审核中',
  AUTO_FAULT_COMPENSATION: '故障已赔付',
  AUTO_DUPLICATE_REFUND: '重复订单已退款',
  APPEAL_APPROVED: '申诉通过',
  APPEAL_REJECTED: '申诉驳回',
  REJECT_FAULT_UNVERIFIED: '申诉被拒（故障未核实）',
  REJECT_DUPLICATE_INELIGIBLE: '申诉被拒（不符合重复购买）',
}

function statusText(o: OrderOut) {
  const m: Record<string, string> = {
    pending: '待支付', paid: '已支付', refunded: '已退款', partial_refunded: '部分退款',
  }
  return m[o.status] || o.status
}
function statusClass(o: OrderOut) {
  if (o.status === 'refunded' || o.status === 'partial_refunded') return 'st-refunded'
  if (o.status === 'paid') return 'st-paid'
  return 'st-pending'
}
function refundLine(o: OrderOut) {
  if (o.refund_status && o.refund_status !== 'NONE') return REFUND_TXT[o.refund_status] || o.refund_status
  if (o.appeal_status && o.appeal_status !== 'NONE') return APPEAL_TXT[o.appeal_status] || o.appeal_status
  return ''
}
// 仅已支付且未发起过退款/申诉的订单可操作
function canAct(o: OrderOut) {
  return o.status === 'paid'
    && (!o.refund_status || o.refund_status === 'NONE')
    && (!o.appeal_status || o.appeal_status === 'NONE')
}
function fmt(s: string) { return (s || '').replace('T', ' ').slice(0, 16) }

// ── 发票 ──
const INV_TXT: Record<string, string> = { pending: '开票申请中', issued: '已开票', rejected: '开票被驳回' }
function invFor(o: OrderOut) { return invoices.value.find(v => v.order_id === o.id) }
function invLine(o: OrderOut) {
  const v = invFor(o)
  if (!v) return ''
  return `🧾 ${INV_TXT[v.status] || v.status}` + (v.status === 'issued' && v.invoice_no ? `（${v.invoice_no}）` : '')
}
// 已支付、未退款、且无进行中/已开票申请 → 可申请开票（驳回后可重申）
function canInvoice(o: OrderOut) {
  if (o.status !== 'paid') return false
  const v = invFor(o)
  return !v || v.status === 'rejected'
}

async function load() {
  loading.value = true
  try {
    orders.value = await getMyOrders()
    try { invoices.value = await getMyInvoices() } catch { /* 忽略 */ }
  }
  catch (e) { uni.showToast({ title: (e as Error).message || '加载失败', icon: 'none' }) }
  finally { loading.value = false }
}

// 开票弹窗
const invOpen = ref(false)
const invSubmitting = ref(false)
const invForm = reactive({ order_id: '', title_type: 'personal', title: '', tax_no: '', email: '' })
function openInvoice(o: OrderOut) {
  Object.assign(invForm, { order_id: o.id, title_type: 'personal', title: '', tax_no: '', email: '' })
  invOpen.value = true
}
async function submitInvoice() {
  if (!invForm.title.trim()) { uni.showToast({ title: '请填写发票抬头', icon: 'none' }); return }
  if (invForm.title_type === 'company' && !invForm.tax_no.trim()) {
    uni.showToast({ title: '企业抬头需填税号', icon: 'none' }); return
  }
  invSubmitting.value = true
  try {
    await requestInvoice({
      order_id: invForm.order_id, title_type: invForm.title_type, title: invForm.title.trim(),
      tax_no: invForm.tax_no.trim() || undefined, email: invForm.email.trim() || undefined,
    })
    uni.showToast({ title: '开票申请已提交', icon: 'success' })
    invOpen.value = false
    await load()
  } catch (e) {
    uni.showToast({ title: (e as Error).message || '提交失败', icon: 'none' })
  } finally { invSubmitting.value = false }
}

function onRefund(o: OrderOut) {
  uni.showModal({
    title: '申请退款',
    content: '系统将按规则自动判定：7天内未使用全额退；已使用按剩余天数比例退（转人工）。确认申请？',
    success: async (r) => {
      if (!r.confirm) return
      try {
        const res = await requestRefund(o.id)
        uni.showToast({ title: res.status === 'completed' ? '退款成功' : '已提交审核', icon: 'success' })
        await load()
      } catch (e) {
        uni.showToast({ title: (e as Error).message || '申请失败', icon: 'none' })
      }
    },
  })
}

// —— 申诉表单 ——
const appealOpen = ref(false)
const appealOrder = ref<OrderOut | null>(null)
const appealTypes = ['SYSTEM_FAULT', 'DESC_MISMATCH', 'DUPLICATE_PURCHASE', 'MINOR_PURCHASE']
const appealLabels = ['平台系统故障', '服务描述不符', '误操作重复购买', '未成年人未授权购买']
const appealTypeIdx = ref(1)
const appealNote = ref('')
const evidence = ref<string[]>([])
const imgUploading = ref(false)
const submitting = ref(false)

function openAppeal(o: OrderOut) {
  appealOrder.value = o
  appealTypeIdx.value = 1
  appealNote.value = ''
  evidence.value = []
  appealOpen.value = true
}
function onTypeChange(e: { detail: { value: number } }) { appealTypeIdx.value = e.detail.value }

function addImg() {
  if (imgUploading.value || evidence.value.length >= 3) return
  uni.chooseImage({
    count: 1, sizeType: ['compressed'],
    success: async (res) => {
      const path = (res.tempFilePaths || [])[0]
      if (!path) return
      imgUploading.value = true
      try {
        const url = await uploadOneImage(path)
        evidence.value.push(url)
      } catch (e) {
        uni.showToast({ title: (e as Error).message || '上传失败', icon: 'none' })
      } finally { imgUploading.value = false }
    },
  })
}
function removeImg(i: number) { evidence.value.splice(i, 1) }

async function submitAppealForm() {
  if (!appealOrder.value || submitting.value) return
  if (!appealNote.value.trim()) { uni.showToast({ title: '请填写申诉说明', icon: 'none' }); return }
  submitting.value = true
  try {
    const res = await submitAppeal(appealOrder.value.id, {
      appeal_type: appealTypes[appealTypeIdx.value],
      note: appealNote.value.trim(),
      evidence_urls: evidence.value.length ? [...evidence.value] : undefined,
    })
    const done = res.status === 'completed'
    uni.showToast({ title: done ? '已自动处理' : '申诉已提交', icon: 'success' })
    appealOpen.value = false
    await load()
  } catch (e) {
    uni.showToast({ title: (e as Error).message || '提交失败', icon: 'none' })
  } finally { submitting.value = false }
}

onMounted(load)
</script>

<style scoped>
.orders-page { padding: 20rpx; background: var(--c-bg-page); min-height: 100vh; }
.tip { text-align: center; padding: 120rpx; color: var(--c-text-hint); }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: 24rpx; margin-bottom: 18rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.o-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14rpx; }
.o-tier { font-size: 30rpx; font-weight: 800; color: var(--c-ink); }
.o-status { font-size: 24rpx; font-weight: 600; }
.st-paid { color: var(--c-primary-deep); }
.st-refunded { color: var(--c-text-hint); }
.st-pending { color: var(--c-warning, #ffb020); }
.o-row { display: flex; justify-content: space-between; font-size: 24rpx; color: var(--c-text-second); padding: 4rpx 0; }
.o-k { color: var(--c-text-hint); }
.o-v { color: var(--c-text-body); }
.o-refund { margin-top: 12rpx; font-size: 24rpx; color: var(--c-primary-deep); background: var(--c-primary-faint); border-radius: var(--r-md); padding: 12rpx 16rpx; }
.o-invoice { margin-top: 8rpx; font-size: 24rpx; color: var(--c-text-second); background: var(--c-bg-soft); border-radius: var(--r-md); padding: 12rpx 16rpx; }
.act-invoice { color: var(--c-primary-deep); border: 2rpx solid var(--c-primary-soft); }
.inv-types { display: flex; gap: 16rpx; margin-bottom: 8rpx; }
.inv-type { flex: 1; text-align: center; padding: 16rpx; border: 2rpx solid var(--c-border); border-radius: var(--r-md); font-size: 28rpx; color: var(--c-text-body); }
.inv-type.on { border-color: var(--c-primary); background: var(--c-primary-faint); color: var(--c-primary-deep); font-weight: 700; }
.ap-input { background: var(--c-bg-soft); border-radius: var(--r-md); padding: 18rpx; width: 100%; box-sizing: border-box; font-size: 26rpx; color: var(--c-ink); margin-bottom: 4rpx; }
.o-acts { display: flex; gap: 16rpx; margin-top: 16rpx; justify-content: flex-end; }
.act { font-size: 26rpx; padding: 10rpx 28rpx; border-radius: var(--r-pill); }
.act-refund { color: var(--c-danger); border: 2rpx solid var(--c-danger); }
.act-appeal { color: var(--c-text-second); border: 2rpx solid var(--c-border); }
/* 申诉弹窗 */
.ap-mask { position: fixed; inset: 0; background: rgba(0,0,0,.5); display: flex; align-items: center; justify-content: center; z-index: 1100; }
.ap-card { width: 620rpx; background: var(--c-bg-card); border-radius: var(--r-lg); padding: 30rpx 26rpx; max-height: 84vh; overflow-y: auto; }
.ap-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14rpx; }
.ap-title { font-size: 32rpx; font-weight: 800; color: var(--c-ink); }
.ap-x { font-size: 44rpx; color: var(--c-text-hint); padding: 0 8rpx; }
.ap-tip { display: block; font-size: 24rpx; color: var(--c-text-hint); margin-bottom: 16rpx; }
.ap-label { display: block; font-size: 26rpx; font-weight: 600; color: var(--c-text-body); margin: 16rpx 0 8rpx; }
.ap-picker { background: var(--c-bg-soft); border-radius: var(--r-md); padding: 20rpx; font-size: 28rpx; color: var(--c-ink); }
.ap-textarea { background: var(--c-bg-soft); border-radius: var(--r-md); padding: 18rpx; width: 100%; box-sizing: border-box; height: 160rpx; font-size: 26rpx; color: var(--c-ink); }
.ap-imgs { display: flex; flex-wrap: wrap; gap: 16rpx; }
.ap-img { width: 150rpx; height: 150rpx; border-radius: var(--r-md); }
.ap-add { width: 150rpx; height: 150rpx; border-radius: var(--r-md); border: 2rpx dashed var(--c-border); display: flex; align-items: center; justify-content: center; font-size: 56rpx; color: var(--c-text-hint); }
.ap-add.busy { font-size: 32rpx; }
.ap-submit { margin-top: 24rpx; background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-pill); font-size: 30rpx; font-weight: 700; height: 84rpx; line-height: 84rpx; }
</style>
