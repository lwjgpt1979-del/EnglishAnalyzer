<template>
  <view class="page">
    <view v-if="loading" class="empty">加载中…</view>

    <template v-else-if="paper">
      <view class="head card">
        <text class="title">{{ paper.title || '未命名试卷' }}</text>
        <view class="status" :class="statusClass">
          <text>{{ statusText }}</text>
        </view>
        <text class="meta">{{ paper.source_image_urls.length }} 张图片 · {{ paper.question_count }} 道题</text>
      </view>

      <!-- 处理中 -->
      <view v-if="isProcessing" class="card processing">
        <text class="proc-text">正在识别并拆题，请稍候…</text>
        <text class="proc-sub">通常 10~30 秒，可停留在此页等待</text>
      </view>

      <!-- 失败 -->
      <view v-else-if="paper.ocr_status === 'failed'" class="card failed">
        <text class="fail-text">识别失败</text>
        <text class="fail-sub">可能是图片不清晰或顺序问题，请重新拍摄上传</text>
        <button class="btn-secondary" @tap="goUpload">重新上传</button>
      </view>

      <!-- 完成：知识点归集 + 题目列表 -->
      <template v-else-if="paper.ocr_status === 'completed'">
        <view v-if="!paper.questions.length" class="card empty-q">
          <text>未识别到题目，请重试或换更清晰的图片</text>
          <button class="btn-secondary" @tap="goUpload">重新上传</button>
        </view>

        <!-- 知识点归集卡（错题按知识点聚合，薄弱红标）-->
        <view v-if="kpItems.length" class="card kp-card">
          <text class="kp-title">本卷知识点归集</text>
          <view v-for="k in kpItems" :key="k.kp_id" class="kp-row">
            <text class="kp-name" :class="{ weak: k.weak }">{{ k.kp_name }}</text>
            <text class="kp-cnt">错 {{ k.wrong }}/{{ k.total }}</text>
            <text v-if="k.weak" class="kp-weak">薄弱</text>
          </view>
        </view>

        <!-- 全部/错题 筛选 -->
        <view v-if="paper.questions.length" class="filter-row">
          <text class="fbtn" :class="{ on: !onlyWrong }" @tap="onlyWrong = false">全部 {{ paper.questions.length }}</text>
          <text class="fbtn" :class="{ on: onlyWrong }" @tap="onlyWrong = true">错题 {{ wrongCount }}</text>
        </view>

        <view
          v-for="(q, idx) in shownQuestions" :key="q.id"
          class="card q-card" :class="{ wrong: q.is_wrong }"
        >
          <view class="q-head">
            <text class="q-no">{{ q.question_no ? `第 ${q.question_no} 题` : `第 ${idx + 1} 题` }}</text>
            <text class="q-type">{{ q.question_type || '题目' }}</text>
            <text v-if="q.is_wrong" class="q-flag">✗ 错</text>
          </view>
          <text class="q-stem">{{ q.stem || '（题干识别为空）' }}</text>
          <view class="q-ans">
            <text class="ans-line">你的答案：{{ q.student_answer || '（未识别）' }}</text>
            <text class="ans-line">正确答案：{{ q.correct_answer || '（未提供）' }}</text>
          </view>
          <text v-if="q.explanation" class="q-exp">{{ q.explanation }}</text>
          <button v-if="q.is_wrong" class="btn-similar" :disabled="similarLoading" @tap="practiceSimilar(q.id)">练同类仿真题</button>
        </view>
      </template>
    </template>

    <!-- 练同类结果弹层 -->
    <view v-if="similarOpen" class="modal" @tap.self="similarOpen = false">
      <view class="modal-card">
        <text class="modal-title">同类练习 · {{ similarKp }}</text>
        <scroll-view scroll-y class="modal-body">
          <view v-for="(sq, i) in similarList" :key="sq.id" class="sq">
            <text class="sq-stem">{{ i + 1 }}. {{ sq.stem }}</text>
            <view v-if="sq.options" class="sq-opts">
              <text v-for="(v, kk) in sq.options" :key="kk" class="sq-opt">{{ kk }}. {{ v }}</text>
            </view>
          </view>
          <text v-if="!similarList.length" class="muted">未生成题目</text>
        </scroll-view>
        <button class="btn-secondary" @tap="similarOpen = false">关闭</button>
      </view>
    </view>

    <view v-else class="empty">试卷不存在或无权访问</view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad, onUnload } from '@dcloudio/uni-app'
