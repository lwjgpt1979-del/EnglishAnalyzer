<template>
  <view class="kp-box">
    <view class="kp-toggle" @tap="open = !open">
      <view class="ic ic-target kp-tg-ic" />
      <text class="kp-toggle-t">考点拓展{{ root ? ' · 词根 ' + root : '' }}</text>
      <text class="kp-arrow" :class="{ open }">▾</text>
    </view>

    <view v-if="open" class="kp-body">
      <text class="kp-hint">点脑图任一叶子节点 → 下方切到该维度并高亮词条</text>

      <!-- 脑图:中心词 + 各维度代表叶子(6 槽放射),spokes 用背景 SVG,叶子/中心/维度标签为可点 view -->
      <view class="mind" :style="spokesBg">
        <view class="mind-center"><text class="mc-w">{{ centerText }}</text><text v-if="centerZh" class="mc-zh">{{ centerZh }}</text></view>
        <text v-for="lf in leaves" :key="'lb'+lf.slot" class="mind-lbl" :class="'dc-' + lf.cat" :style="lblPos(lf.slot)">{{ lf.dimShort }}</text>
        <view v-for="lf in leaves" :key="'lf'+lf.slot" class="mind-leaf"
              :class="{ on: activeDim === lf.dimKey && activeItem === lf.itemKey, low: lf.item?.confidence === 'low' }"
              :style="leafPos(lf.slot)"
              @tap="tapLeaf(lf)">
          <text>{{ lf.text }}</text>
        </view>
      </view>

      <!-- 维度 Tab -->
      <scroll-view scroll-x class="kp-tabs" :show-scrollbar="false">
        <text v-for="d in dims" :key="d.key" class="kp-tab" :class="{ on: activeDim === d.key }" @tap="activeDim = d.key">{{ d.label }}</text>
      </scroll-view>

      <!-- 选中维度的词条列表(关系维 chips 化行 / 考法维文本行)-->
      <view v-if="curDim">
        <template v-if="curDim.relational">
          <view v-for="(it, i) in curDim.items" :key="i" class="kp-line"
                :class="{ hl: activeItem === itemKey(it, i), reported: it.id && reported[it.id] }">
            <view class="kp-line-body">
              <text class="kp-en">{{ it.text }}<text v-if="it.confidence === 'low'" class="kp-low"> 待核</text></text>
              <text v-if="it.zh || it.note" class="kp-zh">{{ it.zh }}{{ it.note ? (it.zh ? ' · ' : '') + it.note : '' }}</text>
            </view>
            <view v-if="it.id" class="ic ic-flag kp-report" :class="{ done: reported[it.id] }" @tap.stop="openReport(it)" />
          </view>
        </template>
        <template v-else>
          <view v-for="(it, i) in curDim.items" :key="i" class="kp-line" :class="{ reported: it.id && reported[it.id] }">
            <view class="kp-line-body">
              <text class="kp-en">{{ it.text }}</text>
              <text v-if="it.zh || it.note" class="kp-zh">{{ it.zh }}{{ it.note ? (it.zh ? ' · ' : '') + it.note : '' }}</text>
            </view>
            <view v-if="it.id" class="ic ic-flag kp-report" :class="{ done: reported[it.id] }" @tap.stop="openReport(it)" />
          </view>
        </template>
      </view>

      <!-- 考点扩展测试(内嵌考点拓展)-->
      <view class="kp-test" @tap="$emit('test')">
        <view class="ic ic-target kp-test-ic" /><text>{{ testLoading ? '出题中…' : '考点扩展测试' }}</text>
      </view>
    </view>

    <!-- 有凭证举报 -->
    <view v-if="reportOpen" class="rp-mask" @tap="reportOpen = false">
      <view class="rp-sheet" @tap.stop>
        <text class="rp-title">举报考点</text>
        <text class="rp-sub">「{{ reportItem?.text }}」· 请选原因，并填写说明或正确项</text>
        <view class="rp-reasons">
          <text v-for="r in REASONS" :key="r.v" class="rp-chip" :class="{ on: reportReason === r.v }"
                @tap="reportReason = r.v">{{ r.l }}</text>
        </view>
        <textarea class="rp-ta" v-model="reportDetail" placeholder="说明问题（至少 4 字，或下方填正确项）" maxlength="200" />
        <input class="rp-in" v-model="reportSuggested" placeholder="我认为正确的词/用法（可选）" maxlength="80" />
        <view class="rp-acts">
          <text class="rp-btn ghost" @tap="reportOpen = false">取消</text>
          <text class="rp-btn pri" @tap="submitReport">提交</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { WordKp, KpDim, KpItem } from '@/api/vocabulary'

