<template>
  <view v-if="loading || net.nodes.length >= 2" class="wrn">
    <view class="wrn-head">
      <view class="wrn-title"><view class="ic ic-share" style="width:30rpx;height:30rpx" /><text>错题关系网</text></view>
      <text class="wrn-sub">点词看考点 · 做测试</text>
    </view>

    <view v-if="loading" class="wrn-tip">分析选项关系中…</view>
    <template v-else>
      <view class="wrn-canvas" :style="{ height: BOXH + 'rpx' }">
        <!-- 边 -->
        <view v-for="(e, i) in layout.edges" :key="'e'+i" class="wrn-edge"
          :class="{ dash: e.rel === 'cooccur' }" :style="edgeStyle(e)" />
        <!-- 边标签 -->
        <view v-for="(e, i) in layout.edges" :key="'l'+i" class="wrn-elabel"
          :style="{ left: (e.mx - 30) + 'rpx', top: (e.my - 15) + 'rpx', background: e.bg, color: e.fg }">{{ e.label }}</view>
        <!-- 节点 -->
        <view v-for="n in layout.nodes" :key="n.word_id" class="wrn-node" :class="n.role"
          :style="{ left: (n.x - n.w / 2) + 'rpx', top: (n.y - n.h / 2) + 'rpx', width: n.w + 'rpx' }"
          @tap="openNode(n)">
          <text v-if="n.role === 'answer'" class="wrn-badge ans">正确</text>
          <text v-else-if="n.role === 'error'" class="wrn-badge err">你选</text>
          <text class="wrn-word">{{ n.word }}</text>
          <text v-if="n.zh" class="wrn-zh">{{ n.zh }}</text>
        </view>
      </view>

      <text v-if="folded > 0" class="wrn-folded">另有 {{ folded }} 个选项词未展开(节点较多已收敛)</text>

      <view class="wrn-foot">
        <view class="wrn-legend">
          <view v-for="l in legendShown" :key="l.rel" class="wrn-lg">
            <view class="wrn-ln" :class="{ dash: l.rel === 'cooccur' }" :style="{ background: l.c }" /><text>{{ l.label }}</text>
          </view>
        </view>
        <view v-if="hasCooccur" class="wrn-toggle" @tap="showCooccur = !showCooccur">
          <view class="wrn-sw" :class="{ on: showCooccur }" /><text>共现</text>
        </view>
      </view>
    </template>

    <WordKpCard v-if="picked" :word-id="picked.word_id" :word="picked.word" :zh="picked.zh" @close="picked = null" />
  </view>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { getWrongRelations } from '@/api/wrongQuestions'
import type { WrongRelationNet, WrongRelNode, WrongRelEdge } from '@/api/wrongQuestions'
import WordKpCard from '@/components/WordKpCard.vue'

const props = defineProps<{ wrongRecordId: string; correctAnswer?: string; studentAnswer?: string }>()

const WORDFORM = { c: '#1D9E75', bg: '#E1F5EE', fg: '#0F6E56' }   // 词形族共用色
const REL: Record<string, { c: string; bg: string; fg: string; label: string }> = {
  synonym: { c: '#639922', bg: '#EAF3DE', fg: '#3B6D11', label: '近义' },
  antonym: { c: '#E24B4A', bg: '#FCEBEB', fg: '#A32D2D', label: '反义' },
  confusion: { c: '#EF9F27', bg: '#FAEEDA', fg: '#854F0B', label: '易混' },
  ambiguity: { c: '#7F77DD', bg: '#EEEDFE', fg: '#534AB7', label: '歧义' },
  related: { c: '#378ADD', bg: '#E6F1FB', fg: '#185FA5', label: '其他' },
  derivation: { ...WORDFORM, label: '派生' },
  tense: { ...WORDFORM, label: '时态' },
  plural: { ...WORDFORM, label: '单复数' },
  comparative: { ...WORDFORM, label: '比较级' },
  cooccur: { c: '#B4B2A9', bg: '#F1EFE8', fg: '#5F5E5A', label: '共现' },
}
const REL_ORDER = ['synonym', 'antonym', 'confusion', 'ambiguity', 'related',
  'derivation', 'tense', 'plural', 'comparative']

