<template>
  <div class="page">
    <h2>作文模板 / 范文配置</h2>
    <p class="hint">按题型配置模板与范文（每行一条范文）。键 _default 为兜底。</p>
    <el-card v-for="(item, key) in form" :key="key" class="tpl-card">
      <template #header>
        <div class="card-head">
          <span>{{ key }}</span>
          <el-button size="small" type="danger" link @click="removeKey(key)">删除</el-button>
        </div>
      </template>
      <el-input v-model="item.template" type="textarea" :rows="3" placeholder="模板" />
      <el-input v-model="item.samplesText" type="textarea" :rows="4" placeholder="范文（每行一条）" style="margin-top: 8px" />
    </el-card>

    <div class="add-row">
      <el-input v-model="newKey" placeholder="新增题型（如 议论文 / _default）" style="width: 240px" />
      <el-button @click="addKey">添加题型</el-button>
    </div>

    <el-button type="primary" :loading="saving" @click="save">保存</el-button>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getEssayTemplates, updateEssayTemplates } from '../api/admin'

type Item = { template: string; samplesText: string }
const form = reactive<Record<string, Item>>({})
const newKey = ref('')
const saving = ref(false)

onMounted(async () => {
  const data = await getEssayTemplates()
  for (const [k, v] of Object.entries(data)) {
    form[k] = { template: v.template, samplesText: (v.samples || []).join('\n') }
  }
})

function addKey() {
  const k = newKey.value.trim()
  if (!k || form[k]) return
  form[k] = { template: '', samplesText: '' }
  newKey.value = ''
}
function removeKey(k: string) { delete form[k] }

async function save() {
  saving.value = true
  try {
    const payload: Record<string, { template: string; samples: string[] }> = {}
    for (const [k, v] of Object.entries(form)) {
      payload[k] = { template: v.template, samples: v.samplesText.split('\n').map((s) => s.trim()).filter(Boolean) }
    }
    await updateEssayTemplates(payload)
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error((e as Error).message || '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.page { padding: 16px; }
.hint { color: #888; font-size: 13px; margin-bottom: 12px; }
.tpl-card { margin-bottom: 16px; }
.card-head { display: flex; justify-content: space-between; align-items: center; }
.add-row { display: flex; gap: 8px; margin: 16px 0; }
</style>