const props = defineProps<{
  wordKp: WordKp
  centerText: string           // 中心节点主字(词/义项 gloss)
  centerZh?: string            // 中心节点副字(中文简释)
  reported?: Record<string, boolean>
  testLoading?: boolean
}>()
const emit = defineEmits<{
  (e: 'report', payload: { item: KpItem; reason: string; detail: string; suggested: string }): void
  (e: 'test'): void
}>()

const REASONS = [
  { v: 'meaning_mismatch', l: '词义不符' },
  { v: 'out_of_syllabus', l: '超纲' },
  { v: 'confuse_wrong', l: '形近误导' },
  { v: 'collocation_fake', l: '搭配不真实' },
  { v: 'other', l: '其它' },
]

const reportOpen = ref(false)
const reportItem = ref<KpItem | null>(null)
const reportReason = ref('meaning_mismatch')
const reportDetail = ref('')
const reportSuggested = ref('')

/** 打开有凭证举报表单 */
function openReport(it: KpItem) {
  if (!it.id || (props.reported || {})[it.id]) return
  reportItem.value = it
  reportReason.value = 'meaning_mismatch'
  reportDetail.value = ''
  reportSuggested.value = ''
  reportOpen.value = true
}

/** 校验凭证后交给父组件提交 */
function submitReport() {
  const it = reportItem.value
  if (!it?.id) return
  const detail = reportDetail.value.trim()
  const suggested = reportSuggested.value.trim()
  if (detail.length < 4 && !suggested) {
    uni.showToast({ title: '请填说明或正确项', icon: 'none' })
    return
  }
  reportOpen.value = false
  emit('report', { item: it, reason: reportReason.value, detail, suggested })
}

const open = ref(true)
const reported = computed(() => props.reported || {})
const root = computed(() => props.wordKp?.root || '')

// 维度:优先用 wordKp.dims(主/选定义项),否则取第一个义项的 dims
const dims = computed<KpDim[]>(() => {
  const w = props.wordKp
  if (w?.dims && w.dims.length) return w.dims
  return (w?.senses?.[0]?.dims) || []
})
const activeDim = ref('')
watch(dims, (d) => { if (d.length && !d.some(x => x.key === activeDim.value)) activeDim.value = d[0].key }, { immediate: true })
const curDim = computed(() => dims.value.find(d => d.key === activeDim.value) || null)

function itemKey(it: KpItem, i: number) { return it.id || (it.text + ':' + i) }
const activeItem = ref('')

// 维度短标签 + 配色类(近义绿/反义&易混橙/派生蓝/搭配蓝/其它灰)
function dimShort(label: string) { return (label || '').split('·')[0].slice(0, 4) }
function dimCat(label: string) {
  if (label.includes('近义')) return 'syn'
  if (label.includes('反义')) return 'ant'
  if (label.includes('易混')) return 'conf'
  if (label.includes('派生') || label.includes('词族')) return 'deriv'
  if (label.includes('搭配')) return 'colloc'
  return 'other'
}

// 叶子:仅取关系维的代表项;高置信优先占槽,最多 6 个
const SLOTS = 6
const leaves = computed(() => {
  const out: any[] = []
  for (const d of dims.value) {
    if (!d.relational) continue
    const sorted = [...d.items].sort((a, b) =>
      (a.confidence === 'low' ? 1 : 0) - (b.confidence === 'low' ? 1 : 0))
    for (let i = 0; i < sorted.length && out.length < SLOTS; i++) {
      out.push({ dimKey: d.key, dimShort: dimShort(d.label), cat: dimCat(d.label),
                 text: sorted[i].text || '', itemKey: itemKey(sorted[i], i), item: sorted[i] })
    }
    if (out.length >= SLOTS) break
  }
  return out.slice(0, SLOTS).map((x, idx) => ({ ...x, slot: idx }))
})

