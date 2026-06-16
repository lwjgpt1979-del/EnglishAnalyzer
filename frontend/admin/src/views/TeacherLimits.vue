<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getTeacherLimits, updateTeacherLimits } from '../api/admin'

const form = reactive({ max_students: 50, monthly_paper_quota: 10, monthly_grading_quota: 20, warn_threshold_pct: 20, reset_day: 1 })
const loading = ref(false)
const saving = ref(false)

async function load() {
  loading.value = true
  try { Object.assign(form, await getTeacherLimits()) }
  catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}
async function save() {
  saving.value = true
  try { await updateTeacherLimits({ ...form }); ElMessage.success('已保存（次月按重置日生效）') }
  catch (e: any) { ElMessage.error(e?.message || '保存失败') }
  finally { saving.value = false }
}

onMounted(load)
</script>

<template>
  <el-card v-loading="loading" style="max-width: 560px">
    <template #header>👨‍🏫 老师月度限额（全局默认）· §5.6</template>
    <el-form label-width="180px">
      <el-form-item label="同时绑定学生上限">
        <el-input-number v-model="form.max_students" :min="0" /> 名
      </el-form-item>
      <el-form-item label="月度出卷上限">
        <el-input-number v-model="form.monthly_paper_quota" :min="0" /> 份/月
      </el-form-item>
      <el-form-item label="月度批改/点评上限">
        <el-input-number v-model="form.monthly_grading_quota" :min="0" /> 次/月
      </el-form-item>
      <el-form-item label="限额预警阈值">
        <el-input-number v-model="form.warn_threshold_pct" :min="0" :max="100" /> %（剩余低于此值推送预警）
      </el-form-item>
      <el-form-item label="月度重置日">
        <el-input-number v-model="form.reset_day" :min="1" :max="28" /> 号 0:00 重置
      </el-form-item>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </el-form>
    <p class="hint">
      此为全平台默认值。出卷/批改用量按自然月（重置日起）从记录实时计数。<br />
      单个老师可在「教师认证」页设置个体覆盖（留空=随全局）。<br />
      绑定学生上限为老师个体值（新老师默认取此配置）；已超限老师不回溯，仅拦新增绑定。
    </p>
  </el-card>
</template>

<style scoped>
.hint { color: #909399; font-size: 12px; margin-top: 16px; line-height: 1.8; }
</style>
