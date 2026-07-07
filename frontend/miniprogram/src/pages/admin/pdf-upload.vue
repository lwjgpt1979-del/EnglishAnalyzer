<template>
  <view class="page">
    <!-- 步骤指示器 -->
    <view class="steps">
      <view v-for="(s, i) in STEPS" :key="i" class="step-item">
        <view class="step-dot" :class="stepDotClass(i)">{{ i + 1 }}</view>
        <text class="step-label" :class="step === i ? 'step-label-active' : ''">{{ s }}</text>
        <view v-if="i < STEPS.length - 1" class="step-line" :class="step > i ? 'step-line-done' : ''"></view>
      </view>
    </view>

    <!-- ── Step 0：教材信息 ── -->
    <view v-if="step === 0" class="card">
      <view class="card-title">选择教材信息</view>

      <!-- 模式选择 -->
      <view class="mode-row">
        <view class="mode-btn" :class="mode === 'pdf' ? 'mode-active' : ''" @tap="mode = 'pdf'"><view class="ic ic-file mode-ic" /><text>上传 PDF</text></view>
        <view class="mode-btn" :class="mode === 'direct' ? 'mode-active' : ''" @tap="mode = 'direct'"><view class="ic ic-robot mode-ic" /><text>直接 AI 生成</text></view>
      </view>

      <view class="form-item">
        <text class="form-label">教材版本</text>
        <picker :range="VERSIONS" :value="vIdx" @change="vIdx = +($event as any).detail.value">
          <view class="picker-val">{{ VERSIONS[vIdx] }} ▾</view>
        </picker>
      </view>
      <view class="form-item">
        <text class="form-label">年级</text>
        <picker :range="GRADES" :value="gIdx" @change="gIdx = +($event as any).detail.value">
          <view class="picker-val">{{ GRADES[gIdx] }} ▾</view>
        </picker>
      </view>
      <view class="form-item">
        <text class="form-label">学期</text>
        <picker :range="SEMS" :value="sIdx" @change="sIdx = +($event as any).detail.value">
          <view class="picker-val">{{ SEMS[sIdx] }}学期 ▾</view>
        </picker>
      </view>
      <view v-if="mode === 'direct'" class="form-item">
        <text class="form-label">单元数</text>
        <picker :range="UNIT_COUNTS.map(String)" :value="ucIdx" @change="ucIdx = +($event as any).detail.value">
          <view class="picker-val">{{ UNIT_COUNTS[ucIdx] }} 个单元 ▾</view>
        </picker>
      </view>

      <view class="note" v-if="mode === 'pdf'">
        <view class="ic ic-pin note-ic" /><text>上传后将自动识别单元分界；若无法自动识别，可手动指定页码范围。</text>
      </view>
      <view class="note" v-else>
        <view class="ic ic-pin note-ic" /><text>直接用 DeepSeek AI 生成，无需上传课本，约 60-90 秒完成。</text>
      </view>

      <view class="btn-primary" @tap="step = 1">下一步</view>
    </view>

    <!-- ── Step 1：PDF 上传 / 直接生成确认 ── -->
    <view v-if="step === 1" class="card">
      <!-- PDF 上传模式 -->
      <template v-if="mode === 'pdf'">
        <view class="card-title">上传教材 PDF</view>
        <view class="meta-summary">{{ VERSIONS[vIdx] }} · {{ GRADES[gIdx] }} · {{ SEMS[sIdx] }}学期</view>

        <view v-if="!fileId" class="upload-area" @tap="chooseFile">
          <view class="ic ic-upload upload-icon" />
          <text class="upload-hint">点击选择 PDF 文件</text>
          <text class="upload-sub">支持从微信文件、云端等来源选取</text>
        </view>

        <view v-if="uploading" class="uploading-row">
          <text class="uploading-txt">上传中…</text>
        </view>

        <view v-if="fileId" class="upload-done">
          <view class="ic ic-check-circle done-icon" />
          <view class="done-info">
            <text class="done-name">{{ uploadedFilename }}</text>
            <text class="done-pages">共 {{ totalPages }} 页</text>
          </view>
          <text class="done-reselect" @tap="resetUpload">重选</text>
        </view>

        <view v-if="uploadErr" class="err-msg err-msg-row"><view class="ic ic-warning err-ic" /><text>{{ uploadErr }}</text></view>

        <view class="btn-row">
          <view class="btn-ghost" @tap="step = 0">上一步</view>
          <view class="btn-primary" :class="!fileId || uploading ? 'btn-disabled' : ''" @tap="onUploaded">下一步</view>
        </view>
      </template>

      <!-- 直接 AI 生成确认 -->
      <template v-else>
        <view class="card-title">确认生成参数</view>
        <view class="confirm-row"><text class="confirm-k">教材版本</text><text class="confirm-v">{{ VERSIONS[vIdx] }}</text></view>
        <view class="confirm-row"><text class="confirm-k">年级</text><text class="confirm-v">{{ GRADES[gIdx] }}</text></view>
        <view class="confirm-row"><text class="confirm-k">学期</text><text class="confirm-v">{{ SEMS[sIdx] }}学期</text></view>
        <view class="confirm-row"><text class="confirm-k">单元数</text><text class="confirm-v">{{ UNIT_COUNTS[ucIdx] }} 个</text></view>
        <view class="note warn-note"><view class="ic ic-warning note-ic" /><text>生成将覆盖同教材已有内容，约 60-90 秒完成。</text></view>
        <view class="btn-row">
          <view class="btn-ghost" @tap="step = 0">上一步</view>
          <view class="btn-primary" @tap="step = 3; startDirectGenerate()">开始生成</view>
        </view>
      </template>
    </view>

    <!-- ── Step 2：单元划分确认 / 手动编辑 ── -->
    <view v-if="step === 2" class="card">
      <view class="card-title">确认单元划分</view>
      <view class="meta-summary">{{ VERSIONS[vIdx] }} · {{ GRADES[gIdx] }} · {{ SEMS[sIdx] }}学期 · {{ totalPages }} 页</view>

      <view v-if="autoSplitSuccess" class="auto-ok-tip tip-row">
        <view class="ic ic-check-circle tip-ic" /><text>自动识别到 {{ segments.length }} 个单元，可直接生成。也可手动调整下方分界。</text>
      </view>
      <view v-else class="auto-fail-tip tip-row">
        <view class="ic ic-help tip-ic" /><text>未能自动识别单元分界，请手动填写各单元的起止页码（共 {{ totalPages }} 页）。</text>
      </view>

      <!-- 手动添加单元 -->
      <view v-if="!autoSplitSuccess && !segments.length" class="add-seg-hint">
        <text>点击下方按钮添加单元范围</text>
      </view>

      <!-- 单元列表（可编辑） -->
      <view v-for="(seg, i) in segments" :key="i" class="seg-row">
        <view class="seg-no">Unit {{ seg.unit_no }}</view>
        <view class="seg-fields">
          <view class="seg-field">
            <text class="seg-lbl">起始页</text>
            <input
              class="seg-ipt"
              type="number"
              :value="String(seg.start_page)"
              @input="seg.start_page = +($event as any).detail.value || 1"
            />
          </view>
          <text class="seg-dash">—</text>
          <view class="seg-field">
            <text class="seg-lbl">结束页</text>
            <input
              class="seg-ipt"
              type="number"
              :value="String(seg.end_page)"
              @input="seg.end_page = +($event as any).detail.value || seg.start_page"
            />
          </view>
        </view>
        <view v-if="seg.detected_title" class="seg-title-hint">{{ seg.detected_title }}</view>
        <view class="ic ic-close seg-del" @tap="segments.splice(i, 1)" />
      </view>

      <!-- 添加单元按钮 -->
      <view class="btn-add-seg" @tap="addSegment">+ 添加单元</view>

      <view v-if="segErr" class="err-msg">{{ segErr }}</view>

      <view class="btn-row">
        <view class="btn-ghost" @tap="step = 1">上一步</view>
        <view class="btn-primary" :class="!segments.length ? 'btn-disabled' : ''" @tap="validateAndGenerate">开始生成</view>
      </view>
    </view>

    <!-- ── Step 3：生成进度 ── -->
    <view v-if="step === 3" class="card">
      <view class="card-title">{{ generating ? 'AI 生成中…' : '生成完成' }}</view>

      <view v-if="generating" class="gen-progress">
        <view class="spinner"></view>
        <text class="gen-hint">正在逐单元调用 DeepSeek…</text>
        <text class="gen-sub">预计 {{ estSeconds }}，请勿关闭页面</text>
      </view>

      <view v-else class="gen-summary">
        <view class="summary-row ok-row">
          <view class="ic ic-check-circle summary-icon" />
          <text class="summary-txt">成功 {{ genOut.success_count }} 个单元</text>
        </view>
        <view v-if="genOut.error_count" class="summary-row err-row">
          <view class="ic ic-x-circle summary-icon" />
          <text class="summary-txt">失败 {{ genOut.error_count }} 个单元</text>
        </view>

        <view class="result-list">
          <view v-for="r in genOut.results" :key="r.unit_no" class="result-row">
            <view class="ic result-status" :class="r.status === 'ok' ? 'ic-check-circle' : 'ic-x-circle'" />
            <view class="result-info">
              <text class="result-title">Unit {{ r.unit_no }} · {{ r.unit_title }}</text>
              <text v-if="r.status === 'ok'" class="result-sub">{{ r.kp_count }} KP · {{ r.word_count }} 词</text>
              <text v-else class="result-err">{{ r.error }}</text>
            </view>
          </view>
        </view>

        <view class="btn-row">
          <view class="btn-ghost" @tap="backToList">返回列表</view>
          <view v-if="genOut.error_count" class="btn-primary" @tap="step = 2">重试失败单元</view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import {
  uploadCurriculumPdf, getPdfPages, generateFromPdf, generateSemester,
  type UnitSegment, type GenerateFromPdfOut,
} from '@/api/adminCurriculum'

