<template>
  <view class="page">
    <view class="tabs">
      <text class="tab" :class="{ active: tab === 'students' }" @tap="tab = 'students'">学生</text>
      <text class="tab" :class="{ active: tab === 'report' }" @tap="switchReport">综合报告</text>
      <text class="tab" :class="{ active: tab === 'kp' }" @tap="switchKp">KP 统计</text>
      <text class="tab" :class="{ active: tab === 'vocab' }" @tap="switchVocab">词力通</text>
    </view>

    <button class="btn-assign" @tap="goAssignments">📋 出卷 / 作业</button>
    <button class="btn-assign btn-papers" @tap="goPapers">📝 仿真题组卷</button>

    <!-- ── 学生 tab ── -->
    <view v-if="tab === 'students'">
      <view v-if="loading" class="tip">加载中…</view>
      <view v-else-if="students.length === 0" class="tip">班级暂无学生</view>
      <view v-for="s in students" :key="s.student_id" class="card s-item">
        <text class="s-id">{{ s.nickname || ('学生 ' + s.student_id.slice(0, 8) + '…') }}</text>
        <text class="s-rm" @tap.stop="onRemove(s.student_id)">移除</text>
      </view>
      <view class="card">
        <text class="hint">添加学生（输入已绑定学生的 UUID）：</text>
        <input v-model="newStudentId" class="input" placeholder="学生 UUID" />
        <button class="btn-primary" :disabled="!newStudentId || adding" @tap="onAdd">
          {{ adding ? '添加中…' : '添加' }}
        </button>
      </view>
      <button class="btn-danger" :disabled="deleting" @tap="onDelete">
        {{ deleting ? '解散中…' : '解散班级' }}
      </button>
    </view>

    <!-- ── 综合报告 tab ── -->
    <view v-else-if="tab === 'report'">
      <view v-if="reportLoading" class="tip">生成报告中…</view>
      <view v-else-if="!report" class="tip">无数据</view>
      <view v-else>
        <view class="card">
          <view class="stat-row">
            <view class="stat"><text class="num">{{ report.student_count }}</text><text class="lbl">学生数</text></view>
            <view class="stat"><text class="num">{{ report.total_questions }}</text><text class="lbl">总错题</text></view>
            <view class="stat"><text class="num">{{ Math.round(report.avg_mastery_rate * 100) }}%</text><text class="lbl">班均掌握率</text></view>
          </view>
        </view>
        <view v-if="report.top_error_types.length" class="card">
          <view class="card-title">班级高频错误</view>
          <view v-for="e in report.top_error_types.slice(0, 5)" :key="e.type" class="row">
            <text>{{ e.type }}</text><text class="count">{{ e.count }}</text>
          </view>
        </view>
        <view v-if="report.students_ranking.length" class="card">
          <view class="card-title">掌握率排名</view>
          <view v-for="(s, i) in report.students_ranking" :key="s.student_id" class="row">
            <text>{{ i + 1 }}. {{ s.nickname || ('学生 ' + s.student_id.slice(0, 8) + '…') }}</text>
            <text class="count">{{ Math.round(s.mastery_rate * 100) }}%</text>
          </view>
        </view>
      </view>
    </view>

    <!-- ── KP 统计 tab（M44）── -->
    <view v-else>
      <view v-if="kpLoading" class="tip">加载中…</view>
      <view v-else-if="!kpStats" class="tip">暂无数据</view>
      <view v-else>

        <!-- 班级总览 -->
        <view class="card">
          <view class="stat-row">
            <view class="stat">
              <text class="num">{{ kpStats.student_count }}</text>
              <text class="lbl">班级人数</text>
            </view>
            <view class="stat">
              <text class="num">{{ kpStats.top_weak_kps.length }}</text>
              <text class="lbl">已覆盖KP数</text>
            </view>
            <view class="stat">
              <text class="num" style="color:#ff4d4f">
                {{ kpStats.top_weak_kps.filter(k => k.avg_accuracy < 0.6).length }}
              </text>
              <text class="lbl">班级薄弱KP</text>
            </view>
          </view>
        </view>

        <!-- 班级最薄弱 KP -->
        <view v-if="kpStats.top_weak_kps.length" class="card">
          <view class="card-title">📉 班级最薄弱知识点</view>
          <view class="card-hint">点击任一知识点即可一键布置该项专项作业</view>
          <view class="kp-header-row">
            <text class="kp-col-name">知识点</text>
            <text class="kp-col-acc">班均正确率</text>
            <text class="kp-col-cnt">薄弱人数</text>
          </view>
          <view
            v-for="kp in kpStats.top_weak_kps"
            :key="kp.kp_key"
            class="kp-row kp-row-tappable"
            @tap="goAssignByKp(kp.kp_key)"
          >
            <view class="kp-name-cell-wrap">
              <text class="kp-name-cell">{{ kp.kp_key }}</text>
              <text class="kp-assign-hint">布置作业 ›</text>
            </view>
            <view class="kp-acc-cell">
              <view class="mini-bar-track">
                <view
                  class="mini-bar-fill"
                  :class="accClass(kp.avg_accuracy)"
                  :style="{ width: Math.max(4, Math.round(kp.avg_accuracy * 100)) + '%' }"
                />
              </view>
              <text class="acc-txt" :class="accClass(kp.avg_accuracy)">
                {{ pct(kp.avg_accuracy) }}
              </text>
            </view>
            <text class="kp-cnt-cell">
              {{ kp.weak_count }}/{{ kp.student_count }}人
            </text>
          </view>
        </view>

        <!-- 需关注学生 -->
        <view v-if="kpStats.students_attention.length" class="card">
          <view class="card-title">⚠️ 需重点关注的学生</view>
          <view class="card-hint">整体平均正确率最低，建议优先辅导</view>
          <view
            v-for="(s, i) in kpStats.students_attention"
            :key="s.student_id"
            class="attention-row"
            @tap="goStudentKp(s.student_id, s.nickname)"
          >
            <text class="attention-rank">{{ i + 1 }}</text>
            <view class="attention-info">
              <text class="attention-name">
                {{ s.nickname || ('学生 ' + s.student_id.slice(0, 8) + '…') }}
              </text>
              <text class="attention-sub">
                薄弱KP {{ s.weak_kp_count }} 个 · 共 {{ s.total_kp_count }} 个
              </text>
            </view>
            <view class="attention-right">
              <text class="attention-acc" :class="accClass(s.avg_accuracy)">
                {{ pct(s.avg_accuracy) }}
              </text>
              <text class="attention-arrow">›</text>
            </view>
          </view>
        </view>

        <view v-if="!kpStats.top_weak_kps.length && !kpStats.students_attention.length" class="tip">
          班级学生暂无知识点答题记录
        </view>

      </view>
    </view>

    <!-- 词力通 -->
    <view v-else-if="tab === 'vocab'">
      <view v-if="vocabLoading" class="tip">加载中…</view>
      <view v-else-if="!vocabStats" class="tip">暂无数据</view>
      <view v-else>
        <view class="card">
          <view class="stat-row">
            <view class="stat"><text class="num">{{ vocabStats.student_count }}</text><text class="lbl">班级人数</text></view>
            <view class="stat"><text class="num">{{ vocabStats.avg_mastered }}</text><text class="lbl">人均掌握</text></view>
            <view class="stat"><text class="num">{{ vocabStats.avg_learned }}</text><text class="lbl">人均学词</text></view>
            <view class="stat"><text class="num">{{ vocabStats.active_count }}</text><text class="lbl">近7天活跃</text></view>
          </view>
          <view class="vocab-sub">
            共学 {{ vocabStats.total_learned }} 词 · 已掌握 {{ vocabStats.total_mastered }} · 错词 {{ vocabStats.wrong_total }}
            <text v-if="vocabStats.pron"> · 发音均分 {{ vocabStats.pron.avg ?? '-' }}（{{ vocabStats.pron.tested_students }} 生）</text>
          </view>
        </view>

        <view v-if="vocabStats.class_weak_words.length" class="card">
          <view class="card-title">📉 班级薄弱词</view>
          <view class="weak-wrap">
            <text v-for="(w, i) in vocabStats.class_weak_words" :key="i" class="weak-chip">{{ w }}</text>
          </view>
        </view>

        <view class="card">
          <view class="card-title">学生明细（按掌握排序）</view>
          <view class="vstu-hd">
            <text class="vstu-name">学生</text>
            <text class="vstu-c">掌握</text>
            <text class="vstu-c">学词</text>
            <text class="vstu-c">错词</text>
            <text class="vstu-c">发音</text>
          </view>
          <view v-for="s in vocabStats.students" :key="s.student_id" class="vstu-row">
            <text class="vstu-name">{{ s.nickname }}</text>
            <text class="vstu-c hl">{{ s.mastered }}</text>
            <text class="vstu-c">{{ s.learned }}</text>
            <text class="vstu-c" :class="{ warn: s.wrong > 0 }">{{ s.wrong }}</text>
            <text class="vstu-c">{{ s.pron_avg ?? '-' }}</text>
          </view>
        </view>
      </view>
    </view>

  </view>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { listClassStudents, addClassStudents, removeClassStudent, getClassReport, deleteClass } from '@/api/classes'
