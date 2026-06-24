<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { getLlmConfig, updateLlmConfig, getLlmUsage, getLlmBalance, type LlmModelConfig, type LlmUsage, type LlmBalance } from '../api/admin'

const cfg = ref<LlmModelConfig | null>(null)
const model = ref('')          // 编辑中的模型名
const saved = ref('')          // 已保存的生效模型
const presets = ref<string[]>([])
const available = ref<string[]>([])    // 厂商当前真实可用模型(/models)
// 下拉优先用真实可用列表;取不到(dev/网络)回退预设
const modelOptions = computed(() => available.value.length ? available.value : presets.value)
const loading = ref(false)
const saving = ref(false)

// LLM 用量
const usage = ref<LlmUsage | null>(null)
const usageDays = ref(30)
const usageLoading = ref(false)
const FEATURE_LABEL: Record<string, string> = {
  ls_analyze: '长难句·结构解析', ls_paraphrase: '长难句·释义生成',
  ls_translate: '长难句·短翻译评分', ls_verify_subj: '长难句·主观判分', other: '其它',
}
const featLabel = (f: string) => FEATURE_LABEL[f] || f
const fmtTok = (n: number) => n >= 10000 ? (n / 10000).toFixed(1) + '万' : String(n)
async function loadUsage() {
  usageLoading.value = true
  try { usage.value = await getLlmUsage(usageDays.value) }
  catch (e: any) { ElMessage.error(e?.message || '用量加载失败') }
  finally { usageLoading.value = false }
}

// DeepSeek 账户余额
const balance = ref<LlmBalance | null>(null)
async function loadBalance() {
  try { balance.value = await getLlmBalance() } catch { balance.value = null }
}

async function load() {
  loading.value = true
  try {
    const c = await getLlmConfig()
    cfg.value = c
    model.value = c.model
    saved.value = c.model
    presets.value = c.presets || []
    available.value = c.available || []
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
    if (c.available?.length) available.value = c.available
    ElMessage.success(`已切换到 ${c.model},立即生效(无需重启)`)
  } catch (e: any) { ElMessage.error(e?.message || '保存失败(模型可能不在厂商可用列表)') }
  finally { saving.value = false }
}

onMounted(() => { load(); loadUsage(); loadBalance() })
</script>

