<template>
  <view class="page">
    <!-- 只读预览模式 -->
    <view v-if="readonly && detail">
      <view class="paper-header">
        <text class="paper-title">{{ detail.title }}</text>
        <view class="meta">
          <text v-if="detail.grade">{{ detail.grade }} · {{ detail.semester }}学期</text>
          <text>共 {{ detail.questions.length }} 题</text>
        </view>
        <text v-if="detail.description" class="desc">{{ detail.description }}</text>
      </view>
      <view v-for="(q, i) in detail.questions" :key="q.id" class="question-card">
        <view class="q-header">
          <text class="q-no">{{ i + 1 }}.</text>
          <text class="q-type-tag">{{ q.question_type }}</text>
          <text class="q-diff">难度 {{ q.difficulty }}</text>
        </view>
        <text class="q-stem">{{ q.stem }}</text>
        <view v-if="q.options" class="options">
          <view v-for="(opt, oi) in q.options" :key="oi" class="option">
            <text>{{ String.fromCharCode(65 + oi) }}. {{ opt }}</text>
          </view>
        </view>
      </view>
      <view v-if="detail.questions.length === 0" class="tip">该试卷暂无题目</view>
    </view>

    <!-- 组卷编辑模式 -->
    <view v-else>
      <view class="section">
        <text class="section-title">试卷信息</text>
        <input v-model="form.title" class="input" placeholder="试卷名称（必填）" />
        <picker mode="selector" :range="gradeOptions" @change="(e: any) => form.grade = gradeOptions[e.detail.value]">
          <view class="picker-row">
            <text class="picker-label">年级</text>
            <text class="picker-value">{{ form.grade || '请选择' }}</text>
          </view>
        </picker>
        <picker mode="selector" :range="semesterOptions" @change="(e: any) => form.semester = semesterOptions[e.detail.value]">
          <view class="picker-row">
            <text class="picker-label">学期</text>
            <text class="picker-value">{{ form.semester || '请选择' }}</text>
          </view>
        </picker>
        <textarea v-model="form.description" class="textarea" placeholder="备注说明（可选）" />
      </view>

      <view class="section">
        <view class="section-header">
          <text class="section-title">已选题目（{{ selectedIds.size }} 题）</text>
          <button class="btn-browse" @tap="showBrowser = true">从题库选题</button>
        </view>
        <view v-if="selectedIds.size === 0" class="tip">尚未选题，点击右侧「从题库选题」</view>
        <view v-for="q in selectedQuestions" :key="q.id" class="q-chip">
          <text class="q-stem-short">{{ q.stem.slice(0, 40) }}{{ q.stem.length > 40 ? '…' : '' }}</text>
          <view class="q-remove ic ic-close" @tap="removeQuestion(q.id)" />
        </view>
      </view>

      <button
        class="btn-submit"
        :disabled="!form.title || submitting"
        @tap="onSubmit"
      >
        {{ submitting ? '保存中…' : '保存试卷' }}
      </button>
    </view>

    <!-- 选题浮层 -->
    <view v-if="showBrowser" class="browser-mask" @tap.self="showBrowser = false">
      <view class="browser-panel">
        <view class="browser-header">
          <text class="browser-title">选题库（仿真题）</text>
          <view class="browser-close ic ic-close" @tap="showBrowser = false" />
        </view>
        <view class="browser-filters">
          <picker mode="selector" :range="difficultyOptions" @change="(e: any) => { filterDiff = e.detail.value === 0 ? undefined : e.detail.value; loadBrowser() }">
            <view class="filter-chip">难度: {{ filterDiff || '全部' }}</view>
          </picker>
        </view>
        <scroll-view class="browser-list" scroll-y>
          <view v-if="browserLoading" class="tip">加载中…</view>
          <view v-for="q in browserItems" :key="q.id" class="browser-item" @tap="toggleSelect(q)">
            <view class="browser-item-left">
              <text :class="['check', selectedIds.has(q.id) ? 'checked' : '']">
                {{ selectedIds.has(q.id) ? '✓' : '○' }}
              </text>
            </view>
            <view class="browser-item-content">
              <text class="bi-stem">{{ q.stem.slice(0, 60) }}{{ q.stem.length > 60 ? '…' : '' }}</text>
              <view class="bi-meta">
                <text class="bi-type">{{ q.question_type }}</text>
                <text class="bi-diff">难度{{ q.difficulty }}</text>
              </view>
            </view>
          </view>
          <view v-if="!browserLoading && browserItems.length === 0" class="tip">暂无仿真题</view>
        </scroll-view>
        <view class="browser-footer">
          <text class="sel-count">已选 {{ selectedIds.size }} 题</text>
          <button class="btn-done" @tap="showBrowser = false">完成选题</button>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { listSimQuestions, createClassPaper, getClassPaperDetail } from '@/api/examPapers'