import { getClassKpStats, getClassVocabStats, type ClassKpStats, type ClassVocabStats } from '@/api/teacher'
import type { ClassStudentOut, ClassReport } from '@/types/api'

const classId = ref('')
const tab = ref<'students' | 'report' | 'kp' | 'vocab'>('students')

const students = ref<ClassStudentOut[]>([])
const loading = ref(false)
const adding = ref(false)
const newStudentId = ref('')
const deleting = ref(false)

const report = ref<ClassReport | null>(null)
const reportLoading = ref(false)

const kpStats = ref<ClassKpStats | null>(null)
const kpLoading = ref(false)

async function loadStudents() {
  loading.value = true
  try { const r = await listClassStudents(classId.value); students.value = r.data || [] }
  finally { loading.value = false }
}

async function switchReport() {
  tab.value = 'report'
  if (report.value) return
  reportLoading.value = true
  try { const r = await getClassReport(classId.value); report.value = r.data || null }
  finally { reportLoading.value = false }
}

async function switchKp() {
  tab.value = 'kp'
  if (kpStats.value) return
  kpLoading.value = true
  try { kpStats.value = await getClassKpStats(classId.value) }
  catch (e: any) { uni.showToast({ title: e?.message || '加载失败', icon: 'none' }) }
  finally { kpLoading.value = false }
}

