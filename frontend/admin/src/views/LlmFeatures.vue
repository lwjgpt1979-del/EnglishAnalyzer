<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getLlmFeatures, type LlmFeatures, type LlmFeatureItem } from '../api/admin'

const data = ref<LlmFeatures | null>(null)
const loading = ref(false)
const days = ref(30)

// 筛选
const kw = ref('')
const modeFilter = ref<'all' | 'reasoning' | 'chat'>('all')
const surfaceFilter = ref<'all' | '小程序端' | '运营后台'>('all')
const taggedFilter = ref<'all' | 'tagged' | 'untagged'>('all')
// 排序
const sortKey = ref<'default' | 'cost' | 'calls'>('default')
// 分页
const page = ref(1)
const pageSize = ref(20)

const fmtTok = (n: number | null) => n == null ? '—' : n >= 10000 ? (n / 10000).toFixed(1) + '万' : String(n)

async function load() {
  loading.value = true
  try { data.value = await getLlmFeatures(days.value) }
  catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}
function reload() { page.value = 1; load() }

const filtered = computed<LlmFeatureItem[]>(() => {
  let rows = data.value?.items || []
  if (modeFilter.value !== 'all') rows = rows.filter(r => r.mode === modeFilter.value)
  if (surfaceFilter.value !== 'all') rows = rows.filter(r => r.surface === surfaceFilter.value)
  if (taggedFilter.value === 'tagged') rows = rows.filter(r => r.tagged)
  else if (taggedFilter.value === 'untagged') rows = rows.filter(r => !r.tagged)
  const q = kw.value.trim().toLowerCase()
  if (q) rows = rows.filter(r =>
    r.purpose.toLowerCase().includes(q) || r.why.toLowerCase().includes(q) ||
    r.service.toLowerCase().includes(q) || r.module.toLowerCase().includes(q) ||
    r.surface.includes(q) || (r.feature || '').toLowerCase().includes(q) ||
    r.locations.some(l => l.toLowerCase().includes(q)))
  const arr = [...rows]
  if (sortKey.value === 'cost') arr.sort((a, b) => (b.est_cost ?? -1) - (a.est_cost ?? -1))
  else if (sortKey.value === 'calls') arr.sort((a, b) => (b.calls ?? -1) - (a.calls ?? -1))
  else arr.sort((a, b) => (a.mode === b.mode ? a.service.localeCompare(b.service) : a.mode === 'reasoning' ? -1 : 1))
  return arr
})
const paged = computed(() => {
  const s = (page.value - 1) * pageSize.value
  return filtered.value.slice(s, s + pageSize.value)
})
// 当前筛选结果的用量小计
const subtotal = computed(() => filtered.value.reduce((a, r) => ({
  calls: a.calls + (r.calls ?? 0), cost: a.cost + (r.est_cost ?? 0),
}), { calls: 0, cost: 0 }))

onMounted(load)
</script>

