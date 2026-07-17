<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getVocabImageConfig, updateVocabImageConfig,
  startVocabImageBatch, getVocabImageBatchStatus,
  getVocabImageLowQualityCount, refreshVocabImageLowQuality, reverifyVocabImages,
  type VocabImageBatchStatus,
} from '../api/admin'

const form = reactive({ batch_size: 20, images_per_word: 1, use_ai_prompt: true, primary: '', stylesText: '' })
const loading = ref(false)
const saving = ref(false)
const batch = ref<VocabImageBatchStatus | null>(null)
const starting = ref(false)
const lowQualityCount = ref<number | null>(null)
const refreshing = ref(false)
const reverifying = ref(false)
let timer: any = null

async function load() {
  loading.value = true
  try {
    const c = await getVocabImageConfig()
    form.batch_size = c.batch_size
    form.images_per_word = c.images_per_word
    form.use_ai_prompt = c.use_ai_prompt
    form.primary = c.primary
    form.stylesText = (c.styles || []).join('\n')
    batch.value = await getVocabImageBatchStatus()
    if (batch.value.running) startPolling()
    loadLowQualityCount()
  } finally {
    loading.value = false
  }
}

async function loadLowQualityCount() {
  try { lowQualityCount.value = (await getVocabImageLowQualityCount()).count } catch { /* 忽略 */ }
}

async function runRefresh() {
  refreshing.value = true
  try {
    const r = await refreshVocabImageLowQuality()
    if (!r.started) { ElMessage.warning(r.reason || '没有需重刷的劣质配图'); return }
    ElMessage.success(`已开始重刷劣质配图（${r.total} 个词）`)
    batch.value = await getVocabImageBatchStatus()
    startPolling()
  } finally {
    refreshing.value = false
  }
}

async function runReverify() {
  reverifying.value = true
  try {
    const r = await reverifyVocabImages()
    if (!r.started) { ElMessage.warning(r.reason || '已有批量任务进行中'); return }
    ElMessage.success('已开始复核存量配图(VLM),坏图将自动重刷/降级')
    batch.value = await getVocabImageBatchStatus()
    startPolling()
  } finally {
    reverifying.value = false
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
      use_ai_prompt: form.use_ai_prompt, primary: form.primary, styles,
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
      loadLowQualityCount()
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
        <el-form-item label="AI智能提示词">
          <el-switch v-model="form.use_ai_prompt" active-text="开" inactive-text="关" />
          <span style="color:#909399;font-size:12px;margin-left:8px">开启后用 DeepSeek 把每个词(尤其抽象词/虚词)转成可画的具体场景，再拼下面的要求；图片更能表意</span>
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

    <el-card>
      <template #header>重刷劣质配图</template>
      <p style="color:#909399;font-size:13px;margin:0 0 14px">
        修复历史「有图但没有场景描述(brief)」的配图——这类图当年缺词意/场景直接生成,常是乱码文字图或语义乱配。
        重刷会经「词意+场景双闸门」重新场景化出图,成功即发布替换(失败不覆盖原图)。
      </p>
      <div style="margin-bottom:12px;font-size:13px;color:#606266">
        待重刷:
        <b :style="{ color: (lowQualityCount || 0) > 0 ? '#e6a23c' : '#67c23a' }">
          {{ lowQualityCount === null ? '统计中…' : lowQualityCount }}
        </b>
        个词（每次按上面「批量数量」取一批）
      </div>
      <el-button type="warning" :loading="refreshing" :disabled="batch?.running || (lowQualityCount || 0) === 0"
                 @click="runRefresh">
        {{ batch?.running ? '生成中…' : '重刷一批劣质配图' }}
      </el-button>
    </el-card>

    <el-card>
      <template #header>复核存量配图(VLM)</template>
      <p style="color:#909399;font-size:13px;margin:0 0 14px">
        用视觉模型复核<b>已发布</b>配图,检出「词不达意 / 含文字乱码」的图——包括「有 brief 但仍坏」的
        (上面「重刷劣质」按 brief 有无筛选,覆盖不到这类)。不达标的按新管线(生成前自评→负向约束多图→VLM复核选优)
        重刷,拿不到好图则降级词义卡。<b>游标式</b>:反复点接着上次扫,一轮扫完自动归零;好图按图指纹缓存不二次付费。
      </p>
      <el-button type="primary" :loading="reverifying" :disabled="batch?.running" @click="runReverify">
        {{ batch?.running ? '处理中…' : '复核一批存量配图' }}
      </el-button>
    </el-card>
  </div>
</template>
