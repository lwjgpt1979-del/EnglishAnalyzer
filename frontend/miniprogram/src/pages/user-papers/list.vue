<!-- src/pages/user-papers/list.vue —— 作业(合并:上传 + 按作业时间线 + 按模块宫格) -->
<template>
  <view class="list-page">
    <!-- 顶部上传入口 -->
    <view class="upload-entry" @tap="goUpload">
      <view class="ue-icon"><view class="ic ic-plus" style="width:40rpx;height:40rpx" /></view>
      <view class="ue-text">
        <text class="ue-title">拍整份作业</text>
        <text class="ue-sub">1~9 张图片，自动识别并拆题</text>
      </view>
      <text class="ue-arrow">›</text>
    </view>

    <!-- 视图切换:按作业 / 按模块 -->
    <view v-if="papers.length" class="seg">
      <text class="seg-i" :class="{ on: view === 'task' }" @tap="view = 'task'">按作业</text>
      <text class="seg-i" :class="{ on: view === 'module' }" @tap="view = 'module'">按模块</text>
    </view>

    <view v-if="loading && !papers.length" class="center-tip">加载中…</view>
    <view v-else-if="!papers.length" class="center-tip">还没有上传作业,点上方按钮试试</view>

    <!-- ===== 按作业:状态 tab + 时间线(本周/一周前/一月前)===== -->
    <template v-else-if="view === 'task'">
      <view class="tabs">
        <text v-for="t in TABS" :key="t.key" class="tab" :class="{ on: tab === t.key }" @tap="tab = t.key">{{ t.label }} {{ statusCount(t.key) }}</text>
      </view>
      <view v-if="!filtered.length" class="center-tip">该状态下暂无作业</view>
      <block v-for="b in BUCKETS" :key="b.v">
        <template v-if="bucketPapers(b.v).length">
          <view class="tsec" :class="b.v">{{ b.label }}</view>
          <view class="tl">
            <view v-for="p in bucketPapers(b.v)" :key="p.paper_id" class="node">
              <view class="ndot" :class="p.status" />
              <view class="paper-card" @tap="goDetail(p.paper_id)">
                <view class="pc-ring" :style="ringStyle(p)"><text class="pc-ring-n" :class="{ done: p.status === 'done' }">{{ p.overall_pct }}%</text></view>
                <view class="pc-body">
                  <text class="pc-title">{{ p.title }}</text>
                  <text class="pc-sub">{{ p.date }} · {{ statusText(p) }}</text>
                  <view class="pc-mods">
                    <text v-for="m in visibleMods(p)" :key="m.key"
                      class="pc-chip" :class="'kc-' + m.key">{{ m.label }}{{ modDisp(p, m.key) }}</text>
                  </view>
                </view>
                <text class="pc-act" :class="{ done: p.status === 'done' }">{{ actLabel(p) }}</text>
              </view>
            </view>
          </view>
        </template>
      </block>
    </template>

    <!-- ===== 按模块:2×2 宫格(进度环 + 份数 + 待学徽章)===== -->
    <template v-else>
      <view class="grid">
        <view v-for="m in moduleAgg" :key="m.key" class="gc" @tap="goModule(m.key)">
          <view class="gring" :style="ringStyle2(m.pct, m.color)"><text class="gring-n" :style="{ color: m.color }">{{ m.pct }}%</text></view>
          <text class="gt">{{ m.title }}</text>
          <text class="gn">{{ m.total }} {{ m.unit }} · {{ m.papers }} 份</text>
          <text v-if="m.remaining > 0" class="gbadge">{{ m.verb }} {{ m.remaining }}</text>
          <text v-else class="gdone">✓ 已学完</text>
        </view>
      </view>
    </template>
  </view>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { getHomeworkProgress, type HomeworkPaper } from '@/api/userPapers'
import { useAuthStore } from '@/stores/auth'

type ModKey = 'word' | 'grammar' | 'sentence' | 'reading'
const MODS: { key: ModKey; label: string }[] = [
  { key: 'word', label: '词' }, { key: 'grammar', label: '语法' },
  { key: 'sentence', label: '句' }, { key: 'reading', label: '阅读' },
]
// 模块元信息(标题/单位/待学动词/色/跳转页)
const MOD_META: Record<ModKey, { title: string; unit: string; verb: string; color: string; page: string }> = {
  word: { title: '单词', unit: '词', verb: '待背', color: '#c77d2e', page: 'words' },
  grammar: { title: '语法精讲', unit: '点', verb: '待学', color: '#7a5cd0', page: 'grammar' },
  sentence: { title: '长难句', unit: '句', verb: '待拆', color: '#3d8bf5', page: 'sentence' },
  reading: { title: '阅读理解', unit: '篇', verb: '待读', color: '#2fa98a', page: 'reading' },
}
const TABS = [
  { key: 'all', label: '全部' }, { key: 'todo', label: '未学习' },
  { key: 'doing', label: '学习中' }, { key: 'done', label: '已完成' },
] as const
const BUCKETS = [
  { v: 'week', label: '本周' }, { v: 'mid', label: '一周前' }, { v: 'old', label: '一月前' },
] as const