import { getUserPaper, getPaperKpSummary, practiceForQuestion, type PaperKpItem, type SimilarQuestion } from '@/api/userPapers'
import type { UserPaperDetailOut } from '@/types/api'

const paper = ref<UserPaperDetailOut | null>(null)
const loading = ref(true)
const paperId = ref('')
let timer: ReturnType<typeof setTimeout> | null = null

// M4 深化：知识点归集 + 错题筛选 + 练同类
const kpItems = ref<PaperKpItem[]>([])
const onlyWrong = ref(false)
const wrongCount = computed(() => (paper.value?.questions || []).filter(q => q.is_wrong).length)
const shownQuestions = computed(() => {
  const qs = paper.value?.questions || []
  return onlyWrong.value ? qs.filter(q => q.is_wrong) : qs
})
const similarOpen = ref(false)
const similarLoading = ref(false)
const similarKp = ref('')
const similarList = ref<SimilarQuestion[]>([])

async function loadKpSummary() {
  try { kpItems.value = (await getPaperKpSummary(paperId.value)).items } catch { /* ignore */ }
}
async function practiceSimilar(qid: string) {
  if (similarLoading.value) return
  similarLoading.value = true
  try {
    const r = await practiceForQuestion(qid)
    similarKp.value = r.knowledge_point; similarList.value = r.questions; similarOpen.value = true
  } catch (e: any) {
    uni.showToast({ title: e?.message || '生成失败', icon: 'none' })
  } finally { similarLoading.value = false }
}

const isProcessing = computed(
  () => paper.value?.ocr_status === 'pending' || paper.value?.ocr_status === 'processing',
)

const statusText = computed(() => {
  const map: Record<string, string> = {
    pending: '排队中',
    processing: '识别中',
    completed: '已完成',
    failed: '失败',
  }
  return map[paper.value?.ocr_status || ''] || '未知'
})

const statusClass = computed(() => {
  const s = paper.value?.ocr_status
  if (s === 'completed') return 'ok'
  if (s === 'failed') return 'bad'
  return 'wait'
})