const BOXW = 690, CX = 345, CY = 300, R = 200, BOXH = 600
const MAX_NODES = 8

const net = ref<WrongRelationNet>({ nodes: [], edges: [] })
const loading = ref(true)
const showCooccur = ref(false)
const picked = ref<WrongRelNode | null>(null)

async function load() {
  loading.value = true
  try { net.value = await getWrongRelations(props.wrongRecordId) } catch { net.value = { nodes: [], edges: [] } }
  finally { loading.value = false }
}
watch(() => props.wrongRecordId, (v) => { if (v) load() }, { immediate: true })

function norm(s?: string): string {
  return (s || '').replace(/^[A-Da-d][.、,)\s]+/, '').trim().toLowerCase()
}
function matchId(answer?: string): string | null {
  const a = norm(answer)
  if (!a) return null
  const hit = net.value.nodes.find(n => n.word.toLowerCase() === a
    || a.includes(n.word.toLowerCase()) || n.word.toLowerCase().includes(a))
  return hit ? hit.word_id : null
}

const hasCooccur = computed(() => net.value.edges.some(e => e.relation === 'cooccur'))
const legendShown = computed(() => {
  const present = new Set(net.value.edges.map(e => e.relation))
  const arr = REL_ORDER.filter(r => present.has(r)).map(r => ({ rel: r, ...REL[r] }))
  if (showCooccur.value && present.has('cooccur')) arr.push({ rel: 'cooccur', ...REL.cooccur })
  return arr
})

const folded = ref(0)
const layout = computed(() => {
  const all = net.value.nodes
  const ansId = matchId(props.correctAnswer)
  const errId = matchId(props.studentAnswer)
  // 边(按开关过滤共现)
  let edges = net.value.edges.filter(e => showCooccur.value || e.relation !== 'cooccur')
  // 节点收敛:优先 答案/错选/有语义边的,>8 折叠
  const deg = new Map<string, number>()
  edges.forEach(e => { deg.set(e.a_word_id, (deg.get(e.a_word_id) || 0) + 1); deg.set(e.b_word_id, (deg.get(e.b_word_id) || 0) + 1) })
  const prio = (n: WrongRelNode) => (n.word_id === ansId ? 100 : 0) + (n.word_id === errId ? 50 : 0) + (deg.get(n.word_id) || 0)
  const sorted = [...all].sort((a, b) => prio(b) - prio(a))
  const shown = sorted.slice(0, MAX_NODES)
  folded.value = Math.max(0, all.length - shown.length)
  const shownIds = new Set(shown.map(n => n.word_id))
  edges = edges.filter(e => shownIds.has(e.a_word_id) && shownIds.has(e.b_word_id))

  // 布局:答案居中,其余环绕;无答案则全环绕
  const pos = new Map<string, { x: number; y: number; role: string; w: number; h: number }>()
  const centerNode = shown.find(n => n.word_id === ansId)
  const ring = centerNode ? shown.filter(n => n.word_id !== ansId) : shown
  if (centerNode) {
    pos.set(centerNode.word_id, { x: CX, y: CY, role: 'answer', w: 168, h: 96 })
  }
  const n = ring.length
  ring.forEach((node, i) => {
    const ang = (-90 + i * (360 / Math.max(n, 1))) * Math.PI / 180
    const role = node.word_id === errId ? 'error' : 'peer'
    pos.set(node.word_id, { x: CX + R * Math.cos(ang), y: CY + R * Math.sin(ang), role, w: 156, h: 78 })
  })

  const nodes = shown.map(node => {
    const p = pos.get(node.word_id)!
    return { ...node, x: p.x, y: p.y, role: p.role, w: p.w, h: p.h }
  })
  const edgeOut = edges.map(e => {
    const a = pos.get(e.a_word_id)!, b = pos.get(e.b_word_id)!
    const meta = REL[e.relation] || REL.related
    return { x1: a.x, y1: a.y, x2: b.x, y2: b.y, mx: (a.x + b.x) / 2, my: (a.y + b.y) / 2,
      rel: e.relation, color: meta.c, bg: meta.bg, fg: meta.fg, label: meta.label }
  })
  return { nodes, edges: edgeOut }
})