function tapLeaf(lf: any) {
  activeDim.value = lf.dimKey
  activeItem.value = lf.itemKey
}
// 6 槽固定坐标(百分比):中心(50,48);上/左上/右上/左下/右下/下
const SLOT_POS = [
  { x: 50, y: 11 }, { x: 17, y: 27 }, { x: 83, y: 27 },
  { x: 17, y: 71 }, { x: 83, y: 71 }, { x: 50, y: 89 },
]
const CENTER = { x: 50, y: 48 }
function leafPos(slot: number) {
  const p = SLOT_POS[slot] || CENTER
  return { left: p.x + '%', top: p.y + '%' }
}
function lblPos(slot: number) {
  const p = SLOT_POS[slot] || CENTER
  return { left: (CENTER.x + (p.x - CENTER.x) * 0.5) + '%', top: (CENTER.y + (p.y - CENTER.y) * 0.5) + '%' }
}
// spokes:按当前叶子数画放射线(SVG 背景,0..100 viewBox 拉伸铺满)
const spokesBg = computed(() => {
  const lines = leaves.value.map(lf => {
    const p = SLOT_POS[lf.slot]
    return `%3Cline x1='${CENTER.x}' y1='${CENTER.y}' x2='${p.x}' y2='${p.y}' stroke='%23d5deea' stroke-width='0.7'/%3E`
  }).join('')
  const svg = `%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100' preserveAspectRatio='none'%3E${lines}%3C/svg%3E`
  return { backgroundImage: `url("data:image/svg+xml,${svg}")` }
})
</script>

