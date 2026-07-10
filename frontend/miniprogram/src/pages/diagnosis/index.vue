<!-- src/pages/diagnosis/index.vue -->
<template>
  <view class="diag-page">
    <view v-if="loading" class="center-tip">生成报告中…</view>
    <view v-else-if="!report" class="center-tip">暂无数据</view>
    <view v-else>

      <!-- 总览卡片 -->
      <view class="card overview">
        <view class="stat-row">
          <view class="stat-item">
            <text class="stat-num">{{ report.total_questions }}</text>
            <text class="stat-label">累计错题</text>
          </view>
          <view class="stat-item">
            <text class="stat-num">{{ report.total_analyzed }}</text>
            <text class="stat-label">已分析</text>
          </view>
          <view class="stat-item">
            <text class="stat-num">{{ report.mastered_count }}</text>
            <text class="stat-label">已掌握</text>
          </view>
          <view class="stat-item">
            <text class="stat-num">{{ (report.mastery_rate * 100).toFixed(0) }}%</text>
            <text class="stat-label">掌握率</text>
          </view>
        </view>
      </view>

      <!-- 口语练习维度 -->
      <view v-if="speakStats && speakStats.total_sessions > 0" class="card speak-card" @tap="() => uni.navigateTo({ url: '/pages/speaking/index' })">
        <view class="card-title" style="display:flex;align-items:center;gap:8rpx"><view class="ic ic-speak" style="width:32rpx;height:32rpx" /><text>口语练习</text></view>
        <view class="stat-row">
          <view class="stat-item">
            <text class="stat-num">{{ speakStats.total_sessions }}</text>
            <text class="stat-label">累计练习</text>
          </view>
          <view class="stat-item">
            <text class="stat-num">{{ speakStats.week_sessions }}</text>
            <text class="stat-label">本周</text>
          </view>
          <view class="stat-item">
            <text class="stat-num">{{ speakStats.avg_score }}</text>
            <text class="stat-label">平均分</text>
          </view>
          <view class="stat-item">
            <text class="stat-num">{{ speakStats.speaking_streak }}<text class="stat-unit">天</text></text>
            <text class="stat-label">连续口语</text>
          </view>
        </view>
      </view>

      <!-- 退步预警（M13）-->
      <view v-if="report.regression_alerts && report.regression_alerts.length > 0" class="card alert-card">
        <view class="alert-head">
          <view class="alert-title"><view class="ic ic-trend-down alert-title-ic" /><text>退步预警</text></view>
          <text class="alert-sub">{{ report.regression_alerts.length }} 个知识点正确率下滑</text>
        </view>
        <view
          v-for="a in report.regression_alerts"
          :key="a.kp_key"
          class="alert-item"
          :class="`sev-${a.severity}`"
          @tap="goTrend(a.kp_key)"
        >
          <view class="alert-row">
            <text class="alert-kp">{{ a.kp_key }}</text>
            <text class="alert-drop">↓{{ Math.round(a.drop * 100) }}%</text>
          </view>
          <text class="alert-detail">
            峰值 {{ Math.round(a.peak_accuracy * 100) }}% → 最新 {{ Math.round(a.latest_accuracy * 100) }}%，建议尽快复习巩固
          </text>
        </view>
      </view>

      <!-- 高频错误类型（CSS 进度条） -->
      <view class="card" v-if="report.top_error_types.length > 0">
        <view class="card-title">高频错误类型 TOP 5</view>
        <view
          v-for="item in report.top_error_types.slice(0, 5)"
          :key="item.error_type"
          class="bar-item"
        >
          <text class="bar-label">{{ item.error_type }}</text>
          <view class="bar-track">
            <view
              class="bar-fill"
              :style="{ width: barWidth(item.count, maxErrorCount) + '%' }"
            />
          </view>
          <text class="bar-count">{{ item.count }}</text>
        </view>
      </view>

      <!-- 题型分布 -->
      <view class="card" v-if="Object.keys(report.question_type_distribution).length > 0">
        <view class="card-title">题型分布</view>
        <view
          v-for="[type, cnt] in distEntries(report.question_type_distribution)"
          :key="type"
          class="bar-item"
        >
          <text class="bar-label">{{ type }}</text>
          <view class="bar-track">
            <view
              class="bar-fill"
              :style="{ width: barWidth(cnt, maxDistCount(report.question_type_distribution)) + '%' }"
            />
          </view>
          <text class="bar-count">{{ cnt }}</text>
        </view>
      </view>

      <!-- 难度分布 -->
      <view class="card" v-if="Object.keys(report.difficulty_distribution).length > 0">
        <view class="card-title">难度分布</view>
        <view
          v-for="[key, cnt] in distEntries(report.difficulty_distribution)"
          :key="key"
          class="bar-item"
        >
          <text class="bar-label">{{ difficultyLabel(key) }}</text>
          <view class="bar-track">
            <view
              class="bar-fill"
              :class="difficultyBarClass(key)"
              :style="{ width: barWidth(cnt, maxDistCount(report.difficulty_distribution)) + '%' }"
            />
          </view>
          <text class="bar-count">{{ cnt }}</text>
        </view>
      </view>

      <!-- 薄弱知识点 -->
      <view class="card" v-if="report.top_weak_knowledge_points.length > 0">
        <view class="card-title">薄弱知识点</view>
        <view class="tags">
          <text
            v-for="kp in report.top_weak_knowledge_points.slice(0, 8)"
            :key="kp.knowledge_point"
            class="tag-kp"
          >
            {{ kp.knowledge_point }}（{{ kp.count }}）
          </text>
        </view>
      </view>

      <!-- 按学期掌握情况（M3 / D-094，来自练习作答记录） -->
      <view class="card" v-if="report.semester_dimension.length > 0">
        <view class="card-title">按学期掌握情况</view>
        <view
          v-for="sem in report.semester_dimension"
          :key="sem.label"
          class="bar-item"
        >
          <text class="bar-label">{{ sem.label }}</text>
          <view class="bar-track">
            <view
              class="bar-fill"
              :class="accClass(sem.accuracy)"
              :style="{ width: Math.round(sem.accuracy * 100) + '%' }"
            />
          </view>
          <text class="bar-count">{{ (sem.accuracy * 100).toFixed(0) }}%</text>
        </view>
        <text class="acc-hint">基于各学期知识点练习作答统计</text>
      </view>

      <!-- 按知识点掌握情况（M3 / D-094，弱项高亮） -->
      <view class="card" v-if="report.kp_dimension.length > 0">
        <view class="card-title">按知识点掌握情况</view>
        <view
          v-for="kp in report.kp_dimension.slice(0, 10)"
          :key="kp.knowledge_point_id"
          class="kpdim-item"
          :class="{ 'kpdim-weak': kp.accuracy < 0.6 }"
        >
          <view class="kpdim-head">
            <text class="kpdim-name">{{ kp.knowledge_point_name }}</text>
            <text class="kpdim-acc" :class="accClass(kp.accuracy)">{{ (kp.accuracy * 100).toFixed(0) }}%</text>
          </view>
          <view class="bar-track">
            <view
              class="bar-fill"
              :class="accClass(kp.accuracy)"
              :style="{ width: Math.round(kp.accuracy * 100) + '%' }"
            />
          </view>
          <text class="kpdim-sub">作答 {{ kp.attempts }} 次 · 答对 {{ kp.correct }} 次</text>
        </view>
        <text class="acc-hint">弱项（正确率低于 60%）已高亮，建议优先攻克</text>
      </view>

      <!-- 知识点掌握台账（M6c，弱项在前 + 复习建议） -->
      <view class="card" v-if="report.mastery_ledger && report.mastery_ledger.length > 0">
        <view class="card-title">知识点掌握台账</view>
        <text class="ledger-hint">综合练习 / 错题 / 作业 / 整卷的累计表现，弱项在前。点击查看趋势 →</text>
        <view
          v-for="item in ledgerShown"
          :key="item.kp_key"
          class="ledger-item"
          :class="`lv-${item.level}`"
          @tap="goTrend(item.kp_key)"
        >
          <view class="ledger-head">
            <text class="ledger-name">{{ item.kp_key }}</text>
            <text class="ledger-acc" :class="`acc-${item.level}`">
              {{ item.total > 0 ? Math.round(item.accuracy * 100) + '%' : '未练习' }}
            </text>
          </view>
          <view class="bar-track">
            <view class="bar-fill" :class="`acc-${item.level}`" :style="{ width: Math.round(item.accuracy * 100) + '%' }" />
          </view>
          <view class="ledger-meta">
            <text class="ledger-sub">对 {{ item.correct_count }} · 错 {{ item.wrong_count }}（共 {{ item.total }}）</text>
            <text class="ledger-badge" :class="`badge-${item.level}`">{{ levelLabel(item.level) }}</text>
          </view>
          <view class="ledger-suggestion"><view class="ic ic-idea ledger-sug-ic" /><text>{{ item.suggestion }}</text></view>
        </view>
        <view
          v-if="report.mastery_ledger.length > LEDGER_PREVIEW"
          class="ledger-toggle"
          @tap="ledgerExpanded = !ledgerExpanded"
        >
          {{ ledgerExpanded ? '收起' : `展开全部 ${report.mastery_ledger.length} 个知识点` }}
        </view>
      </view>

      <!-- 近30天活跃度方格 -->
      <view class="card">
        <view class="card-title">近30天提交</view>
        <view class="activity-grid">
          <view
            v-for="day in report.recent_daily_activity"
            :key="day.date"
            class="activity-cell"
            :class="activityClass(day.count)"
          />
        </view>
        <text class="activity-hint">颜色越深表示提交越多</text>
      </view>

      <!-- AI 学习建议 -->
      <view class="card" v-if="report.top_suggestions.length > 0">
        <view class="card-title">AI 学习建议</view>
        <view
          v-for="(s, i) in report.top_suggestions"
          :key="i"
          class="suggestion-item"
        >
          <text class="suggestion-num">{{ i + 1 }}</text>
          <text class="suggestion-text">{{ s }}</text>
        </view>
      </view>

      <!-- 针对薄弱点练习入口 -->
      <view class="card practice-entry">
        <view class="card-title">智能练习</view>
        <text class="practice-desc">基于你的薄弱知识点，AI 实时生成针对性练习题。</text>
        <button class="btn-practice" @tap="goPractice">开始 AI 练习</button>
      </view>

      <!-- 报告导出 -->
      <view class="card export-entry">
        <view class="card-title">导出报告</view>
        <text class="practice-desc">将学情诊断报告导出为 PDF，可保存或分享给老师。</text>
        <button class="btn-export" :disabled="exporting" @tap="exportPdf">
          <view v-if="!exporting" class="ic ic-file btn-export-ic" />
          <text>{{ exporting ? '生成中…' : '导出 PDF' }}</text>
        </button>
      </view>

    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getDiagnosisReport, exportDiagnosisPdf } from '@/api/diagnosis'