const STEPS       = ['教材信息', '上传/确认', '单元划分', '生成']
const VERSIONS    = ['译林版', '人教版', '外研版', '北师大版']
// 规范年级(与学生端/后端统一;禁用「七年级」旧格式)
const GRADES      = ['小学5年级', '小学6年级', '初中7年级', '初中8年级', '初中9年级']
const SEMS        = ['上', '下']
const UNIT_COUNTS = [4, 5, 6, 7, 8]

const step     = ref(0)
const mode     = ref<'pdf' | 'direct'>('pdf')
const vIdx     = ref(0)
const gIdx     = ref(0)
const sIdx     = ref(0)
const ucIdx    = ref(2)  // 默认 6 单元

// PDF 上传状态
const fileId           = ref('')
const uploadedFilename = ref('')
const totalPages       = ref(0)
const autoSplitSuccess = ref(false)
const uploading        = ref(false)
const uploadErr        = ref('')

// 单元分段
const segments = ref<UnitSegment[]>([])
const segErr   = ref('')

// 生成结果
const generating = ref(false)
const genOut     = ref<GenerateFromPdfOut>({ results: [], success_count: 0, error_count: 0 })

const estSeconds = computed(() => {
  const n = segments.value.length || UNIT_COUNTS[ucIdx.value]
  return `${n * 20}–${n * 30} 秒`
})