const vocabStats = ref<ClassVocabStats | null>(null)
const vocabLoading = ref(false)
async function switchVocab() {
  tab.value = 'vocab'
  if (vocabStats.value) return
  vocabLoading.value = true
  try { vocabStats.value = await getClassVocabStats(classId.value) }
  catch (e: any) { uni.showToast({ title: e?.message || '加载失败', icon: 'none' }) }
  finally { vocabLoading.value = false }
}

async function onAdd() {
  adding.value = true
  try {
    await addClassStudents(classId.value, [newStudentId.value.trim()])
    newStudentId.value = ''
    await loadStudents()
    uni.showToast({ title: '已添加', icon: 'success' })
  } catch (e: any) { uni.showToast({ title: e?.message || '失败', icon: 'none' }) }
  finally { adding.value = false }
}

async function onRemove(sid: string) {
  try { await removeClassStudent(classId.value, sid); await loadStudents() }
  catch (e: any) { uni.showToast({ title: e?.message || '失败', icon: 'none' }) }
}

function goAssignments() { uni.navigateTo({ url: `/pages/teacher/assignments?classId=${classId.value}` }) }
function goAssignByKp(kpKey: string) {
  uni.navigateTo({
    url: `/pages/teacher/assignments?classId=${classId.value}&kpKey=${encodeURIComponent(kpKey)}`,
  })
}
function goPapers() { uni.navigateTo({ url: `/pages/teacher/class-papers?classId=${classId.value}` }) }
function goStudentKp(studentId: string, nickname: string | null) {
  const n = nickname ? encodeURIComponent(nickname) : ''
  uni.navigateTo({ url: `/pages/teacher/student-kp?studentId=${studentId}&nickname=${n}` })
}