import { getSpeakStats, type SpeakStats } from '@/api/speaking'
import { useAuthStore } from '@/stores/auth'
import type { DiagnosisReport } from '@/types/api'

const auth = useAuthStore()
const report = ref<DiagnosisReport | null>(null)
const speakStats = ref<SpeakStats | null>(null)
const loading = ref(true)  // true until first fetch completes, prevents "暂无数据" flash
const exporting = ref(false)

const maxErrorCount = computed(() => {
  if (!report.value || report.value.top_error_types.length === 0) return 1
  return Math.max(...report.value.top_error_types.map((e) => e.count))
})

// 知识点掌握台账（弱项在前，默认预览前 5 条）
const LEDGER_PREVIEW = 5
const ledgerExpanded = ref(false)
const ledgerShown = computed(() => {
  const all = report.value?.mastery_ledger ?? []
  return ledgerExpanded.value ? all : all.slice(0, LEDGER_PREVIEW)
})

onMounted(async () => {
  if (!auth.isLoggedIn()) await auth.login()
  loading.value = true
  try {
    report.value = await getDiagnosisReport()
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'error' })
  } finally {
    loading.value = false
  }
  // 口语维度独立拉取，失败不影响主报告
  try {
    speakStats.value = await getSpeakStats()
  } catch {
    speakStats.value = null
  }
})

