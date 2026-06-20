<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getLlmConfig, updateLlmConfig, type LlmModelConfig } from '../api/admin'

const cfg = ref<LlmModelConfig | null>(null)
const model = ref('')          // 编辑中的模型名
const saved = ref('')          // 已保存的生效模型
const presets = ref<string[]>([])
const loading = ref(false)
const saving = ref(false)

async function load() {
  loading.value = true
  try {
    const c = await getLlmConfig()
    cfg.value = c
    model.value = c.model
    saved.value = c.model
    presets.value = c.presets || []
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}

async function onSave() {
  const m = model.value.trim()
  if (!m) { ElMessage.warning('模型名不能为空'); return }
  saving.value = true
  try {
    const c = await updateLlmConfig(m)
    cfg.value = c; model.value = c.model; saved.value = c.model
    ElMessage.success(`已切换到 ${c.model},立即生效(无需重启)`)
  } catch (e: any) { ElMessage.error(e?.message || '保存失败') }
  finally { saving.value = false }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" style="max-width:640px">
    <div class="toolbar">
      <h3 style="margin:0">模型配置</h3>
      <span class="hint">设置调用大模型用哪个模型名(OpenAI 兼容)。保存后所有 AI 功能(整卷匹配、教材生成、作文批改等)即刻改用新模型,无需重启。</span>
    </div>

    <el-alert v-if="cfg?.dev_mock" type="warning" :closable="false" show-icon style="margin-bottom:14px"
      title="当前为 dev-mock 模式" description="API key 是占位符(sk-placeholder),AI 调用走本地确定性 mock,不会真正请求模型。配置真实 DEEPSEEK_API_KEY 后才会用此处模型。" />

    <el-card shadow="never">
      <el-form label-width="100px">
        <el-form-item label="生效模型">
          <div style="display:flex;gap:10px;flex:1;align-items:center">
            <el-select v-model="model" filterable allow-create default-first-option
              placeholder="选择或自填模型名" style="flex:1">
              <el-option v-for="p in presets" :key="p" :label="p" :value="p" />
            </el-select>
            <el-tag v-if="model.trim() === saved" type="success" effect="plain">当前生效</el-tag>
            <el-tag v-else type="warning" effect="plain">未保存</el-tag>
          </div>
        </el-form-item>
        <el-form-item label="Endpoint">
          <span class="ro">{{ cfg?.base_url }}</span>
          <span class="muted">(只读,改 .env 的 LLM_BASE_URL)</span>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
          <el-button :disabled="saving" @click="load">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <div class="note">
      <p>· 模型名可从下拉选常见 DeepSeek 模型,也可<b>自填</b>任意 OpenAI 兼容模型名(回车确认)。</p>
      <p>· <b>默认</b> deepseek-v4-pro。API key / Endpoint 仍走 .env(密钥不入库)。</p>
    </div>
  </div>
</template>

<style scoped>
.toolbar { display:flex; align-items:center; gap:14px; margin-bottom:16px; flex-wrap:wrap; }
.hint { color:#909399; font-size:12px; }
.muted { color:#c0c4cc; font-size:12px; margin-left:8px; }
.ro { font-family:monospace; color:#606266; }
.note { margin-top:14px; color:#909399; font-size:12px; line-height:1.8; }
.note p { margin:0; }
</style>