onLoad((q) => {
  const query = q as { mode?: string; v?: string; g?: string; s?: string }
  if (query.mode === 'direct') {
    mode.value = 'direct'
    if (query.v) { const i = VERSIONS.indexOf(decodeURIComponent(query.v)); if (i >= 0) vIdx.value = i }
    if (query.g) { const i = GRADES.indexOf(decodeURIComponent(query.g)); if (i >= 0) gIdx.value = i }
    if (query.s) { const i = SEMS.indexOf(query.s); if (i >= 0) sIdx.value = i }
  }
})

// ─── PDF 选择上传 ─────────────────────────────────────────────────────────

function chooseFile() {
  uni.chooseMessageFile({
    count: 1,
    type: 'file',
    extension: ['.pdf'],
    success: async (res) => {
      const f = res.tempFiles[0]
      uploadErr.value = ''
      uploading.value = true
      try {
        const out = await uploadCurriculumPdf(f.path)
        fileId.value           = out.file_id
        uploadedFilename.value = out.filename
        totalPages.value       = out.total_pages
        autoSplitSuccess.value = out.auto_split_success
        if (out.auto_split_success) {
          segments.value = out.auto_segments.map(s => ({ ...s }))
        } else {
          segments.value = []
        }
      } catch (e) {
        uploadErr.value = (e as Error).message
      } finally {
        uploading.value = false
      }
    },
    fail: (e) => {
      if (!e.errMsg?.includes('cancel')) {
        uploadErr.value = e.errMsg || '文件选择失败'
      }
    },
  })
}

