<template>
  <view class="page">
    <view class="hd">
      <text class="hd-title">{{ modeLabel }} · 单词</text>
      <text class="hd-sub">{{ mode === 'homework' ? '按批次(卷/日期)' : '按 年级 → 册 → 单元' }}</text>
    </view>

    <view v-if="loading" class="tip">加载中…</view>

    <!-- 一级:作业=批次列表 / 课程=闯关地图;点卷/单元 → 跳独立卷详情页,原生返回回来 -->
    <template v-else>
      <template v-if="mode === 'homework'">
        <view v-if="!groups.length" class="tip">还没有加入待学习的单词——去上传的试卷里挑生词加入</view>
        <IntensiveBatchList v-else :batches="hwItems" unit="词" @open="openById" />
      </template>
      <UnitLevelMap v-else :units="courseUnits" unit="词" :title="semLabel" :next-hint="nextHint" @open="openCourseUnit" />
    </template>

    <!-- 学完当前学期:庆祝弹层(测验 / 预习下册 / 复习)-->
    <SemesterDoneModal :visible="showDone" :semester-label="semLabel" unit-label="单词"
      :unit-total="courseUnits.length" :content-total="courseWordTotal" :next-semester="nextSemester"
      @quiz="onSemesterQuiz" @preview="onPreviewNext" @review="showDone = false" @close="showDone = false" />
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import { getHwWordBatches, getCourseWordUnits,
         type HwWordBatch, type CourseWordUnit } from '@/api/vocabulary'
import IntensiveBatchList, { type BatchItem } from '@/components/IntensiveBatchList.vue'
import UnitLevelMap from '@/components/UnitLevelMap.vue'
import SemesterDoneModal from '@/components/SemesterDoneModal.vue'

const mode = ref('homework')
const loading = ref(true)
const groups = ref<any[]>([])          // {id, title, sub, count, studied}
const modeLabel = computed(() => (mode.value === 'homework' ? '作业精讲' : '课程精讲'))

// 作业批次 → 统一批次组件(状态/时间轴/进度);sub 即日期
const hwItems = computed<BatchItem[]>(() => groups.value.map(g => ({
  id: g.id, title: g.title, date: g.sub, count: g.count, studied: g.studied,
})))
// 点作业名 → 跳独立卷详情页(words-paper),原生返回回本列表
function openById(id: string) {
  const g = groups.value.find(x => x.id === id)
  if (!g) return
  const t = encodeURIComponent(g.title || '单词精讲')
  const s = encodeURIComponent(g.sub || '')
  uni.navigateTo({ url: `/pages/intensive/words-paper?mode=homework&id=${id}&title=${t}&sub=${s}` })
}

// 课程精讲·闯关地图 + 学完庆祝弹层
const courseUnits = ref<CourseWordUnit[]>([])
const courseGrade = ref<string | undefined>(undefined)   // 空=后端默认当前学期;切学期时赋值
const courseSem = ref<string | undefined>(undefined)
const semLabel = ref('课程')
const nextSemester = ref<{ grade: string; semester: string } | null>(null)
const showDone = ref(false)
const courseWordTotal = computed(() => courseUnits.value.reduce((a, u) => a + (u.word_count || 0), 0))
const nextHint = computed(() => nextSemester.value
  ? `闯完本册接入 ${nextSemester.value.grade}${nextSemester.value.semester}册` : '')
// 点单元 → 跳独立卷详情页(words-paper),原生返回回来
function openCourseUnit(unitId: string) {
  const u = courseUnits.value.find(x => x.unit_id === unitId)
  if (!u) return
  const t = encodeURIComponent(u.unit_title || '单词精讲')
  const s = encodeURIComponent(`第${u.unit_no}单元`)
  uni.navigateTo({ url: `/pages/intensive/words-paper?mode=course&id=${unitId}&title=${t}&sub=${s}` })
}
function onPreviewNext() {   // 预习下学期:切 grade/semester 重新加载
  if (!nextSemester.value) return
  courseGrade.value = nextSemester.value.grade
  courseSem.value = nextSemester.value.semester
  showDone.value = false
  load()
}
function onSemesterQuiz() { uni.showToast({ title: '学期测验即将上线', icon: 'none' }) }

async function load() {
  loading.value = true
  try {
    if (mode.value === 'homework') {
      const bs: HwWordBatch[] = (await getHwWordBatches()).batches
      groups.value = bs.map(b => ({ id: b.paper_id, title: b.title, sub: b.date, count: b.word_count, studied: b.studied }))
    } else {
      const r = await getCourseWordUnits(courseGrade.value, courseSem.value)
      courseUnits.value = r.units
      semLabel.value = r.grade && r.semester ? `${r.grade}${r.semester}册` : '课程'
      nextSemester.value = r.next_semester
      showDone.value = r.semester_done
    }
  } catch (e: any) { uni.showToast({ title: e?.message || '加载失败', icon: 'none' }) }
  finally { loading.value = false }
}

onLoad((q: any) => { mode.value = q.mode || 'homework'; load() })
// 从卷详情页返回 → 刷新批次/单元进度(跳过 onLoad 后的首次)
let _shown = false
onShow(() => { if (!_shown) { _shown = true; return } load() })
</script>

<style scoped>
.page { min-height: 100vh; background: var(--c-bg, #f5f7fa); padding: 24rpx; box-sizing: border-box; }
.hd { padding: 8rpx 4rpx 16rpx; }
.hd-title { font-size: 38rpx; font-weight: 800; color: var(--c-ink); display: block; }
.hd-sub { font-size: 23rpx; color: var(--c-text-hint); margin-top: 6rpx; display: block; }
.tip { text-align: center; color: var(--c-text-hint); padding: 70rpx 24rpx; line-height: 1.6; }
</style>
