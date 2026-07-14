<template>
  <view class="page">
    <view class="hd">
      <text class="hd-title">作业精讲 · 阅读理解</text>
      <text class="hd-sub">来自你上传作业里的阅读理解,按卷复习:读短文、看题、对答案。</text>
    </view>

    <view v-if="loading" class="tip">加载中…</view>
    <view v-else-if="!batches.length" class="tip">还没有阅读理解——上传含阅读理解的作业即可在此复习。</view>

    <!-- 批次列表 -->
    <template v-else>
      <view v-for="b in batches" :key="b.paper_id" class="card batch" @tap="openBatch(b)">
        <view class="batch-main">
          <text class="batch-title">{{ b.title }}</text>
          <text class="batch-sub">{{ b.date }} · {{ b.count }} 题</text>
        </view>
        <text class="batch-arrow">{{ openId === b.paper_id ? '▾' : '›' }}</text>
      </view>
      <!-- 展开:该卷的短文 + 小题 -->
      <view v-if="openId" class="wrap">
        <view v-if="itemsLoading" class="tip">加载中…</view>
        <view v-else-if="!blocks.length" class="tip">该卷没有阅读理解内容</view>
        <template v-else>
          <view v-for="(bk, bi) in blocks" :key="bi" class="block">
            <view v-if="bk.passage" class="card passage" @tap="toggle(bi)">
              <view class="passage-head">
                <text class="passage-title">短文{{ bk.block_label }}</text>
                <text class="passage-toggle">{{ collapsed[bi] ? '展开 ▾' : '收起 ▴' }}</text>
              </view>
              <text v-if="!collapsed[bi]" class="passage-text">{{ bk.passage }}</text>
            </view>
            <view v-for="(q, qi) in bk.questions" :key="qi" class="card q-card" :class="{ wrong: q.is_wrong }">
              <view class="q-head">
                <text class="q-no">{{ q.no ? `第 ${q.no} 题` : '题目' }}</text>
                <text class="q-type">{{ q.type || '题目' }}</text>
                <text v-if="q.is_wrong" class="q-flag">错</text>
              </view>
              <text class="q-stem">{{ q.stem || '（题干为空）' }}</text>
              <view class="q-ans">
                <text class="ans-line">你的答案：{{ q.student_answer || '（未识别）' }}</text>
                <text class="ans-line">正确答案：{{ q.correct_answer || '（未提供）' }}</text>
              </view>
              <text v-if="q.explanation" class="q-exp">{{ q.explanation }}</text>
            </view>
          </view>
        </template>
      </view>
    </template>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { rdHwBatches, rdHwPassages, type IntensiveBatch, type ReadingBlock } from '@/api/curriculum'

const batches = ref<IntensiveBatch[]>([])
const loading = ref(true)
const openId = ref('')
const blocks = ref<ReadingBlock[]>([])
const itemsLoading = ref(false)
const collapsed = ref<Record<number, boolean>>({})

function toggle(i: number) { collapsed.value = { ...collapsed.value, [i]: !collapsed.value[i] } }

async function openBatch(b: IntensiveBatch) {
  if (openId.value === b.paper_id) { openId.value = ''; return }   // 再点收起
  openId.value = b.paper_id
  itemsLoading.value = true
  blocks.value = []
  collapsed.value = {}
  try {
    blocks.value = (await rdHwPassages(b.paper_id)).blocks
  } catch (e: any) { uni.showToast({ title: e?.message || '加载失败', icon: 'none' }) }
  finally { itemsLoading.value = false }
}

onLoad(async () => {
  try { batches.value = (await rdHwBatches()).batches } catch { /* ignore */ }
  finally { loading.value = false }
})
</script>

<style scoped>
.page { min-height: 100vh; background: var(--c-bg, #f5f7fa); padding: 24rpx; box-sizing: border-box; }
.hd { padding: 8rpx 4rpx 20rpx; }
.hd-title { font-size: 40rpx; font-weight: 800; color: var(--c-ink); display: block; }
.hd-sub { font-size: 24rpx; color: var(--c-text-hint); margin-top: 8rpx; display: block; line-height: 1.5; }
.tip { text-align: center; color: var(--c-text-hint); padding: 60rpx 0; }
.card { background: #fff; border-radius: 20rpx; padding: 24rpx; margin-bottom: 16rpx; }
.batch { display: flex; align-items: center; }
.batch-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6rpx; }
.batch-title { font-size: 30rpx; font-weight: 700; color: var(--c-ink); }
.batch-sub { font-size: 23rpx; color: var(--c-text-hint); }
.batch-arrow { font-size: 30rpx; color: var(--c-primary); }
.wrap { margin-top: 6rpx; }
.block { margin-bottom: 8rpx; }
.passage { background: var(--c-primary-faint); }
.passage-head { display: flex; align-items: center; justify-content: space-between; }
.passage-title { font-size: 26rpx; font-weight: 700; color: var(--c-primary-deep, var(--c-primary)); }
.passage-toggle { font-size: 22rpx; color: var(--c-primary); }
.passage-text { display: block; font-size: 26rpx; color: var(--c-text-body, var(--c-ink)); line-height: 1.7; margin-top: 14rpx; white-space: pre-wrap; }
.q-card.wrong { border: 2rpx solid #f5c2c7; }
.q-head { display: flex; align-items: center; gap: 12rpx; margin-bottom: 10rpx; }
.q-no { font-size: 24rpx; font-weight: 700; color: var(--c-ink); }
.q-type { font-size: 21rpx; color: var(--c-primary); background: var(--c-primary-faint); border-radius: 8rpx; padding: 2rpx 12rpx; }
.q-flag { font-size: 20rpx; color: #fff; background: #e5484d; border-radius: 6rpx; padding: 2rpx 10rpx; }
.q-stem { display: block; font-size: 26rpx; line-height: 1.6; color: var(--c-ink); }
.q-ans { margin-top: 12rpx; display: flex; flex-direction: column; gap: 4rpx; }
.ans-line { font-size: 24rpx; color: var(--c-text-sub); }
.q-exp { display: block; font-size: 24rpx; color: var(--c-text-sub); line-height: 1.6; margin-top: 10rpx; background: var(--c-bg-soft, #f6f8fb); border-radius: 10rpx; padding: 12rpx 14rpx; }
</style>
