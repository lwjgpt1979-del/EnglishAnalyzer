<!-- src/pages/user-papers/list.vue —— 我的作业(C-a:状态Tab + 大进度环 + 四模块小点) -->
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

    <!-- 状态 Tab -->
    <view v-if="papers.length" class="tabs">
      <text v-for="t in TABS" :key="t.key" class="tab" :class="{ on: tab === t.key }" @tap="tab = t.key">{{ t.label }}</text>
    </view>

    <view v-if="loading && !papers.length" class="center-tip">加载中…</view>
    <view v-else-if="!papers.length" class="center-tip">还没有上传作业,点上方按钮试试</view>
    <view v-else-if="!filtered.length" class="center-tip">该状态下暂无作业</view>

    <!-- 作业卡:大进度环 + 四模块小点 -->
    <view v-else>
      <view v-for="p in filtered" :key="p.paper_id" class="paper-card" @tap="goDetail(p.paper_id)">
        <view class="pc-ring" :style="ringStyle(p)"><text class="pc-ring-n" :class="{ done: p.status === 'done' }">{{ ringLabel(p) }}</text></view>
        <view class="pc-body">
          <text class="pc-title">{{ p.title }}</text>
          <text class="pc-sub">{{ p.date }} · {{ statusText(p) }}</text>
          <view class="pc-mods">
            <view v-for="m in MODS" :key="m.key" class="pc-mod">
              <view class="pc-dot" :class="dotCls(p, m.key)"></view><text class="pc-mod-t">{{ m.label }}</text>
            </view>
          </view>
        </view>
        <text class="pc-act" :class="{ done: p.status === 'done' }">{{ actLabel(p) }}</text>
      </view>
    </view>
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
const TABS = [
  { key: 'all', label: '全部' }, { key: 'doing', label: '学习中' }, { key: 'done', label: '已完成' },
] as const

const auth = useAuthStore()
const papers = ref<HomeworkPaper[]>([])
const loading = ref(false)
const tab = ref<'all' | 'doing' | 'done'>('all')

const filtered = computed(() =>
  tab.value === 'all' ? papers.value : papers.value.filter(p => p.status === tab.value))

onShow(async () => {
  if (!auth.isLoggedIn()) await auth.login()
  await load()
})

async function load() {
  if (loading.value) return
  loading.value = true
  try {
    papers.value = (await getHomeworkProgress()).papers
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'none' })
  } finally {
    loading.value = false
  }
}

// 综合进度环(SVG 背景数据 URI,mp-weixin 安全;已完成=绿,否则蓝)
function ringStyle(p: HomeworkPaper) {
  const C = 94.2
  const done = p.status === 'done'
  const arc = Math.max(0, Math.min(100, p.overall_pct)) / 100 * C
  const stroke = done ? '%232fa98a' : '%233d8bf5'
  const track = done ? '%232fa98a' : '%23e6eaf0'
  const svg = `%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 36 36'%3E`
    + `%3Ccircle cx='18' cy='18' r='15' fill='none' stroke='${track}' stroke-width='4'/%3E`
    + (done ? '' : `%3Ccircle cx='18' cy='18' r='15' fill='none' stroke='${stroke}' stroke-width='4' stroke-linecap='round' stroke-dasharray='${arc.toFixed(1)} ${(C - arc).toFixed(1)}' transform='rotate(-90 18 18)'/%3E`)
    + `%3C/svg%3E`
  return { backgroundImage: `url("data:image/svg+xml,${svg}")` }
}
function ringLabel(p: HomeworkPaper) { return `${p.overall_pct}%` }

// 四模块小点:满(绿)/ 进行中(蓝)/ 未学(灰)/ 未涉及(浅灰)
function dotCls(p: HomeworkPaper, k: ModKey) {
  const m = p.modules[k]
  if (!m || m.total === 0) return 'd-none'
  if (m.studied >= m.total) return 'd-done'
  if (m.studied > 0) return 'd-doing'
  return 'd-todo'
}

function statusText(p: HomeworkPaper) {
  if (p.ocr_status && p.ocr_status !== 'completed') {
    return { pending: '识别排队中', processing: '识别中', failed: '识别失败' }[p.ocr_status] || '处理中'
  }
  return { done: '已完成', doing: '学习中', todo: '未开始' }[p.status]
}
function actLabel(p: HomeworkPaper) { return p.status === 'done' ? '复习 ›' : (p.status === 'doing' ? '继续 ›' : '开始 ›') }

function goUpload() { uni.navigateTo({ url: '/pages/user-papers/upload' }) }
function goDetail(id: string) { uni.navigateTo({ url: `/pages/user-papers/detail?id=${id}` }) }
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
/* 状态 Tab */
.tabs { display: flex; gap: 14rpx; margin: 4rpx 2rpx 18rpx; }
.tab { font-size: 25rpx; padding: 8rpx 26rpx; border-radius: 999rpx; background: #fff; border: 2rpx solid #e0e5ec; color: var(--c-text-sub, #5f6b7a); }
.tab.on { background: var(--c-primary, #3d8bf5); color: #fff; border-color: var(--c-primary, #3d8bf5); }
/* 作业卡 */
.paper-card { display: flex; align-items: center; gap: 26rpx; background: #fff; border-radius: 20rpx; padding: 28rpx 26rpx; margin-bottom: 16rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.pc-ring { width: 104rpx; height: 104rpx; flex-shrink: 0; background-size: contain; background-repeat: no-repeat; background-position: center; display: flex; align-items: center; justify-content: center; }
.pc-ring-n { font-size: 27rpx; font-weight: 800; color: var(--c-primary, #3d8bf5); }
.pc-ring-n.done { color: #2fa98a; }
.pc-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6rpx; }
.pc-title { font-size: 30rpx; font-weight: 700; color: var(--c-ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pc-sub { font-size: 23rpx; color: var(--c-text-hint); }
.pc-mods { display: flex; gap: 20rpx; margin-top: 8rpx; }
.pc-mod { display: flex; align-items: center; gap: 7rpx; }
.pc-dot { width: 14rpx; height: 14rpx; border-radius: 50%; }
.d-done { background: #2fa98a; } .d-doing { background: #3d8bf5; } .d-todo { background: #d3d8e0; } .d-none { background: #eef1f5; }
.pc-mod-t { font-size: 22rpx; color: var(--c-text-sub, #8a93a3); }
.pc-act { font-size: 24rpx; color: var(--c-primary, #3d8bf5); flex-shrink: 0; }
.pc-act.done { color: #2fa98a; }
</style>