const auth = useAuthStore()
const papers = ref<HomeworkPaper[]>([])
const loading = ref(false)
const view = ref<'task' | 'module'>('task')
const tab = ref<'all' | 'todo' | 'doing' | 'done'>('all')

const filtered = computed(() =>
  tab.value === 'all' ? papers.value : papers.value.filter(p => p.status === tab.value))
function statusCount(k: string) {
  return k === 'all' ? papers.value.length : papers.value.filter(p => p.status === k).length
}
// 时间桶:本周≤7天 / 一周前8-30天 / 一月前>30天(按上传日期)
function bucketOf(dateStr: string): string {
  const d = new Date((dateStr || '').replace(/-/g, '/'))
  const days = Math.floor((Date.now() - d.getTime()) / 86400000)
  return isNaN(days) ? 'old' : (days <= 7 ? 'week' : days <= 30 ? 'mid' : 'old')
}
function bucketPapers(b: string) { return filtered.value.filter(p => bucketOf(p.date) === b) }
function visibleMods(p: HomeworkPaper) { return MODS.filter(m => p.modules[m.key] && p.modules[m.key].total > 0) }
function modDisp(p: HomeworkPaper, k: ModKey) {
  const m = p.modules[k]
  return m.studied >= m.total ? '✓' : String(m.total)
}

// 按模块聚合(跨所有作业)
const moduleAgg = computed(() => MODS.map(m => {
  let studied = 0, total = 0, papersN = 0
  for (const p of papers.value) {
    const mm = p.modules[m.key]
    if (mm && mm.total > 0) { studied += mm.studied; total += mm.total; papersN++ }
  }
  const meta = MOD_META[m.key]
  return {
    key: m.key, title: meta.title, unit: meta.unit, verb: meta.verb, color: meta.color,
    total, studied, papers: papersN, remaining: total - studied,
    pct: total ? Math.round(studied / total * 100) : 0,
  }
}))

onShow(async () => {
  if (!auth.isLoggedIn()) await auth.login()
  await load()
})
async function load() {
  if (loading.value) return
  loading.value = true
  try { papers.value = (await getHomeworkProgress()).papers }
  catch (e) { uni.showToast({ title: (e as Error).message, icon: 'none' }) }
  finally { loading.value = false }
}

// 作业综合进度环(蓝/绿)
function ringStyle(p: HomeworkPaper) {
  return ringStyle2(p.overall_pct, p.status === 'done' ? '#2fa98a' : '#3d8bf5', p.status === 'done')
}
// 通用进度环(pct + 色);done=整圈填色
function ringStyle2(pct: number, hex: string, done = false) {
  const C = 94.2
  const arc = Math.max(0, Math.min(100, pct)) / 100 * C
  const col = '%23' + hex.replace('#', '')
  const track = done ? col : '%23e6eaf0'
  const svg = `%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 36 36'%3E`
    + `%3Ccircle cx='18' cy='18' r='15' fill='none' stroke='${track}' stroke-width='4'/%3E`
    + (done ? '' : `%3Ccircle cx='18' cy='18' r='15' fill='none' stroke='${col}' stroke-width='4' stroke-linecap='round' stroke-dasharray='${arc.toFixed(1)} ${(C - arc).toFixed(1)}' transform='rotate(-90 18 18)'/%3E`)
    + `%3C/svg%3E`
  return { backgroundImage: `url("data:image/svg+xml,${svg}")` }
}

function statusText(p: HomeworkPaper) {
  if (p.ocr_status && p.ocr_status !== 'completed') {
    return { pending: '识别排队中', processing: '识别中', failed: '识别失败' }[p.ocr_status] || '处理中'
  }
  return { done: '已完成', doing: '学习中', todo: '未学习' }[p.status]
}
function actLabel(p: HomeworkPaper) { return p.status === 'done' ? '复习 ›' : (p.status === 'doing' ? '继续 ›' : '开始 ›') }

function goUpload() { uni.navigateTo({ url: '/pages/user-papers/upload' }) }
function goDetail(id: string) { uni.navigateTo({ url: `/pages/user-papers/detail?id=${id}` }) }
function goModule(k: ModKey) { uni.navigateTo({ url: `/pages/intensive/${MOD_META[k].page}?mode=homework` }) }
</script>