function resetUpload() {
  fileId.value = ''
  uploadedFilename.value = ''
  totalPages.value = 0
  segments.value = []
  uploadErr.value = ''
}

function onUploaded() {
  if (!fileId.value || uploading.value) return
  step.value = 2
}

// ─── 手动分段 ────────────────────────────────────────────────────────────

function addSegment() {
  const last = segments.value[segments.value.length - 1]
  const nextNo = segments.value.length + 1
  const nextStart = last ? last.end_page + 1 : 1
  segments.value.push({
    unit_no: nextNo,
    start_page: nextStart,
    end_page: Math.min(nextStart + 19, totalPages.value || 999),
    detected_title: null,
  })
}

function validateAndGenerate() {
  segErr.value = ''
  if (!segments.value.length) { segErr.value = '请至少添加一个单元'; return }
  for (const s of segments.value) {
    if (s.end_page < s.start_page) {
      segErr.value = `Unit ${s.unit_no} 结束页不能小于起始页`; return
    }
  }
  step.value = 3
  startPdfGenerate()
}

// ─── 生成触发 ────────────────────────────────────────────────────────────

async function startPdfGenerate() {
  generating.value = true
  genOut.value = { results: [], success_count: 0, error_count: 0 }
  try {
    const out = await generateFromPdf(fileId.value, {
      textbook_version: VERSIONS[vIdx.value],
      grade: GRADES[gIdx.value],
      semester: SEMS[sIdx.value],
      segments: segments.value,
      content_status: 'published',
    })
    genOut.value = out
  } catch (e) {
    uni.showToast({ title: (e as Error).message || '生成失败', icon: 'none' })
  } finally {
    generating.value = false
  }
}

async function startDirectGenerate() {
  generating.value = true
  genOut.value = { results: [], success_count: 0, error_count: 0 }
  try {
    const rows = await generateSemester({
      textbook_version: VERSIONS[vIdx.value],
      grade: GRADES[gIdx.value],
      semester: SEMS[sIdx.value],
      unit_count: UNIT_COUNTS[ucIdx.value],
      content_status: 'published',
      reset: true,
    })
    // 将 generate-semester 结果适配为 GenerateFromPdfOut 格式展示
    genOut.value = {
      results: rows.map(r => ({
        unit_no: r.unit_no,
        unit_title: r.unit_title,
        kp_count: r.kp_count,
        word_count: r.word_count,
        status: r.status as 'ok' | 'error',
      })),
      success_count: rows.filter(r => r.status === 'ok').length,
      error_count:   rows.filter(r => r.status !== 'ok').length,
    }
  } catch (e) {
    uni.showToast({ title: (e as Error).message || '生成失败', icon: 'none' })
  } finally {
    generating.value = false
  }
}

// ─── 工具 ─────────────────────────────────────────────────────────────────

function stepDotClass(i: number) {
  if (i < step.value) return 'dot-done'
  if (i === step.value) return 'dot-active'
  return 'dot-idle'
}

function backToList() {
  uni.navigateBack()
}
</script>

<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }

