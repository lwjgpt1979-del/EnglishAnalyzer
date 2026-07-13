<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getThirdPartyStatus, getLlmUsage, getLlmBalance,
         type ThirdPartyStatus, type LlmUsage, type LlmBalance } from '../api/admin'

const status = ref<ThirdPartyStatus | null>(null)
const usage = ref<LlmUsage | null>(null)
const balance = ref<LlmBalance | null>(null)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    status.value = await getThirdPartyStatus()
    getLlmUsage(30).then(u => (usage.value = u)).catch(() => {})
    getLlmBalance().then(b => (balance.value = b)).catch(() => {})
  } finally { loading.value = false }
}
onMounted(load)
</script>

<template>
  <div class="page" v-loading="loading">
    <div class="toolbar">
      <h2>第三方 API 资源</h2>
      <span v-if="status" class="sum">
        <el-tag type="success">已配 {{ status.configured }}</el-tag>
        <el-tag v-if="status.mock" type="info">占位 {{ status.mock }}</el-tag>
        <el-tag>共 {{ status.total }} 项</el-tag>
      </span>
      <el-button size="small" @click="load">刷新</el-button>
      <span class="hint">图像 / 声音 / LLM / 存储 的所有第三方付费能力。绿=已配真 key,灰=占位 dev-mock。</span>
    </div>

    <!-- LLM 用量 + 余额 -->
    <el-card class="blk" shadow="never">
      <template #header><b>LLM 用量与余额</b>(DeepSeek · 近 30 天)</template>
      <div class="kpis">
        <div class="kpi"><div class="k-n">{{ usage?.total_calls ?? '—' }}</div><div class="k-l">调用次数</div></div>
        <div class="kpi"><div class="k-n">{{ usage ? (usage.total_prompt_tokens + usage.total_completion_tokens).toLocaleString() : '—' }}</div><div class="k-l">总 token</div></div>
        <div class="kpi"><div class="k-n">¥{{ usage?.est_cost?.toFixed(2) ?? '—' }}</div><div class="k-l">估算成本</div></div>
        <div class="kpi">
          <div class="k-n" :class="{ low: balance?.low }">
            {{ balance?.ok ? `¥${balance.total?.toFixed(2)}` : '—' }}
          </div>
          <div class="k-l">DeepSeek 余额<span v-if="balance && !balance.ok" class="k-x"> ({{ balance.reason }})</span></div>
        </div>
      </div>
      <el-table v-if="usage?.by_model?.length" :data="usage.by_model" size="small" border style="margin-top:12px">
        <el-table-column prop="model" label="模型" min-width="160" />
        <el-table-column prop="calls" label="调用" width="90" />
        <el-table-column prop="prompt_tokens" label="输入 token" width="120" />
        <el-table-column prop="completion_tokens" label="输出 token" width="120" />
        <el-table-column label="成本" width="100"><template #default="{ row }">¥{{ row.cost?.toFixed(2) }}</template></el-table-column>
      </el-table>
    </el-card>

    <!-- 配置总览(分类别)-->
    <el-card v-for="cat in status?.categories || []" :key="cat.category" class="blk" shadow="never">
      <template #header><b>{{ cat.category }}</b></template>
      <el-table :data="cat.items" border size="small">
        <el-table-column label="能力" min-width="150">
          <template #default="{ row }">
            <b>{{ row.name }}</b>
            <el-tag :type="row.mode === 'real' ? 'success' : 'info'" size="small" style="margin-left:8px">
              {{ row.mode === 'real' ? '已配' : '占位' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="provider" label="供应商" width="150" />
        <el-table-column prop="api" label="接口/模型" min-width="150" show-overflow-tooltip />
        <el-table-column prop="purpose" label="用途" min-width="200" show-overflow-tooltip />
        <el-table-column prop="billing" label="计费" width="180" />
        <el-table-column prop="console" label="控制台" min-width="200" show-overflow-tooltip />
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.page { padding: 16px; }
.toolbar { display: flex; align-items: center; gap: 14px; margin-bottom: 16px; flex-wrap: wrap; }
.toolbar h2 { margin: 0; }
.sum { display: flex; gap: 8px; }
.hint { color: #909399; font-size: 13px; }
.blk { margin-bottom: 16px; }
.kpis { display: flex; gap: 24px; flex-wrap: wrap; }
.kpi { min-width: 120px; }
.k-n { font-size: 26px; font-weight: 700; color: #303133; }
.k-n.low { color: #f56c6c; }
.k-l { font-size: 13px; color: #909399; margin-top: 4px; }
.k-x { color: #c0c4cc; }
</style>