<style scoped>
.list-page { padding: 24rpx; background: var(--c-bg-page, #f4f6fa); min-height: 100vh; }
.center-tip { text-align: center; padding: 120rpx 0; color: var(--c-text-hint); font-size: 28rpx; }
.upload-entry { display: flex; align-items: center; gap: 20rpx; background: var(--c-bg-card, #fff); border-radius: 20rpx; padding: 28rpx; margin-bottom: 20rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.ue-icon { width: 72rpx; height: 72rpx; display: flex; align-items: center; justify-content: center; background: var(--c-primary-soft, #eaf2ff); border-radius: 16rpx; }
.ue-text { flex: 1; display: flex; flex-direction: column; gap: 6rpx; }
.ue-title { font-size: 30rpx; font-weight: 700; color: var(--c-ink); }
.ue-sub { font-size: 24rpx; color: var(--c-text-hint); }
.ue-arrow { font-size: 40rpx; color: var(--c-text-hint); }
/* 视图切换 */
.seg { display: flex; background: #e9eef4; border-radius: 16rpx; padding: 6rpx; margin-bottom: 18rpx; }
.seg-i { flex: 1; text-align: center; font-size: 26rpx; padding: 14rpx 0; border-radius: 12rpx; color: var(--c-text-sub, #5f6b7a); }
.seg-i.on { background: #fff; color: var(--c-primary, #3d8bf5); font-weight: 800; box-shadow: 0 2rpx 6rpx rgba(0,0,0,.06); }
/* 状态 Tab */
.tabs { display: flex; gap: 14rpx; margin: 4rpx 2rpx 16rpx; overflow-x: auto; }
.tab { font-size: 24rpx; padding: 8rpx 22rpx; border-radius: 999rpx; background: #fff; border: 2rpx solid #e0e5ec; color: var(--c-text-sub, #5f6b7a); white-space: nowrap; }
.tab.on { background: var(--c-primary, #3d8bf5); color: #fff; border-color: var(--c-primary, #3d8bf5); }
/* 时间线 */
.tsec { font-size: 26rpx; font-weight: 800; color: var(--c-text-sub, #8a93a3); margin: 12rpx 0 12rpx 8rpx; }
.tsec.old { color: #e0863a; }
.tl { position: relative; padding-left: 40rpx; }
.tl::before { content: ''; position: absolute; left: 12rpx; top: 10rpx; bottom: 10rpx; width: 3rpx; background: #e0e5ec; }
.node { position: relative; margin-bottom: 16rpx; }
.ndot { position: absolute; left: -34rpx; top: 44rpx; width: 22rpx; height: 22rpx; border-radius: 50%; border: 5rpx solid var(--c-bg-page, #f4f6fa); box-sizing: border-box; }
.ndot.todo { background: #b7c0cc; } .ndot.doing { background: #3d8bf5; } .ndot.done { background: #2fa98a; }
/* 作业卡 */
.paper-card { display: flex; align-items: center; gap: 22rpx; background: #fff; border-radius: 20rpx; padding: 24rpx 22rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.pc-ring { width: 100rpx; height: 100rpx; flex-shrink: 0; background-size: contain; background-repeat: no-repeat; background-position: center; display: flex; align-items: center; justify-content: center; }
.pc-ring-n { font-size: 26rpx; font-weight: 800; color: var(--c-primary, #3d8bf5); }
.pc-ring-n.done { color: #2fa98a; }
.pc-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6rpx; }
.pc-title { font-size: 29rpx; font-weight: 700; color: var(--c-ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pc-sub { font-size: 22rpx; color: var(--c-text-hint); }
.pc-mods { display: flex; gap: 10rpx; margin-top: 8rpx; flex-wrap: wrap; }
.pc-chip { font-size: 21rpx; font-weight: 700; padding: 3rpx 14rpx; border-radius: 999rpx; }
.pc-chip.kc-word { color: #c77d2e; background: #fbf4ea; }
.pc-chip.kc-grammar { color: #7a5cd0; background: #f4f0fb; }
.pc-chip.kc-sentence { color: #3d8bf5; background: #eef4fd; }
.pc-chip.kc-reading { color: #2fa98a; background: #eef8f4; }
.pc-act { font-size: 24rpx; color: var(--c-primary, #3d8bf5); flex-shrink: 0; }
.pc-act.done { color: #2fa98a; }
/* 按模块 2×2 宫格 */
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18rpx; }
.gc { background: #fff; border-radius: 20rpx; padding: 30rpx 20rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); display: flex; flex-direction: column; align-items: center; gap: 10rpx; }
.gring { width: 108rpx; height: 108rpx; background-size: contain; background-repeat: no-repeat; background-position: center; display: flex; align-items: center; justify-content: center; }
.gring-n { font-size: 28rpx; font-weight: 900; }
.gt { font-size: 30rpx; font-weight: 800; color: var(--c-ink); }
.gn { font-size: 22rpx; color: var(--c-text-hint); }
.gbadge { font-size: 21rpx; font-weight: 700; color: #d9573f; background: #fbe9e4; padding: 3rpx 16rpx; border-radius: 999rpx; margin-top: 4rpx; }
.gdone { font-size: 21rpx; font-weight: 700; color: #2fa98a; background: #e9f6f1; padding: 3rpx 16rpx; border-radius: 999rpx; margin-top: 4rpx; }
</style>