async function load() {
  try {
    paper.value = await getUserPaper(paperId.value)
  } catch (e: any) {
    uni.showToast({ title: e?.message || '加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
  // 仍在处理中 → 轮询
  if (isProcessing.value) {
    timer = setTimeout(load, 2500)
  } else if (paper.value?.ocr_status === 'completed') {
    loadKpSummary()
  }
}

onLoad((q: any) => {
  paperId.value = q.id || ''
  if (!paperId.value) {
    uni.showToast({ title: '缺少试卷 id', icon: 'none' })
    setTimeout(() => uni.navigateBack(), 800)
    return
  }
  load()
})

onUnload(() => {
  if (timer) clearTimeout(timer)
})

function goUpload() {
  uni.redirectTo({ url: '/pages/user-papers/upload' })
}
</script>

<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.empty { text-align: center; padding: 80rpx 0; color: var(--c-text-hint); }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: 28rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); margin-bottom: 20rpx; }
.head { display: flex; flex-direction: column; gap: 12rpx; }
.title { font-size: 32rpx; font-weight: 800; color: var(--c-ink); }
.status { align-self: flex-start; font-size: 24rpx; padding: 4rpx 16rpx; border-radius: 20rpx; }
.status.ok { background: #eafaf1; color: #2ecc71; }
.status.bad { background: var(--c-danger-bg); color: var(--c-danger); }
.status.wait { background: var(--c-primary-faint); color: #b9892e; }
.meta { font-size: 24rpx; color: var(--c-text-second); }
.processing { display: flex; flex-direction: column; gap: 10rpx; align-items: center; padding: 48rpx; }
.proc-text { font-size: 28rpx; font-weight: 700; color: var(--c-ink); }
.proc-sub { font-size: 24rpx; color: var(--c-text-hint); }
.failed, .empty-q { display: flex; flex-direction: column; gap: 16rpx; align-items: center; padding: 48rpx; }
.fail-text { font-size: 30rpx; font-weight: 700; color: var(--c-danger); }
.fail-sub { font-size: 24rpx; color: var(--c-text-second); text-align: center; }
.btn-secondary { background: var(--c-bg-soft); color: var(--c-text-body); border: 2rpx solid var(--c-border); border-radius: var(--r-btn); padding: 16rpx 40rpx; font-size: 28rpx; }
.q-card { border-left: 6rpx solid transparent; }
.q-card.wrong { border-left-color: var(--c-danger); }
.q-head { display: flex; align-items: center; gap: 16rpx; margin-bottom: 12rpx; }
.q-no { font-size: 26rpx; font-weight: 700; color: var(--c-ink); }
.q-type { font-size: 22rpx; color: var(--c-text-hint); }
.q-flag { margin-left: auto; font-size: 24rpx; font-weight: 700; color: var(--c-danger); }
.q-stem { display: block; font-size: 28rpx; color: var(--c-text-body); line-height: 1.6; margin-bottom: 16rpx; white-space: pre-wrap; }
.q-ans { display: flex; flex-direction: column; gap: 6rpx; background: var(--c-bg-soft); border-radius: var(--r-md); padding: 16rpx; }
.ans-line { font-size: 24rpx; color: var(--c-text-body); }
.q-exp { display: block; font-size: 24rpx; color: var(--c-text-second); line-height: 1.6; margin-top: 12rpx; }
.kp-card { display: flex; flex-direction: column; gap: 10rpx; }
.kp-title { font-size: 28rpx; font-weight: 800; color: var(--c-ink); margin-bottom: 6rpx; }
.kp-row { display: flex; align-items: center; gap: 12rpx; }
.kp-name { flex: 1; font-size: 26rpx; color: var(--c-text-body); }
.kp-name.weak { color: var(--c-danger); font-weight: 700; }
.kp-cnt { font-size: 24rpx; color: var(--c-text-hint); }
.kp-weak { font-size: 20rpx; color: #fff; background: var(--c-danger); border-radius: 8rpx; padding: 2rpx 10rpx; }
.filter-row { display: flex; gap: 16rpx; margin-bottom: 16rpx; }
.fbtn { font-size: 26rpx; color: var(--c-text-second); padding: 8rpx 24rpx; border-radius: 999rpx; background: var(--c-bg-soft); }
.fbtn.on { background: var(--c-primary); color: var(--c-on-primary); font-weight: 700; }
.btn-similar { margin-top: 16rpx; background: var(--c-primary-faint); color: var(--c-primary-deep); border-radius: var(--r-btn); font-size: 26rpx; padding: 12rpx 0; }
.modal { position: fixed; inset: 0; background: rgba(0,0,0,.45); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-card { width: 86%; max-height: 76vh; background: var(--c-bg-card); border-radius: var(--r-lg); padding: 28rpx; display: flex; flex-direction: column; gap: 16rpx; }
.modal-title { font-size: 30rpx; font-weight: 800; color: var(--c-ink); }
.modal-body { max-height: 56vh; }
.sq { margin-bottom: 20rpx; }
.sq-stem { display: block; font-size: 27rpx; color: var(--c-text-body); line-height: 1.6; }
.sq-opts { display: flex; flex-direction: column; gap: 4rpx; margin-top: 8rpx; }
.sq-opt { font-size: 25rpx; color: var(--c-text-second); }
.muted { color: var(--c-text-hint); font-size: 24rpx; }
</style>