<template>
  <div v-loading="loading" style="max-width:1200px">
    <div class="toolbar">
      <h3 style="margin:0">LLM 调用清单</h3>
      <span class="hint">系统里每一处调 DeepSeek LLM 的地方 · 标注<b>深度思考 / 对话</b> · 需要深度思考的原因 · 合并近 N 天真实用量。新增调用点请同步登记 <code>llm_feature_registry.py</code>。</span>
      <div style="margin-left:auto;display:flex;gap:8px;align-items:center">
        <el-select v-model="days" size="small" style="width:120px" @change="reload">
          <el-option :value="7" label="近 7 天" /><el-option :value="30" label="近 30 天" /><el-option :value="90" label="近 90 天" />
        </el-select>
        <el-button size="small" :loading="loading" @click="load">刷新</el-button>
      </div>
    </div>

    <!-- 概览 -->
    <div class="stat-row">
      <el-card shadow="never" class="stat"><div class="sv">{{ data?.counts.total ?? 0 }}</div><div class="sl">调用点总数</div></el-card>
      <el-card shadow="never" class="stat r"><div class="sv">{{ data?.counts.reasoning ?? 0 }}</div><div class="sl">深度思考(推理档)</div></el-card>
      <el-card shadow="never" class="stat c"><div class="sv">{{ data?.counts.chat ?? 0 }}</div><div class="sl">对话(快档)</div></el-card>
      <el-card shadow="never" class="stat w"><div class="sv">{{ data?.counts.untagged ?? 0 }}</div><div class="sl">未打 feature 标签</div></el-card>
    </div>

    <div class="models">
      <span>深度思考模型 <b class="mono">{{ data?.reasoning_model || '—' }}</b>(不传 model → 主模型/推理档,thinking 开)</span>
      <span>对话模型 <b class="mono">{{ data?.chat_model || '—' }}</b>(走快档 <code>fast_model()</code> 或 <code>disable_thinking=True</code>)</span>
      <span>端分布:小程序端 <b>{{ data?.counts.mini ?? 0 }}</b> · 运营后台 <b>{{ data?.counts.admin ?? 0 }}</b></span>
      <span class="muted">LLM 代码均在<b>后端</b> backend/app/services;下表「端」= 消费该能力的前端项目,「位置」= 后端 service 文件。</span>
    </div>

    <el-alert v-if="data?.counts.untagged" type="info" :closable="false" show-icon style="margin-bottom:10px"
      :title="`有 ${data.counts.untagged} 处调用未打 feature 标签`"
      description="未打标签的调用无法在用量台账里单独统计(会并入 null/其它)。多为深度思考的高成本调用,建议在 chat_completion/complete_json 传 feature= 以便计量。" />
    <el-alert v-if="data?.unregistered?.length" type="warning" :closable="false" show-icon style="margin-bottom:10px"
      :title="`用量里出现 ${data.unregistered.length} 个未登记的 feature`"
      :description="`${data.unregistered.map(u => u.feature).join('、')} 有历史用量但不在清单登记表。若是新调用点漏登记→补进 llm_feature_registry.py;若是已下线旧特征(retired code 的残留台账)可忽略。注:other=所有未打标签(feature=None)调用的汇总桶。`" />

    <!-- 筛选 -->
    <div class="filters">
      <el-input v-model="kw" placeholder="搜用途 / 原因 / 服务 / feature / 位置" clearable size="small" style="width:280px" @input="page = 1" />
      <el-radio-group v-model="modeFilter" size="small" @change="page = 1">
        <el-radio-button value="all">全部</el-radio-button>
        <el-radio-button value="reasoning">深度思考</el-radio-button>
        <el-radio-button value="chat">对话</el-radio-button>
      </el-radio-group>
      <el-radio-group v-model="surfaceFilter" size="small" @change="page = 1">
        <el-radio-button value="all">全端</el-radio-button>
        <el-radio-button value="小程序端">小程序端</el-radio-button>
        <el-radio-button value="运营后台">运营后台</el-radio-button>
      </el-radio-group>
      <el-radio-group v-model="taggedFilter" size="small" @change="page = 1">
        <el-radio-button value="all">标签不限</el-radio-button>
        <el-radio-button value="tagged">已打标签</el-radio-button>
        <el-radio-button value="untagged">未打标签</el-radio-button>
      </el-radio-group>
      <el-select v-model="sortKey" size="small" style="width:150px">
        <el-option value="default" label="排序:分档" />
        <el-option value="cost" label="排序:成本↓" />
        <el-option value="calls" label="排序:调用数↓" />
      </el-select>
      <span class="muted" style="margin-left:auto">
        筛选出 {{ filtered.length }} 项 · 近{{ data?.days ?? days }}天调用 {{ subtotal.calls }} 次 · 估算 ¥{{ subtotal.cost.toFixed(4) }}
      </span>
    </div>

    <el-table :data="paged" size="small" border style="width:100%">
      <el-table-column label="用途" min-width="200">
        <template #default="{ row }">
          <div class="purpose">{{ row.purpose }}</div>
          <div class="feat"><code>{{ row.feature || '(无 feature 标签)' }}</code></div>
        </template>
      </el-table-column>
      <el-table-column label="端 · 模块" width="150">
        <template #default="{ row }">
          <el-tag :type="row.surface === '小程序端' ? 'success' : 'warning'" effect="plain" size="small">{{ row.surface }}</el-tag>
          <div class="mod">{{ row.module }}</div>
        </template>
      </el-table-column>
      <el-table-column label="分档" width="96" align="center">
        <template #default="{ row }">
          <el-tag :type="row.mode === 'reasoning' ? 'danger' : 'info'" effect="plain" size="small">
            {{ row.mode === 'reasoning' ? '深度思考' : '对话' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="原因(为何需要该档)" min-width="240">
        <template #default="{ row }">{{ row.why }}</template>
      </el-table-column>
      <el-table-column label="模型" width="150">
        <template #default="{ row }"><span class="mono sm">{{ row.model }}</span></template>
      </el-table-column>
      <el-table-column label="后端位置(service)" min-width="200">
        <template #default="{ row }">
          <div v-for="l in row.locations" :key="l" class="mono sm loc">{{ l }}</div>
        </template>
      </el-table-column>
      <el-table-column label="近N天用量" width="150" align="right">
        <template #default="{ row }">
          <template v-if="row.tagged">
            <div>{{ row.calls ?? 0 }} 次</div>
            <div class="muted sm">↓{{ fmtTok(row.prompt_tokens) }} ↑{{ fmtTok(row.completion_tokens) }}</div>
            <div class="cost">¥{{ (row.est_cost ?? 0).toFixed(4) }}</div>
          </template>
          <el-tooltip v-else content="未打 feature 标签,无法单独统计用量" placement="top">
            <span class="muted">未计量</span>
          </el-tooltip>
        </template>
      </el-table-column>
    </el-table>

    <div class="pager">
      <el-pagination background layout="total, sizes, prev, pager, next, jumper"
        :total="filtered.length" :current-page="page" :page-size="pageSize"
        :page-sizes="[20, 50, 100]" @current-change="(p: number) => page = p"
        @size-change="(s: number) => { pageSize = s; page = 1 }" />
    </div>
  </div>
</template>

<style scoped>
.toolbar { display:flex; align-items:center; gap:14px; margin-bottom:16px; flex-wrap:wrap; }
.hint { color:#909399; font-size:12px; max-width:720px; }
.muted { color:#909399; font-size:12px; }
.sm { font-size:12px; }
.mono { font-family:monospace; }
.stat-row { display:flex; gap:12px; margin-bottom:12px; flex-wrap:wrap; }
.stat { flex:1; min-width:140px; text-align:center; }
.stat .sv { font-size:26px; font-weight:700; color:#303133; }
.stat .sl { font-size:12px; color:#909399; margin-top:4px; }
.stat.r .sv { color:#f56c6c; }
.stat.c .sv { color:#409eff; }
.stat.w .sv { color:#e6a23c; }
.models { display:flex; gap:24px; flex-wrap:wrap; color:#606266; font-size:12px; margin-bottom:14px; }
.models .mono { color:#303133; }
.filters { display:flex; gap:12px; align-items:center; margin-bottom:12px; flex-wrap:wrap; }
.purpose { color:#303133; font-weight:500; }
.mod { margin-top:4px; color:#606266; font-size:12px; }
.feat { margin-top:2px; }
.feat code, .filters code, .hint code, .models code { background:#f4f4f5; padding:1px 5px; border-radius:3px; font-size:12px; color:#606266; }
.loc { color:#909399; }
.cost { color:#e6a23c; font-weight:600; }
.pager { margin-top:14px; display:flex; justify-content:flex-end; }
</style>