<template>
  <div v-loading="loading" style="max-width:980px">
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
              <el-option v-for="p in modelOptions" :key="p" :label="p" :value="p" />
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
      <p>· 下拉为厂商<b>实时可用</b>模型(取自 /models{{ available.length ? `:${available.join('、')}` : ',当前取不到→回退预设' }});保存时会校验,<b>不在可用列表的模型会被拒绝</b>,杜绝用到已下线/拼错的模型。</p>
      <p>· <b>默认</b> deepseek-v4-pro。API key / Endpoint 仍走 .env(密钥不入库)。</p>
    </div>

    <!-- LLM 用量与成本 -->
    <div class="toolbar" style="margin-top:28px">
      <h3 style="margin:0">LLM 用量 & 成本</h3>
      <span class="hint">每次真实调用记一行台账;成本为<b>估算</b>(按价目表,可在后端 usage_log_service 调整)。</span>
      <div style="margin-left:auto;display:flex;gap:8px;align-items:center">
        <el-select v-model="usageDays" size="small" style="width:120px" @change="loadUsage">
          <el-option :value="7" label="近 7 天" /><el-option :value="30" label="近 30 天" /><el-option :value="90" label="近 90 天" />
        </el-select>
        <el-button size="small" :loading="usageLoading" @click="loadUsage">刷新</el-button>
      </div>
    </div>

    <el-alert v-if="balance?.ok && balance.low" type="error" :closable="false" show-icon style="margin-bottom:12px"
      :title="`DeepSeek 账户余额不足:¥${(balance.total ?? 0).toFixed(2)}${balance.available === false ? '(账户已不可用)' : `(低于 ¥${balance.threshold})`},请尽快充值`" />

    <div v-loading="usageLoading">
      <div class="stat-row">
        <el-card shadow="never" class="stat" :class="balance?.ok ? (balance.low ? 'danger' : 'ok') : ''">
          <div class="sv">
            <template v-if="balance?.ok">¥{{ (balance.total ?? 0).toFixed(2) }}</template>
            <template v-else>—</template>
          </div>
          <div class="sl">账户余额{{ balance && !balance.ok ? '(' + (balance.reason || '不可用') + ')' : '(DeepSeek 实时)' }}</div>
        </el-card>
        <el-card shadow="never" class="stat"><div class="sv">{{ usage?.total_calls ?? 0 }}</div><div class="sl">调用次数</div></el-card>
        <el-card shadow="never" class="stat"><div class="sv">{{ fmtTok(usage?.total_prompt_tokens ?? 0) }}</div><div class="sl">输入 token</div></el-card>
        <el-card shadow="never" class="stat"><div class="sv">{{ fmtTok(usage?.total_completion_tokens ?? 0) }}</div><div class="sl">输出 token</div></el-card>
        <el-card shadow="never" class="stat hl"><div class="sv">¥{{ (usage?.est_cost ?? 0).toFixed(4) }}</div><div class="sl">估算成本</div></el-card>
      </div>

      <div class="grid2">
        <el-card shadow="never" header="按用途">
          <el-table :data="usage?.by_feature || []" size="small" :show-header="true">
            <el-table-column label="用途"><template #default="{ row }">{{ featLabel(row.feature) }}</template></el-table-column>
            <el-table-column prop="calls" label="次数" width="70" align="right" />
            <el-table-column label="输入" width="80" align="right"><template #default="{ row }">{{ fmtTok(row.prompt_tokens) }}</template></el-table-column>
            <el-table-column label="输出" width="80" align="right"><template #default="{ row }">{{ fmtTok(row.completion_tokens) }}</template></el-table-column>
          </el-table>
        </el-card>
        <el-card shadow="never" header="按模型(含成本估算)">
          <el-table :data="usage?.by_model || []" size="small">
            <el-table-column prop="model" label="模型" />
            <el-table-column prop="calls" label="次数" width="70" align="right" />
            <el-table-column label="输入" width="80" align="right"><template #default="{ row }">{{ fmtTok(row.prompt_tokens) }}</template></el-table-column>
            <el-table-column label="输出" width="80" align="right"><template #default="{ row }">{{ fmtTok(row.completion_tokens) }}</template></el-table-column>
            <el-table-column label="¥估算" width="90" align="right"><template #default="{ row }">¥{{ row.cost.toFixed(4) }}</template></el-table-column>
          </el-table>
        </el-card>
      </div>

      <el-card shadow="never" header="按天" style="margin-top:14px">
        <el-table :data="usage?.by_day || []" size="small" max-height="240">
          <el-table-column prop="day" label="日期" />
          <el-table-column prop="calls" label="次数" width="80" align="right" />
          <el-table-column label="输入 token" width="120" align="right"><template #default="{ row }">{{ fmtTok(row.prompt_tokens) }}</template></el-table-column>
          <el-table-column label="输出 token" width="120" align="right"><template #default="{ row }">{{ fmtTok(row.completion_tokens) }}</template></el-table-column>
        </el-table>
        <el-empty v-if="!(usage?.by_day || []).length" description="所选区间暂无调用" :image-size="60" />
      </el-card>
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
.stat-row { display:flex; gap:12px; margin-bottom:14px; flex-wrap:wrap; }
.stat { flex:1; min-width:140px; text-align:center; }
.stat .sv { font-size:24px; font-weight:700; color:#303133; }
.stat .sl { font-size:12px; color:#909399; margin-top:4px; }
.stat.hl .sv { color:#e6a23c; }
.stat.ok .sv { color:#67c23a; }
.stat.danger .sv { color:#f56c6c; }
.grid2 { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
@media (max-width:760px) { .grid2 { grid-template-columns:1fr; } }
</style>
