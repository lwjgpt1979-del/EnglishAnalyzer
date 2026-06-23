<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getInfoChangeLimit, setInfoChangeLimit } from '../api/admin'
import { Setting } from '@element-plus/icons-vue'

const infoChangeLimit = ref(3)
const loading = ref(false)
const saving = ref(false)

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

onMounted(load)
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
  </div>
</template>

<style scoped>
.ss { padding: 16px; }
.ss h2 { margin: 0 0 16px; }
.hint { color: #909399; font-size: 12px; margin-top: 12px; line-height: 1.7; }
</style>
