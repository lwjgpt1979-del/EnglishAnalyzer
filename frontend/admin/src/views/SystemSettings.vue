<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getInfoChangeLimit, setInfoChangeLimit, getLearningPlanCaps, updateLearningPlanCaps,
         getReadingAnalyticsConfig, updateReadingAnalyticsConfig } from '../api/admin'
import type { LearningPlanCaps, ReadingAnalyticsConfig } from '../api/admin'
import { Setting } from '@element-plus/icons-vue'

const infoChangeLimit = ref(3)
const loading = ref(false)
const saving = ref(false)

// 今日学习计划·课程每日上限
const caps = ref<LearningPlanCaps>({ word: 10, grammar: 3, sentence: 3 })
const capsLoading = ref(false)
const capsSaving = ref(false)

async function load() {
  loading.value = true
  try { infoChangeLimit.value = (await getInfoChangeLimit()).limit }
  catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}
async function saveInfoChange() {
  saving.value = true
  try { await setInfoChangeLimit(infoChangeLimit.value); ElMessage.success('已保存（次月起按新值计）') }
  catch (e: any) { ElMessage.error(e?.message || '保存失败') }
  finally { saving.value = false }
}

async function loadCaps() {
  capsLoading.value = true
  try { caps.value = await getLearningPlanCaps() }
  catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { capsLoading.value = false }
}
async function saveCaps() {
  capsSaving.value = true
  try { caps.value = await updateLearningPlanCaps(caps.value); ElMessage.success('已保存') }
  catch (e: any) { ElMessage.error(e?.message || '保存失败') }
  finally { capsSaving.value = false }
}

// 阅读学情·判弱阈值
const ra = ref<ReadingAnalyticsConfig>({ weak_word_min_papers: 2, skill_min_sample: 3, skill_weak_rate: 60, struct_min_stuck: 3 })
const raLoading = ref(false)
const raSaving = ref(false)
async function loadRa() {
  raLoading.value = true
  try { ra.value = (await getReadingAnalyticsConfig()).config }
  catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { raLoading.value = false }
}
async function saveRa() {
  raSaving.value = true
  try { ra.value = (await updateReadingAnalyticsConfig(ra.value)).config; ElMessage.success('已保存，即时生效') }
  catch (e: any) { ElMessage.error(e?.message || '保存失败') }
  finally { raSaving.value = false }
}

onMounted(() => { load(); loadCaps(); loadRa() })
</script>

<template>
  <div class="ss">
    <h2><el-icon style="vertical-align:-2px;margin-right:4px"><Setting /></el-icon>系统参数</h2>
    <el-card v-loading="loading" style="max-width: 560px">
      <template #header>学习信息变更月度上限（§5.6）</template>
      <el-form label-width="200px">
        <el-form-item label="每月可改 年级/教材/学期 次数">
          <el-input-number v-model="infoChangeLimit" :min="0" /> 次/月
        </el-form-item>
        <el-button type="primary" :loading="saving" @click="saveInfoChange">保存</el-button>
      </el-form>
      <p class="hint">学生每自然月修改 年级/教材版本/学期 的总次数上限，防滥用。一次改多项算 1 次；城市归属不计入。调整次月 1 日起按新值计，当月已用计数不变。</p>
    </el-card>

    <el-card v-loading="capsLoading" style="max-width: 560px; margin-top: 16px">
      <template #header>今日学习计划 · 课程每日上限</template>
      <el-form label-width="200px">
        <el-form-item label="课程单词 每日上限">
          <el-input-number v-model="caps.word" :min="1" /> 条/天
        </el-form-item>
        <el-form-item label="课程语法 每日上限">
          <el-input-number v-model="caps.grammar" :min="1" /> 条/天
        </el-form-item>
        <el-form-item label="课程长难句 每日上限">
          <el-input-number v-model="caps.sentence" :min="1" /> 条/天
        </el-form-item>
        <el-button type="primary" :loading="capsSaving" @click="saveCaps">保存</el-button>
      </el-form>
      <p class="hint">首页「今日学习计划」课程精讲各模块每天最多提示的数量 = min(当前单元剩余, 本上限)。仅约束课程精讲；作业精讲不封顶（应尽快清完）。改后即时生效。</p>
    </el-card>

    <el-card v-loading="raLoading" style="max-width: 560px; margin-top: 16px">
      <template #header>阅读学情 · 判弱阈值</template>
      <el-form label-width="220px">
        <el-form-item label="高频薄弱词：出现卷数 ≥">
          <el-input-number v-model="ra.weak_word_min_papers" :min="1" /> 卷
        </el-form-item>
        <el-form-item label="题型判弱：最小样本 ≥">
          <el-input-number v-model="ra.skill_min_sample" :min="1" /> 题
        </el-form-item>
        <el-form-item label="题型判弱：正确率 <">
          <el-input-number v-model="ra.skill_weak_rate" :min="1" :max="100" /> %
        </el-form-item>
        <el-form-item label="句法结构判弱：累计卡 ≥">
          <el-input-number v-model="ra.struct_min_stuck" :min="1" /> 次
        </el-form-item>
        <el-button type="primary" :loading="raSaving" @click="saveRa">保存</el-button>
      </el-form>
      <p class="hint">学生端「阅读学情」页据此判定薄弱：考纲词在 ≥N 卷出现算高频薄弱词；某题型样本够(≥M)且正确率&lt;X% 判弱题型；某句法结构累计卡 ≥K 次判弱结构。改后即时生效。</p>
    </el-card>
  </div>
</template>

<style scoped>
.ss { padding: 16px; }
.ss h2 { margin: 0 0 16px; }
.hint { color: #909399; font-size: 12px; margin-top: 12px; line-height: 1.7; }
</style>