function accClass(accuracy: number): string {
  if (accuracy < 0.6) return 'acc-low'
  if (accuracy < 0.85) return 'acc-mid'
  return 'acc-high'
}

async function exportPdf() {
  if (exporting.value) return
  exporting.value = true
  try {
    const { pdf_base64, filename } = await exportDiagnosisPdf()
    const base64Str = pdf_base64

    // #ifdef H5
    // 浏览器：base64 → Blob → 触发下载（H5 无 getFileSystemManager）
    {
      const byteChars = atob(base64Str)
      const bytes = new Uint8Array(byteChars.length)
      for (let i = 0; i < byteChars.length; i++) bytes[i] = byteChars.charCodeAt(i)
      const blob = new Blob([bytes], { type: 'application/pdf' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
      uni.showToast({ title: 'PDF 已下载', icon: 'success' })
    }
    // #endif

    // #ifndef H5
    // 微信小程序：写本地临时文件 → openDocument
    const fs = uni.getFileSystemManager()
    const tmpPath = `${wx.env.USER_DATA_PATH}/${filename}`
    fs.writeFile({
      filePath: tmpPath,
      data: base64Str,
      encoding: 'base64',
      success: () => {
        uni.openDocument({
          filePath: tmpPath,
          fileType: 'pdf',
          showMenu: true,  // 显示右上角分享菜单
          success: () => {
            uni.showToast({ title: 'PDF 已生成', icon: 'success' })
          },
          fail: (err) => {
            uni.showToast({ title: '打开失败：' + (err.errMsg || ''), icon: 'none' })
          },
        })
      },
      fail: (err) => {
        uni.showToast({ title: '写入失败：' + (err.errMsg || ''), icon: 'none' })
      },
    })
    // #endif
  } catch (e: any) {
    uni.showToast({ title: e?.message || '导出失败', icon: 'none' })
  } finally {
    exporting.value = false
  }
}

function goPractice() {
  uni.navigateTo({ url: '/pages/practice/adaptive' })
}

function levelLabel(level: string): string {
  return ({ weak: '薄弱', medium: '待巩固', good: '已掌握' } as Record<string, string>)[level] || level
}

function goTrend(kpKey: string) {
  uni.navigateTo({ url: `/pages/kp-mastery/trend?kpKey=${encodeURIComponent(kpKey)}` })
}

function barWidth(count: number, max: number): number {
  return max === 0 ? 0 : Math.round((count / max) * 100)
}

function distEntries(dist: Record<string, number>): [string, number][] {
  return Object.entries(dist).sort((a, b) => b[1] - a[1])
}

function maxDistCount(dist: Record<string, number>): number {
  const vals = Object.values(dist)
  return vals.length === 0 ? 1 : Math.max(...vals)
}

function difficultyLabel(key: string): string {
  const map: Record<string, string> = { '1': '简单', '2': '中等', '3': '困难', 'easy': '简单', 'medium': '中等', 'hard': '困难' }
  return map[key] ?? key
}

function difficultyBarClass(key: string): string {
  if (key === '1' || key === 'easy') return 'acc-high'
  if (key === '3' || key === 'hard') return 'acc-low'
  return 'acc-mid'
}

function activityClass(count: number): string {
  if (count === 0) return 'activity-0'
  if (count === 1) return 'activity-1'
  if (count <= 3) return 'activity-2'
  return 'activity-3'
}
</script>

<style scoped>
.diag-page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.center-tip { text-align: center; padding: 120rpx; color: var(--c-text-hint); }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin-bottom: 20rpx; box-shadow: 0 4rpx 24rpx rgba(0, 0, 0, 0.04); }
/* 退步预警（M13）*/
.alert-card { border: 2rpx solid #ffd7d2; }
.alert-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 16rpx; }
.alert-title { display: flex; align-items: center; gap: 8rpx; font-size: var(--fs-h2); font-weight: 800; color: var(--c-danger); }
.alert-title-ic { width: 32rpx; height: 32rpx; }
.alert-sub { font-size: 22rpx; color: var(--c-text-hint); }
.alert-item { padding: 16rpx; border-radius: var(--r-md); background: var(--c-danger-bg); margin-bottom: 12rpx; border-left: 6rpx solid var(--c-danger); }
.alert-item.sev-mid { border-left-color: var(--c-orange); background: #fff4ec; }
.alert-item.sev-low { border-left-color: var(--c-gold); background: #fff8e8; }
.alert-row { display: flex; justify-content: space-between; align-items: baseline; }
.alert-kp { font-size: 28rpx; font-weight: 700; color: var(--c-ink); }
.alert-drop { font-size: 28rpx; font-weight: 800; color: var(--c-danger); }
.alert-item.sev-mid .alert-drop { color: var(--c-orange); }
.alert-detail { display: block; font-size: 22rpx; color: var(--c-text-second); margin-top: 6rpx; line-height: 1.5; }
.card-title { font-size: var(--fs-h2); font-weight: 700; margin-bottom: 20rpx; color: var(--c-ink); }

/* 总览 */
.stat-row { display: flex; justify-content: space-around; }
.stat-item { text-align: center; }
.stat-num { font-size: 56rpx; font-weight: 800; color: var(--c-ink); display: block; }
.stat-label { font-size: 24rpx; color: var(--c-text-hint); }
.stat-unit { font-size: 24rpx; font-weight: 600; color: var(--c-text-hint); }
.speak-card { border-left: 6rpx solid var(--c-primary); }

/* 进度条 */
.bar-item { display: flex; align-items: center; margin-bottom: 16rpx; }
.bar-label { width: 160rpx; font-size: 26rpx; color: var(--c-text-body); flex-shrink: 0; }
.bar-track { flex: 1; background: var(--c-bg-soft); height: 16rpx; border-radius: var(--r-pill); margin: 0 16rpx; }
.bar-fill { height: 100%; background: var(--c-gold); border-radius: var(--r-pill); }
.bar-count { font-size: 24rpx; color: var(--c-text-second); width: 48rpx; text-align: right; }

/* 知识点正确率 */
.acc-hint { display: block; font-size: 22rpx; color: var(--c-text-hint); margin-top: 8rpx; }
.bar-fill.acc-low { background: var(--c-danger); }
.bar-fill.acc-mid { background: var(--c-gold); }
.bar-fill.acc-high { background: #2ecc71; }

/* 按知识点掌握情况（D-094） */
.kpdim-item { margin-bottom: 20rpx; padding: 16rpx; border-radius: var(--r-md); background: var(--c-bg-soft); }
.kpdim-item.kpdim-weak { background: #fdecea; }
.kpdim-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 10rpx; }
.kpdim-name { font-size: 26rpx; font-weight: 600; color: var(--c-ink); }
.kpdim-acc { font-size: 28rpx; font-weight: 700; }
.kpdim-acc.acc-low { color: var(--c-danger); }
.kpdim-acc.acc-mid { color: var(--c-gold); }
.kpdim-acc.acc-high { color: #2ecc71; }
.kpdim-sub { display: block; font-size: 22rpx; color: var(--c-text-hint); margin-top: 8rpx; }

/* 知识点掌握台账（M6c） */
.ledger-hint { display: block; font-size: 22rpx; color: var(--c-text-hint); margin-bottom: 16rpx; }
.ledger-item { padding: 16rpx; border-radius: var(--r-md); background: var(--c-bg-soft); margin-bottom: 16rpx; border-left: 6rpx solid transparent; }
.ledger-item.lv-weak { background: #fdecea; border-left-color: var(--c-danger); }
.ledger-item.lv-medium { background: #fff7e6; border-left-color: var(--c-gold); }
.ledger-item.lv-good { background: #eafaf1; border-left-color: #2ecc71; }
.ledger-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 10rpx; }
.ledger-name { font-size: 26rpx; font-weight: 600; color: var(--c-ink); flex: 1; }
.ledger-acc { font-size: 28rpx; font-weight: 700; margin-left: 12rpx; }
.bar-fill.acc-weak { background: var(--c-danger); }
.bar-fill.acc-medium { background: var(--c-gold); }
.bar-fill.acc-good { background: #2ecc71; }
.acc-weak { color: var(--c-danger); }
.acc-medium { color: var(--c-gold); }
.acc-good { color: #2ecc71; }
.ledger-meta { display: flex; justify-content: space-between; align-items: center; margin-top: 8rpx; }
.ledger-sub { font-size: 22rpx; color: var(--c-text-hint); }
.ledger-badge { font-size: 20rpx; padding: 2rpx 14rpx; border-radius: var(--r-pill); }
.badge-weak { background: var(--c-danger); color: #fff; }
.badge-medium { background: var(--c-gold); color: #fff; }
.badge-good { background: #2ecc71; color: #fff; }
.ledger-suggestion { display: flex; align-items: flex-start; gap: 6rpx; font-size: 22rpx; color: var(--c-text-second); margin-top: 10rpx; line-height: 1.5; }
.ledger-sug-ic { width: 26rpx; height: 26rpx; flex-shrink: 0; margin-top: 2rpx; }
.ledger-toggle { text-align: center; font-size: 24rpx; color: var(--c-primary, #1677ff); padding: 12rpx; }

/* 知识点标签 */
.tags { display: flex; flex-wrap: wrap; gap: 12rpx; }
.tag-kp {
  background: #eaeac4;
  color: #6b6b2e;
  font-size: 24rpx;
  font-weight: 600;
  padding: 6rpx 16rpx;
  border-radius: var(--r-pill);
}

/* 活跃度方格 */
.activity-grid { display: flex; flex-wrap: wrap; gap: 6rpx; margin-bottom: 12rpx; }
.activity-cell { width: 28rpx; height: 28rpx; border-radius: 6rpx; }
.activity-0 { background: var(--c-bg-soft); }
.activity-1 { background: #fdf0b4; }
.activity-2 { background: var(--c-primary); }
.activity-3 { background: var(--c-gold); }
.activity-hint { font-size: 22rpx; color: var(--c-text-hint); }

/* 建议 */
.suggestion-item { display: flex; align-items: flex-start; margin-bottom: 20rpx; }
.suggestion-num {
  width: 44rpx;
  height: 44rpx;
  background: var(--c-primary);
  color: var(--c-on-primary);
  border-radius: 50%;
  font-size: 24rpx;
  font-weight: 700;
  line-height: 44rpx;
  text-align: center;
  flex-shrink: 0;
  margin-right: 16rpx;
}
.suggestion-text { flex: 1; font-size: 28rpx; color: var(--c-text-body); line-height: 1.7; }

.practice-entry { }
.practice-desc { font-size: 24rpx; color: var(--c-text-second); display: block; margin-bottom: 12rpx; line-height: 1.5; }
.btn-practice { background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-btn); padding: 16rpx; font-size: 28rpx; font-weight: 700; text-align: center; }
.export-entry { margin-top: 24rpx; }
.btn-export { display: flex; align-items: center; justify-content: center; gap: 8rpx; background: #f0f0f0; color: var(--c-ink); border-radius: var(--r-btn); padding: 16rpx; font-size: 28rpx; font-weight: 600; text-align: center; border: 2rpx solid var(--c-border); }
.btn-export-ic { width: 30rpx; height: 30rpx; }
.btn-export[disabled] { opacity: 0.5; }
</style>