async function onDelete() {
  const { confirm } = await new Promise<{ confirm: boolean }>(resolve =>
    uni.showModal({ title: '解散班级', content: '确认解散？班级数据将永久删除。', success: resolve })
  )
  if (!confirm) return
  deleting.value = true
  try {
    await deleteClass(classId.value)
    uni.showToast({ title: '班级已解散', icon: 'success' })
    setTimeout(() => uni.navigateBack(), 1000)
  } catch (e: any) {
    uni.showToast({ title: e?.message || '失败', icon: 'none' })
  } finally { deleting.value = false }
}

onMounted(() => {
  const pages = getCurrentPages()
  classId.value = (pages[pages.length - 1] as any).options?.classId || ''
  if (classId.value) loadStudents()
})

// ── 工具函数 ─────────────────────────────────────────────────────────────────
function pct(acc: number) { return `${(acc * 100).toFixed(0)}%` }
function accClass(acc: number) {
  if (acc >= 0.8) return 'acc-green'
  if (acc >= 0.6) return 'acc-yellow'
  return 'acc-red'
}
</script>

<style scoped>
.page { padding: 16rpx; background: var(--c-bg-page); min-height: 100vh; }
.tabs { display: flex; gap: 12rpx; padding: 8rpx 0 16rpx; }
.tab { padding: 12rpx 28rpx; background: var(--c-bg-card); border-radius: var(--r-pill); font-size: 26rpx; color: var(--c-text-second); }
.tab.active { background: var(--c-primary); color: var(--c-on-primary); font-weight: 700; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin-bottom: 16rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.card-title { font-size: var(--fs-h2); font-weight: 700; color: var(--c-ink); margin-bottom: 12rpx; }
.card-hint { font-size: 22rpx; color: var(--c-text-hint); margin-bottom: 16rpx; }
.tip { text-align: center; padding: 80rpx 0; color: var(--c-text-hint); }
.s-item { display: flex; justify-content: space-between; align-items: center; }
.s-id { font-size: 26rpx; color: var(--c-text-body); }
.s-rm { font-size: 24rpx; color: var(--c-danger); padding: 8rpx 16rpx; }
.hint { font-size: 22rpx; color: var(--c-text-hint); display: block; margin-bottom: 12rpx; }
.btn-papers { background: #52c41a; margin-top: -8rpx; margin-bottom: 16rpx; }
.btn-assign { background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-btn); padding: 16rpx; font-size: 26rpx; font-weight: 700; margin-bottom: 16rpx; }
.input { border: 2rpx solid var(--c-border); border-radius: var(--r-md); padding: 16rpx; font-size: 26rpx; width: 100%; box-sizing: border-box; margin-bottom: 12rpx; }
.btn-primary { background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-btn); padding: 16rpx; font-weight: 700; font-size: 26rpx; }
.btn-primary[disabled] { background: var(--c-primary-soft); color: #9aa7b8; }
.btn-danger { background: var(--c-danger, #e53935); color: #fff; border-radius: var(--r-btn); padding: 20rpx; font-weight: 700; font-size: 26rpx; margin-top: 8rpx; }
.btn-danger[disabled] { opacity: 0.5; }
.stat-row { display: flex; justify-content: space-around; }
.stat { text-align: center; }
.num { font-size: 48rpx; font-weight: 800; color: var(--c-ink); display: block; }
.lbl { font-size: 22rpx; color: var(--c-text-hint); }
.row { display: flex; justify-content: space-between; padding: 6rpx 0; border-bottom: 1rpx solid var(--c-border); font-size: 26rpx; color: var(--c-text-body); }
.count { color: var(--c-gold); font-weight: 700; }

/* ── KP 统计 ── */
.kp-header-row { display: flex; padding: 8rpx 0; border-bottom: 2rpx solid var(--c-border); margin-bottom: 8rpx; }
.kp-col-name { flex: 2; font-size: 22rpx; color: var(--c-text-hint); }
.kp-col-acc  { flex: 2; font-size: 22rpx; color: var(--c-text-hint); }
.kp-col-cnt  { flex: 1; font-size: 22rpx; color: var(--c-text-hint); text-align: right; }
.kp-row { display: flex; align-items: center; padding: 12rpx 0; border-bottom: 1rpx solid var(--c-border); }
.kp-row-tappable:active { background: var(--c-bg-soft); }
.kp-name-cell-wrap { flex: 2; display: flex; flex-direction: column; gap: 2rpx; }
.kp-name-cell { font-size: 26rpx; color: var(--c-text-body); }
.kp-assign-hint { font-size: 20rpx; color: var(--c-primary, #1677ff); }
.kp-acc-cell { flex: 2; display: flex; align-items: center; gap: 8rpx; }
.mini-bar-track { flex: 1; height: 10rpx; background: #f0f0f0; border-radius: 5rpx; overflow: hidden; }
.mini-bar-fill { height: 100%; border-radius: 5rpx; }
.acc-txt { font-size: 22rpx; font-weight: 700; min-width: 60rpx; }
.kp-cnt-cell { flex: 1; font-size: 22rpx; color: var(--c-text-hint); text-align: right; }

/* ── 需关注学生 ── */
.attention-row { display: flex; align-items: center; gap: 16rpx; padding: 16rpx 0; border-bottom: 1rpx solid var(--c-border); }
.attention-rank { width: 40rpx; height: 40rpx; border-radius: 50%; background: var(--c-primary-soft); text-align: center; line-height: 40rpx; font-size: 24rpx; font-weight: 700; color: var(--c-ink); flex-shrink: 0; }
.attention-info { flex: 1; }
.attention-name { font-size: 28rpx; font-weight: 600; color: var(--c-text-body); display: block; }
.attention-sub { font-size: 22rpx; color: var(--c-text-hint); margin-top: 4rpx; display: block; }
.attention-right { display: flex; align-items: center; gap: 8rpx; }
.attention-acc { font-size: 28rpx; font-weight: 700; }
.attention-arrow { font-size: 32rpx; color: #bbb; }

/* ── 颜色 ── */
.acc-green { color: #52c41a; }
.acc-yellow { color: #ffb020; }
.acc-red { color: #ff4d4f; }
.mini-bar-fill.acc-green  { background: #52c41a; }
.mini-bar-fill.acc-yellow { background: #ffb020; }
.mini-bar-fill.acc-red    { background: #ff4d4f; }
/* 词力通 */
.vocab-sub { margin-top: 14rpx; font-size: 24rpx; color: #888; line-height: 1.5; }
.weak-wrap { display: flex; flex-wrap: wrap; gap: 12rpx; }
.weak-chip { font-size: 24rpx; font-weight: 700; color: #d6457e; background: #fff0f5; border-radius: 999rpx; padding: 6rpx 20rpx; }
.vstu-hd, .vstu-row { display: flex; align-items: center; padding: 12rpx 0; }
.vstu-hd { border-bottom: 1rpx solid #eee; font-size: 22rpx; color: #999; }
.vstu-row { border-bottom: 1rpx solid #f5f5f5; font-size: 26rpx; color: #333; }
.vstu-name { flex: 2; }
.vstu-c { flex: 1; text-align: center; }
.vstu-c.hl { color: #34c759; font-weight: 800; }
.vstu-c.warn { color: #ff6b6b; font-weight: 700; }
</style>