<style scoped>
.kp-box { margin-top: 8rpx; }
.kp-toggle { display: flex; align-items: center; gap: 10rpx; padding: 16rpx 20rpx; background: #eef5ff; border-radius: 14rpx; }
.kp-tg-ic { width: 28rpx; height: 28rpx; }
.kp-toggle-t { flex: 1; font-size: 26rpx; font-weight: 600; color: #185fa5; }
.kp-arrow { font-size: 24rpx; color: #9aa4b2; transition: transform .2s; }
.kp-arrow.open { transform: rotate(180deg); }
.kp-body { padding: 12rpx 4rpx 0; }
.kp-hint { display: block; text-align: center; font-size: 20rpx; color: #adb5c0; margin-bottom: 6rpx; }
/* 脑图 */
.mind { position: relative; width: 100%; height: 460rpx; background-size: 100% 100%; background-repeat: no-repeat; }
.mind-center { position: absolute; left: 50%; top: 48%; transform: translate(-50%,-50%); background: #e9f6f1; border: 2rpx solid #8cc2a6; border-radius: 16rpx; padding: 10rpx 18rpx; max-width: 260rpx; text-align: center; }
.mc-w { display: block; font-size: 28rpx; font-weight: 800; color: #1f7a5e; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mc-zh { display: block; font-size: 19rpx; color: #5f9c86; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mind-leaf { position: absolute; transform: translate(-50%,-50%); background: #eaf2ff; border: 2rpx solid #bcd8ff; border-radius: 12rpx; padding: 8rpx 16rpx; max-width: 200rpx; }
.mind-leaf text { font-size: 24rpx; font-weight: 600; color: #185fa5; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mind-leaf.on { background: #e6f0ff; border-color: #3d8bf5; border-width: 3rpx; }
.mind-leaf.on text { color: #0c447c; }
.mind-leaf.low { background: #f2f4f8; border-color: #dde3ea; }
.mind-leaf.low text { color: #94a3b8; font-weight: 500; }
.mind-leaf.low.on { background: #eef1f5; border-color: #9aa4b2; }
.mind-leaf.low.on text { color: #5f6b7a; }
.mind-lbl { position: absolute; transform: translate(-50%,-50%); font-size: 20rpx; padding: 0 6rpx; background: rgba(255,255,255,.85); border-radius: 5rpx; }
.dc-syn { color: #3b8f5f; } .dc-ant { color: #b0651a; } .dc-conf { color: #c2711a; } .dc-deriv { color: #2b7fb0; } .dc-colloc { color: #3170c0; } .dc-other { color: #8a93a3; }
/* Tab */
.kp-tabs { white-space: nowrap; padding: 6rpx 0 12rpx; }
.kp-tab { display: inline-block; font-size: 24rpx; padding: 8rpx 24rpx; margin-right: 14rpx; border-radius: 999rpx; background: #f2f5f9; color: #5f6b7a; border: 2rpx solid #e6ebf1; }
.kp-tab.on { background: #e9f2fe; color: #185fa5; border-color: #bcd8ff; font-weight: 600; }
/* 列表 */
.kp-line { display: flex; align-items: center; gap: 12rpx; padding: 16rpx 8rpx; border-top: 2rpx solid #f2f4f8; }
.kp-line:first-child { border-top: none; }
.kp-line.hl { background: #eef5ff; border-radius: 10rpx; }
.kp-line-body { flex: 1; min-width: 0; }
.kp-en { font-size: 26rpx; font-weight: 600; color: #1f2733; }
.kp-low { font-size: 18rpx; color: #b0651a; }
.kp-zh { display: block; font-size: 22rpx; color: #5f6b7a; margin-top: 3rpx; line-height: 1.5; }
.kp-report { width: 30rpx; height: 30rpx; flex-shrink: 0; opacity: .5; }
.kp-report.done { opacity: 1; }
.kp-line.reported { opacity: .55; }
/* 测试 */
.kp-test { margin-top: 16rpx; display: flex; align-items: center; justify-content: center; gap: 8rpx;
  padding: 18rpx; background: #eef5ff; border-radius: 14rpx; color: #185fa5; font-size: 26rpx; font-weight: 700; }
.kp-test-ic { width: 28rpx; height: 28rpx; }
/* 有凭证举报 */
.rp-mask { position: fixed; left: 0; right: 0; top: 0; bottom: 0; background: rgba(15,23,42,.45); z-index: 1000;
  display: flex; align-items: flex-end; }
.rp-sheet { width: 100%; background: #fff; border-radius: 24rpx 24rpx 0 0; padding: 28rpx 28rpx calc(28rpx + env(safe-area-inset-bottom)); }
.rp-title { display: block; font-size: 30rpx; font-weight: 800; color: #1f2733; }
.rp-sub { display: block; font-size: 22rpx; color: #94a3b8; margin: 8rpx 0 16rpx; line-height: 1.45; }
.rp-reasons { display: flex; flex-wrap: wrap; gap: 12rpx; margin-bottom: 16rpx; }
.rp-chip { font-size: 24rpx; padding: 10rpx 20rpx; border-radius: 999rpx; background: #f2f5f9; color: #5f6b7a; border: 2rpx solid #e6ebf1; }
.rp-chip.on { background: #e8f2ff; color: #185fa5; border-color: #bcd8ff; font-weight: 700; }
.rp-ta { width: 100%; min-height: 140rpx; background: #f7f9fc; border-radius: 12rpx; padding: 16rpx; font-size: 26rpx; box-sizing: border-box; margin-bottom: 12rpx; }
.rp-in { width: 100%; background: #f7f9fc; border-radius: 12rpx; padding: 16rpx; font-size: 26rpx; box-sizing: border-box; margin-bottom: 20rpx; }
.rp-acts { display: flex; gap: 16rpx; }
.rp-btn { flex: 1; text-align: center; padding: 18rpx; border-radius: 12rpx; font-size: 28rpx; font-weight: 700; }
.rp-btn.ghost { background: #f2f5f9; color: #5f6b7a; }
.rp-btn.pri { background: #3d8bf5; color: #fff; }
</style>
