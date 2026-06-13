<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getVocabImageConfig, updateVocabImageConfig,
  startVocabImageBatch, getVocabImageBatchStatus,
  type VocabImageBatchStatus,
} from '../api/admin'

const form = reactive({ batch_size: 20, images_per_word: 1, primary: '', stylesText: '' })
const loading = ref(false)
const saving = ref(false)
const batch = ref<VocabImageBatchStatus | null>(null)
const starting = ref(false)
let timer: any = null

async function load() {
  loading.value = true
  try {
    const c = await getVocabImageConfig()
    form.batch_size = c.batch_size
    form.images_per_word = c.images_per_word
    form.primary = c.primary
    form.stylesText = (c.styles || []).join('\n')
    batch.value = await getVocabImageBatchStatus()
    if (batch.value.running) startPolling()
  } finally {
    loading.value = false
  }
}

async function save() {
  const styles = form.stylesText.split('\n').map(s => s.trim()).filter(Boolean)
  if (!form.primary.trim()) { ElMessage.warning('主要要求不能为空'); return }
  if (!styles.length) { ElMessage.warning('至少配 1 个风格'); return }
  saving.value = true
  try {
    await updateVocabImageConfig({
      batch_size: form.batch_size, images_per_word: form.images_per_word,
      primary: form.primary, styles,
    })
    ElMessage.success('已保存')
  } finally {
    saving.value = false
  }
}

function startPolling() {
  if (timer) return
  timer = setInterval(async () => {
    batch.value = await getVocabImageBatchStatus()
    if (!batch.value.running) {
      stopPolling()
      ElMessage.success(`批量完成：成功 ${batch.value.ok} / ${batch.value.total}，失败 ${batch.value.failed}`)
    }
  }, 3000)
}
function stopPolling() { if (timer) { clearInterval(timer); timer = null } }

async function runBatch() {
  starting.value = true
  try {
    const r = await startVocabImageBatch()
    if (!r.started) { ElMessage.warning(r.reason || '未能启动'); return }
    ElMessage.success(`已开始批量配图（${r.total} 个词）`)
    batch.value = await getVocabImageBatchStatus()
    startPolling()
  } finally {
    starting.value = false
  }
}

const pct = () => batch.value && batch.value.total ? Math.round((batch.value.done / batch.value.total) * 100) : 0

onMounted(load)
onUnmounted(stopPolling)
</script>

<template>
  <div v-loading="loading" style="display:flex;flex-direction:column;gap:16px;max-width:760px">
    <el-alert type="info" :closable="false" show-icon
      title="词力通配图：腾讯混元生图极速版。提示词 = 主要要求(固定) + 每词随机抽一个风格(多样化)。批量对「未配图」的单词按数量生成。" />

    <el-card>
      <template #header>配图提示词配置</template>
      <el-form label-width="120px">
        <el-form-item label="一次批量数量">
          <el-input-number v-model="form.batch_size" :min="1" :max="200" :step="5" />
          <span style="color:#909399;font-size:12px;margin-left:8px">每次「批量配图」处理多少个未配图的词</span>
        </el-form-item>
        <el-form-item label="每词图片数">
          <el-input-number v-model="form.images_per_word" :min="1" :max="3" />
          <span style="color:#909399;font-size:12px;margin-left:8px">每词生成几张（×单价计费）</span>
        </el-form-item>
        <el-form-item label="主要要求">
          <el-input v-model="form.primary" type="textarea" :rows="4"
            placeholder="可用占位符 {word} {meaning}" />
          <span style="color:#909399;font-size:12px">固定要求模板，支持 {word}（单词）{meaning}（中文释义）占位符</span>
        </el-form-item>
        <el-form-item label="次要随机风格">
          <el-input v-model="form.stylesText" type="textarea" :rows="6"
            placeholder="一行一个风格，生成时每词随机抽一个" />
          <span style="color:#909399;font-size:12px">一行一个；每个词随机抽一个风格拼到主要要求后，图片更多样</span>
        </el-form-item>
        <el-button type="primary" :loading="saving" @click="save">保存配置</el-button>
      </el-form>
    </el-card>

    <el-card>
      <template #header>批量配图</template>
      <p style="color:#909399;font-size:13px;margin:0 0 14px">
        对当前「未配图」的单词，按上面的「批量数量」取一批，用配置的提示词逐词生成 → 转存 COS。
      </p>
      <el-button type="primary" :loading="starting" :disabled="batch?.running" @click="runBatch">
        {{ batch?.running ? '生成中…' : '开始批量配图' }}
      </el-button>
      <div v-if="batch && (batch.running || batch.total)" style="margin-top:16px">
        <div style="font-size:13px;color:#606266;margin-bottom:6px">
          {{ batch.done }}/{{ batch.total }}（成功 {{ batch.ok }}，失败 {{ batch.failed }}）
        </div>
        <el-progress :percentage="pct()" :status="batch.running ? '' : 'success'" />
      </div>
    </el-card>
  </div>
</template>