function edgeStyle(e: { x1: number; y1: number; x2: number; y2: number; color: string }) {
  const dx = e.x2 - e.x1, dy = e.y2 - e.y1
  const len = Math.sqrt(dx * dx + dy * dy)
  const ang = Math.atan2(dy, dx) * 180 / Math.PI
  return `left:${e.x1}rpx; top:${e.y1 - 2}rpx; width:${len}rpx; transform:rotate(${ang}deg); transform-origin:0 50%; background:${e.color};`
}
function openNode(n: WrongRelNode) { picked.value = n }
</script>

<style scoped>
.wrn { background: #fff; border-radius: 20rpx; padding: 22rpx; margin-top: 20rpx; }
.wrn-head { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 8rpx; }
.wrn-title { display: flex; align-items: center; gap: 8rpx; font-size: 30rpx; font-weight: 800; color: var(--c-ink); }
.wrn-sub { font-size: 22rpx; color: #9aa3b0; }
.wrn-tip { text-align: center; color: #9aa3b0; font-size: 26rpx; padding: 60rpx 0; }
.wrn-canvas { position: relative; width: 690rpx; }
.wrn-edge { position: absolute; height: 4rpx; border-radius: 2rpx; }
.wrn-edge.dash { opacity: .7; }
.wrn-elabel { position: absolute; width: 60rpx; height: 30rpx; line-height: 30rpx; text-align: center; font-size: 20rpx; font-weight: 500; border-radius: 8rpx; }
.wrn-node { position: absolute; box-sizing: border-box; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 10rpx 8rpx; background: #E6F1FB; border: 2rpx solid #85B7EB; border-radius: 16rpx; }
.wrn-node.answer { height: 96rpx; background: #E1F5EE; border-color: #1D9E75; border-width: 3rpx; border-radius: 48rpx; }
.wrn-node.error { background: #FCEBEB; border-color: #E24B4A; }
.wrn-node.peer { height: 78rpx; }
.wrn-badge { font-size: 18rpx; font-weight: 500; color: #fff; padding: 0 10rpx; border-radius: 10rpx; margin-bottom: 2rpx; }
.wrn-badge.ans { background: #1D9E75; }
.wrn-badge.err { background: #E24B4A; }
.wrn-word { font-size: 26rpx; font-weight: 600; color: #0C447C; }
.wrn-node.answer .wrn-word { font-size: 30rpx; color: #0F6E56; }
.wrn-node.error .wrn-word { color: #A32D2D; }
.wrn-zh { font-size: 20rpx; color: #4A6785; margin-top: 2rpx; }
.wrn-node.answer .wrn-zh { color: #0F6E56; }
.wrn-folded { display: block; text-align: center; font-size: 22rpx; color: #9aa3b0; margin-top: 8rpx; }
.wrn-foot { display: flex; align-items: center; justify-content: space-between; margin-top: 14rpx; padding-top: 12rpx; border-top: 1rpx solid #EEF2F7; }
.wrn-legend { display: flex; flex-wrap: wrap; gap: 8rpx 16rpx; }
.wrn-lg { display: flex; align-items: center; gap: 6rpx; font-size: 22rpx; color: #6b7178; }
.wrn-ln { width: 24rpx; height: 4rpx; border-radius: 2rpx; }
.wrn-ln.dash { opacity: .6; }
.wrn-toggle { display: flex; align-items: center; gap: 8rpx; font-size: 22rpx; color: #6b7178; }
.wrn-sw { width: 44rpx; height: 24rpx; border-radius: 12rpx; background: #D3D1C7; position: relative; transition: background .2s; }
.wrn-sw::after { content: ''; position: absolute; top: 3rpx; left: 3rpx; width: 18rpx; height: 18rpx; border-radius: 50%; background: #fff; transition: left .2s; }
.wrn-sw.on { background: var(--c-primary); }
.wrn-sw.on::after { left: 23rpx; }
</style>