import type { SimQuestionItem, ClassPaperDetailOut } from '@/types/api'

// 路由参数
const pages = getCurrentPages()
const currentPage = pages[pages.length - 1] as any
const classId: string = currentPage.options?.classId || ''
const paperId: string = currentPage.options?.paperId || ''
const readonly = currentPage.options?.readonly === '1'

// 表单
const form = reactive({
  title: '',
  grade: '',
  semester: '',
  description: '',
})
const gradeOptions = ['小学3年级', '小学4年级', '小学5年级', '小学6年级', '初中1年级', '初中2年级', '初中3年级']
const semesterOptions = ['上', '下']
const submitting = ref(false)

// 已选题目
const selectedIds = ref<Set<string>>(new Set())
const selectedMap = ref<Map<string, SimQuestionItem>>(new Map())
const selectedQuestions = computed(() =>
  Array.from(selectedIds.value).map(id => selectedMap.value.get(id)!).filter(Boolean)
)

function toggleSelect(q: SimQuestionItem) {
  if (selectedIds.value.has(q.id)) {
    selectedIds.value.delete(q.id)
    selectedMap.value.delete(q.id)
  } else {
    selectedIds.value.add(q.id)
    selectedMap.value.set(q.id, q)
  }
  selectedIds.value = new Set(selectedIds.value)
}

function removeQuestion(id: string) {
  selectedIds.value.delete(id)
  selectedMap.value.delete(id)
  selectedIds.value = new Set(selectedIds.value)
}

// 题库浏览器
const showBrowser = ref(false)
const browserItems = ref<SimQuestionItem[]>([])
const browserLoading = ref(false)
const filterDiff = ref<number | undefined>(undefined)
const difficultyOptions = ['全部难度', 1, 2, 3, 4, 5]

async function loadBrowser() {
  browserLoading.value = true
  try {
    const r = await listSimQuestions({ difficulty: filterDiff.value, limit: 50 })
    browserItems.value = r.data?.items || []
  } finally {
    browserLoading.value = false
  }
}

// 只读：加载详情
const detail = ref<ClassPaperDetailOut | null>(null)
async function loadDetail() {
  if (!paperId) return
  try {
    const r = await getClassPaperDetail(paperId)
    detail.value = r.data || null
  } catch (e: any) {
    uni.showToast({ title: e?.message || '加载失败', icon: 'none' })
  }
}

async function onSubmit() {
  if (!form.title) { uni.showToast({ title: '请输入试卷名称', icon: 'none' }); return }
  submitting.value = true
  try {
    await createClassPaper(classId, {
      title: form.title,
      grade: form.grade || undefined,
      semester: form.semester || undefined,
      description: form.description || undefined,
      question_ids: Array.from(selectedIds.value),
    })
    uni.showToast({ title: '试卷已保存', icon: 'success' })
    setTimeout(() => uni.navigateBack(), 1200)
  } catch (e: any) {
    uni.showToast({ title: e?.message || '保存失败', icon: 'none' })
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  if (readonly) {
    loadDetail()
  } else {
    loadBrowser()
  }
})
</script>