/* ── 步骤条 ── */
.steps {
  display: flex; align-items: center; justify-content: center;
  padding: 20rpx 0 28rpx; gap: 0;
}
.step-item { display: flex; align-items: center; gap: 0; }
.step-dot {
  width: 48rpx; height: 48rpx; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 22rpx; font-weight: 700; flex-shrink: 0;
}
.dot-active { background: var(--c-primary); color: var(--c-on-primary); }
.dot-done   { background: #52c41a; color: #fff; }
.dot-idle   { background: var(--c-border); color: var(--c-text-hint); }
.step-label { font-size: 20rpx; color: var(--c-text-hint); margin: 0 8rpx; white-space: nowrap; }
.step-label-active { color: var(--c-ink); font-weight: 600; }
.step-line { width: 40rpx; height: 2rpx; background: var(--c-border); margin: 0 4rpx; }
.step-line-done { background: #52c41a; }

/* ── 卡片 ── */
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); }
.card-title { font-size: var(--fs-h2); font-weight: 700; color: var(--c-ink); margin-bottom: 24rpx; }
.meta-summary { font-size: 24rpx; color: var(--c-text-hint); margin-bottom: 20rpx; }

/* ── 模式选择 ── */
.mode-row { display: flex; gap: 16rpx; margin-bottom: 28rpx; }
.mode-btn {
  flex: 1; text-align: center; padding: 18rpx 0; border-radius: var(--r-btn);
  font-size: 26rpx; border: 2rpx solid var(--c-border); color: var(--c-text-body);
  display: flex; align-items: center; justify-content: center; gap: 8rpx;
}
.mode-ic { width: 32rpx; height: 32rpx; }
.mode-active { border-color: var(--c-primary); background: #eef5ff; font-weight: 700; }

/* ── 表单 ── */
.form-item { display: flex; justify-content: space-between; align-items: center; padding: 20rpx 0; border-bottom: 1rpx solid var(--c-border); }
.form-label { font-size: 28rpx; color: var(--c-ink); }
.picker-val { font-size: 28rpx; color: var(--c-primary); font-weight: 600; }

/* ── 提示 ── */
.note { font-size: 22rpx; color: var(--c-text-hint); background: var(--c-bg-page); border-radius: 8rpx; padding: 16rpx; margin: 20rpx 0; line-height: 1.6; display: flex; align-items: flex-start; gap: 8rpx; }
.note-ic { width: 28rpx; height: 28rpx; flex-shrink: 0; margin-top: 2rpx; }
.warn-note { color: #b8860b; background: #eef5ff; }
.err-msg   { font-size: 24rpx; color: #ff4d4f; margin-top: 12rpx; }
.err-msg-row { display: flex; align-items: center; gap: 8rpx; }
.err-ic { width: 28rpx; height: 28rpx; flex-shrink: 0; }

/* ── 上传区 ── */
.upload-area {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  border: 2rpx dashed var(--c-border); border-radius: var(--r-lg);
  padding: 60rpx 0; margin: 24rpx 0; gap: 12rpx;
}
.upload-icon { width: 64rpx; height: 64rpx; }
.upload-hint { font-size: 28rpx; font-weight: 600; color: var(--c-ink); }
.upload-sub  { font-size: 22rpx; color: var(--c-text-hint); }
.uploading-row { text-align: center; padding: 20rpx; color: var(--c-text-hint); font-size: 26rpx; }
.upload-done {
  display: flex; align-items: center; gap: 16rpx;
  background: var(--c-bg-page); border-radius: var(--r-lg); padding: 20rpx; margin: 16rpx 0;
}
.done-icon { width: 40rpx; height: 40rpx; flex-shrink: 0; }
.done-info { flex: 1; }
.done-name  { font-size: 26rpx; font-weight: 600; color: var(--c-ink); display: block; }
.done-pages { font-size: 22rpx; color: var(--c-text-hint); }
.done-reselect { font-size: 24rpx; color: var(--c-primary); }
.uploading-txt { color: var(--c-text-hint); font-size: 26rpx; }

/* ── 确认行 ── */
.confirm-row { display: flex; justify-content: space-between; padding: 16rpx 0; border-bottom: 1rpx solid var(--c-border); }
.confirm-k { font-size: 26rpx; color: var(--c-text-hint); }
.confirm-v { font-size: 26rpx; font-weight: 600; color: var(--c-ink); }

/* ── 分段编辑 ── */
.auto-ok-tip  { font-size: 24rpx; color: #389e0d; background: #f6ffed; border-radius: 8rpx; padding: 12rpx 16rpx; margin-bottom: 16rpx; }
.auto-fail-tip{ font-size: 24rpx; color: #b8860b; background: #eef5ff; border-radius: 8rpx; padding: 12rpx 16rpx; margin-bottom: 16rpx; }
.tip-row { display: flex; align-items: flex-start; gap: 8rpx; }
.tip-ic { width: 30rpx; height: 30rpx; flex-shrink: 0; margin-top: 2rpx; }
.add-seg-hint { text-align: center; color: var(--c-text-hint); font-size: 24rpx; padding: 24rpx 0; }
.seg-row {
  display: flex; align-items: flex-start; gap: 12rpx;
  padding: 16rpx 0; border-bottom: 1rpx solid var(--c-border); flex-wrap: wrap;
}
.seg-no     { font-size: 22rpx; font-weight: 700; color: var(--c-primary); min-width: 80rpx; padding-top: 8rpx; }
.seg-fields { display: flex; align-items: center; gap: 8rpx; flex: 1; }
.seg-field  { display: flex; flex-direction: column; align-items: center; gap: 4rpx; }
.seg-lbl    { font-size: 18rpx; color: var(--c-text-hint); }
.seg-ipt    {
  width: 100rpx; height: 60rpx; font-size: 26rpx; text-align: center;
  border: 1rpx solid var(--c-border); border-radius: 8rpx;
}
.seg-dash   { font-size: 24rpx; color: var(--c-text-hint); padding-top: 20rpx; }
.seg-title-hint { font-size: 20rpx; color: var(--c-text-hint); width: 100%; padding-left: 92rpx; margin-top: -8rpx; }
.seg-del    { width: 32rpx; height: 32rpx; margin: 8rpx 8rpx 0; flex-shrink: 0; }
.btn-add-seg {
  text-align: center; padding: 20rpx; color: var(--c-primary);
  font-size: 26rpx; border: 1rpx dashed var(--c-primary); border-radius: var(--r-btn); margin-top: 16rpx;
}

/* ── 生成进度 ── */
.gen-progress { display: flex; flex-direction: column; align-items: center; padding: 60rpx 0; gap: 20rpx; }
.spinner {
  width: 64rpx; height: 64rpx; border: 6rpx solid var(--c-border);
  border-top-color: var(--c-primary); border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.gen-hint   { font-size: 28rpx; font-weight: 600; color: var(--c-ink); }
.gen-sub    { font-size: 22rpx; color: var(--c-text-hint); }

/* ── 生成结果 ── */
.gen-summary { display: flex; flex-direction: column; gap: 16rpx; }
.summary-row { display: flex; align-items: center; gap: 12rpx; padding: 16rpx; border-radius: 12rpx; }
.ok-row  { background: #f6ffed; }
.err-row { background: #fff2f0; }
.summary-icon { width: 32rpx; height: 32rpx; flex-shrink: 0; }
.summary-txt  { font-size: 28rpx; font-weight: 600; color: var(--c-ink); }
.result-list  { display: flex; flex-direction: column; gap: 12rpx; margin-top: 8rpx; }
.result-row   { display: flex; align-items: flex-start; gap: 16rpx; padding: 16rpx 0; border-bottom: 1rpx solid var(--c-border); }
.result-status{ width: 30rpx; height: 30rpx; flex-shrink: 0; margin-top: 2rpx; }
.result-info  { flex: 1; }
.result-title { font-size: 26rpx; font-weight: 600; color: var(--c-ink); display: block; }
.result-sub   { font-size: 22rpx; color: var(--c-text-hint); }
.result-err   { font-size: 22rpx; color: #ff4d4f; }

/* ── 通用按钮 ── */
.btn-row { display: flex; gap: 16rpx; margin-top: 32rpx; }
.btn-primary {
  flex: 1; text-align: center; padding: 22rpx 0; border-radius: var(--r-btn);
  background: var(--c-primary); color: var(--c-on-primary); font-size: 28rpx; font-weight: 700; margin-top: 24rpx;
}
.btn-ghost {
  flex: 1; text-align: center; padding: 22rpx 0; border-radius: var(--r-btn);
  background: var(--c-bg-page); color: var(--c-text-body); font-size: 28rpx;
  border: 1rpx solid var(--c-border);
}
.btn-disabled { opacity: 0.4; }
</style>