<style scoped>
.page { padding: 24rpx; background: #f5f5f5; min-height: 100vh; }
.section { background: #fff; border-radius: 12rpx; padding: 24rpx; margin-bottom: 20rpx; }
.section-title { font-size: 28rpx; font-weight: 600; color: #333; display: block; margin-bottom: 16rpx; }
.section-header { display: flex; align-items: center; margin-bottom: 16rpx; }
.section-header .section-title { margin-bottom: 0; flex: 1; }
.input { width: 100%; border: 1px solid #eee; border-radius: 8rpx; padding: 16rpx 20rpx; font-size: 28rpx; margin-bottom: 16rpx; box-sizing: border-box; }
.textarea { width: 100%; border: 1px solid #eee; border-radius: 8rpx; padding: 16rpx 20rpx; font-size: 28rpx; min-height: 100rpx; box-sizing: border-box; }
.picker-row { display: flex; align-items: center; padding: 16rpx 0; border-bottom: 1px solid #f5f5f5; }
.picker-label { font-size: 28rpx; color: #555; width: 80rpx; }
.picker-value { font-size: 28rpx; color: #333; margin-left: 16rpx; }
.btn-browse { background: #4f9bff; color: #fff; font-size: 24rpx; padding: 0 20rpx; height: 56rpx; line-height: 56rpx; border-radius: 8rpx; border: none; }
.tip { text-align: center; color: #aaa; padding: 32rpx 0; font-size: 26rpx; }
.q-chip { display: flex; align-items: center; background: #f0f7ff; border-radius: 8rpx; padding: 16rpx; margin-bottom: 12rpx; }
.q-stem-short { flex: 1; font-size: 26rpx; color: #333; }
.q-remove { width: 32rpx; height: 32rpx; margin-left: 16rpx; flex-shrink: 0; }
.btn-submit { width: 100%; background: #4f9bff; color: #fff; font-size: 30rpx; height: 88rpx; line-height: 88rpx; border-radius: 12rpx; border: none; }
.btn-submit[disabled] { background: #aaa; }

/* 只读模式 */
.paper-header { background: #fff; border-radius: 12rpx; padding: 28rpx; margin-bottom: 20rpx; }
.paper-title { font-size: 36rpx; font-weight: 700; color: #333; display: block; margin-bottom: 12rpx; }
.meta { display: flex; gap: 20rpx; font-size: 24rpx; color: #999; margin-bottom: 8rpx; }
.desc { font-size: 26rpx; color: #666; display: block; margin-top: 8rpx; }
.question-card { background: #fff; border-radius: 12rpx; padding: 24rpx; margin-bottom: 16rpx; }
.q-header { display: flex; align-items: center; gap: 12rpx; margin-bottom: 16rpx; }
.q-no { font-size: 30rpx; font-weight: 700; color: #333; }
.q-type-tag { background: #e8f4ff; color: #4f9bff; font-size: 22rpx; padding: 4rpx 12rpx; border-radius: 20rpx; }
.q-diff { background: #fff7e6; color: #f99; font-size: 22rpx; padding: 4rpx 12rpx; border-radius: 20rpx; }
.q-stem { font-size: 28rpx; color: #333; line-height: 1.6; display: block; }
.options { margin-top: 16rpx; }
.option { font-size: 26rpx; color: #555; padding: 8rpx 0; }

/* 浮层 */
.browser-mask { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,.45); z-index: 100; display: flex; align-items: flex-end; }
.browser-panel { background: #fff; border-radius: 24rpx 24rpx 0 0; width: 100%; max-height: 80vh; display: flex; flex-direction: column; }
.browser-header { display: flex; align-items: center; padding: 28rpx 32rpx 16rpx; border-bottom: 1px solid #eee; }
.browser-title { flex: 1; font-size: 32rpx; font-weight: 700; color: #333; }
.browser-close { width: 36rpx; height: 36rpx; flex-shrink: 0; }
.browser-filters { display: flex; gap: 16rpx; padding: 16rpx 32rpx; }
.filter-chip { background: #f0f0f0; border-radius: 20rpx; padding: 8rpx 24rpx; font-size: 24rpx; color: #555; }
.browser-list { flex: 1; padding: 0 16rpx; overflow: hidden; }
.browser-item { display: flex; align-items: flex-start; padding: 20rpx 16rpx; border-bottom: 1px solid #f5f5f5; }
.browser-item-left { margin-right: 16rpx; padding-top: 4rpx; }
.check { font-size: 32rpx; color: #ccc; }
.checked { color: #4f9bff; }
.browser-item-content { flex: 1; }
.bi-stem { font-size: 26rpx; color: #333; display: block; margin-bottom: 8rpx; line-height: 1.5; }
.bi-meta { display: flex; gap: 12rpx; }
.bi-type { background: #e8f4ff; color: #4f9bff; font-size: 22rpx; padding: 2rpx 10rpx; border-radius: 10rpx; }
.bi-diff { background: #fff7e6; color: #f99; font-size: 22rpx; padding: 2rpx 10rpx; border-radius: 10rpx; }
.browser-footer { display: flex; align-items: center; padding: 20rpx 32rpx; border-top: 1px solid #eee; }
.sel-count { flex: 1; font-size: 26rpx; color: #666; }
.btn-done { background: #4f9bff; color: #fff; font-size: 28rpx; padding: 0 40rpx; height: 72rpx; line-height: 72rpx; border-radius: 12rpx; border: none; }
</style>
