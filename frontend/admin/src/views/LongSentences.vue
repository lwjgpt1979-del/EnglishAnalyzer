<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  extractLongSentences, reanalyzeLongSentences, getLsReanalyzeJob, listLongSentences, reviewLongSentence, getLSConfig, setLSConfig,
} from '../api/admin'
import type { LSAdminItem, LSConfig } from '../types'
import { Refresh, Loading } from '@element-plus/icons-vue'

// ── 抽取触发 ──
const sourceOptions = [
  { label: '按配置(sources)', value: 'config' },
  { label: '全部(真题+教材)', value: 'all' },
  { label: '① 平台真题', value: 'platform_real' },
  { label: '② 教材单元短文', value: 'textbook' },
]
const extractSource = ref('config')
const extractLimit = ref(200)
const extracting = ref(false)

async function onExtract() {
  extracting.value = true
  try {
    const r = await extractLongSentences({ source: extractSource.value, limit: extractLimit.value })
    ElMessage.success(`抽取完成:新建 ${r.created} / 长句 ${r.long_kept} / 挂边 ${r.edges} / `
      + `候选 ${r.candidates} / 跳过 ${r.skipped_done}`)
    await load()
  } catch (e: any) { ElMessage.error(e?.message || '抽取失败') }
  finally { extracting.value = false }
}

// ── 重新解析(刷新为新结构:分段/结构/成分/词汇/语法点,供小程序展示)──
const reanalyzing = ref(false)
const reJob = ref<{ done: number; total: number } | null>(null)
async function onReanalyze(publish: boolean) {
  try {
    await ElMessageBox.confirm(
      `重新解析「${status.value}」状态的长难句,刷新为新结构${publish ? ',并发布' : ''}?(后台跑,可继续操作)`,
      '重新解析', { type: 'warning' })
  } catch { return }
  reanalyzing.value = true; reJob.value = { done: 0, total: 0 }
  try {
    const { job_id } = await reanalyzeLongSentences({ status: status.value, limit: 500, publish })
    const poll = async () => {
      try {
        const j = await getLsReanalyzeJob(job_id)
        reJob.value = { done: j.done, total: j.total }
        if (j.status === 'done') {
          ElMessage.success(`重新解析完成:${j.done} 条${j.failed ? `(${j.failed} 失败)` : ''}`)
          reanalyzing.value = false; reJob.value = null; await load(); return
        }
        if (j.status === 'error') { ElMessage.error('重新解析失败:' + (j.error || '')); reanalyzing.value = false; return }
        setTimeout(poll, 2000)
      } catch { reanalyzing.value = false }
    }
    setTimeout(poll, 1500)
  } catch (e: any) { ElMessage.error(e?.message || '启动失败'); reanalyzing.value = false }
}

// ── 审核队列 ──
const status = ref('draft')
const nodeId = ref('')
const rows = ref<LSAdminItem[]>([])
const total = ref(0)
const loading = ref(false)
const sortBy = ref('created_at')   // created_at | difficulty
const order = ref('asc')           // asc | desc
const statusOptions = ['draft', 'published', 'retired']
const stLabel = (s: string) => (({ draft: '草稿', published: '已发布', retired: '已下架' } as Record<string, string>)[s] || s)

async function load() {
  loading.value = true
  try {
    const data = await listLongSentences({
      status: status.value || undefined,
      node_id: nodeId.value.trim() || undefined,
      limit: 50,
      sort_by: sortBy.value,
      order: order.value,
    })
    rows.value = data.items
    total.value = data.total
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}

// el-table 列表头排序:难度 升/降;取消则回到按时间升序
function onSortChange({ prop, order: ord }: { prop: string; order: string | null }) {
  if (!ord) { sortBy.value = 'created_at'; order.value = 'asc' }
  else { sortBy.value = prop; order.value = ord === 'ascending' ? 'asc' : 'desc' }
  load()
}

async function onReview(row: LSAdminItem, approve: boolean) {
  await ElMessageBox.confirm(`确认${approve ? '通过发布' : '退回下架'}该长难句？`, '确认', { type: 'warning' })
  await reviewLongSentence(row.id, approve)
  ElMessage.success(approve ? '已发布' : '已退回')
  await load()
}

// ── 配置 ──
const cfg = ref<LSConfig>({ sources: [], verify_types: [], min_words: 20, required_pass: 3 })
const allSources = ['platform_real', 'textbook', 'uploaded']
const allVerifyTypes = ['cloze', 'struct_type', 'main_clause', 'translate',
  'span_label', 'reorder', 'rewrite', 'read_aloud']
const savingCfg = ref(false)

async function loadCfg() {
  try { cfg.value = await getLSConfig() } catch (e: any) { ElMessage.error(e?.message || '配置加载失败') }
}

async function saveCfg() {
  savingCfg.value = true
  try {
    cfg.value = await setLSConfig({
      sources: cfg.value.sources,
      verify_types: cfg.value.verify_types,
      min_words: cfg.value.min_words,
      required_pass: cfg.value.required_pass,
    })
    ElMessage.success('配置已保存')
  } catch (e: any) { ElMessage.error(e?.message || '保存失败') }
  finally { savingCfg.value = false }
}

onMounted(() => { load(); loadCfg() })
</script>

<template>
  <div>
    <!-- 抽取触发 -->
    <el-card shadow="never" class="sec">
      <template #header><b>抽取触发</b>(独立后台任务,幂等;来源指针:真题/教材语料 Passage/学生上传题)</template>
      <div class="toolbar">
        <span>来源：</span>
        <el-select v-model="extractSource" style="width: 160px">
          <el-option v-for="s in sourceOptions" :key="s.value" :label="s.label" :value="s.value" />
        </el-select>
        <span style="margin-left: 16px">limit：</span>
        <el-input-number v-model="extractLimit" :min="1" :max="2000" style="width: 130px" />
        <el-button style="margin-left: 12px" type="primary" :loading="extracting" @click="onExtract">
          开始抽取
        </el-button>
      </div>
    </el-card>

    <!-- 审核队列 -->
    <el-card shadow="never" class="sec">
      <template #header><b>审核队列</b></template>
      <div class="toolbar">
        <span>状态：</span>
        <el-select v-model="status" style="width: 130px" @change="load">
          <el-option v-for="s in statusOptions" :key="s" :label="stLabel(s)" :value="s" />
        </el-select>
        <span style="margin-left: 16px">句法 node_id：</span>
        <el-input v-model="nodeId" placeholder="可选,knowledge_nodes.id" style="width: 280px" />
        <el-button style="margin-left: 12px" @click="load">查询</el-button>
        <span class="hint">共 {{ total }} 条</span>
        <div style="flex:1" />
        <el-button :loading="reanalyzing" @click="onReanalyze(false)"><el-icon style="vertical-align:-2px;margin-right:4px"><Refresh /></el-icon>重新解析(刷新结构)</el-button>
        <el-button type="success" :loading="reanalyzing" @click="onReanalyze(true)">重解析并发布</el-button>
        <span v-if="reJob" class="hint"><el-icon style="vertical-align:-2px;margin-right:4px"><Loading /></el-icon>{{ reJob.done }}/{{ reJob.total || '…' }}</span>
      </div>
      <el-table v-loading="loading" :data="rows" border style="width: 100%" @sort-change="onSortChange">
        <el-table-column prop="text" label="句子" min-width="320" show-overflow-tooltip />
        <el-table-column prop="source_kind" label="来源" width="120" />
        <el-table-column label="句法点" min-width="160">
          <template #default="{ row }">
            <el-tag v-for="p in row.syntax_points" :key="p" size="small" style="margin-right:4px">{{ p }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="difficulty" label="难度" width="110" sortable="custom"
                         :sort-orders="['descending', 'ascending']">
          <template #default="{ row }">
            <el-tag v-if="row.difficulty != null" size="small"
                    :type="row.difficulty >= 80 ? 'danger' : row.difficulty >= 60 ? 'warning' : 'success'"
                    effect="light">{{ row.difficulty }}</el-tag>
            <span v-else style="color:#bbb">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="90" />
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status !== 'published'" size="small" type="success"
                       @click="onReview(row, true)">发布</el-button>
            <el-button v-if="row.status !== 'retired'" size="small" type="danger"
                       @click="onReview(row, false)">退回</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 配置 -->
    <el-card shadow="never" class="sec">
      <template #header><b>配置</b>(long_sentence.*)</template>
      <el-form label-width="120px" style="max-width: 720px">
        <el-form-item label="抽取来源 sources">
          <el-checkbox-group v-model="cfg.sources">
            <el-checkbox v-for="s in allSources" :key="s" :label="s" :value="s">{{ s }}</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="验证题型 verify_types">
          <el-checkbox-group v-model="cfg.verify_types">
            <el-checkbox v-for="t in allVerifyTypes" :key="t" :label="t" :value="t">{{ t }}</el-checkbox>
          </el-checkbox-group>
          <span class="hint">reorder 暂未实现,即使开放学生端也不返回</span>
        </el-form-item>
        <el-form-item label="长句最小词数">
          <el-input-number v-model="cfg.min_words" :min="5" :max="60" />
        </el-form-item>
        <el-form-item label="判掌握净做对数">
          <el-input-number v-model="cfg.required_pass" :min="1" :max="10" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="savingCfg" @click="saveCfg">保存配置</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.sec { margin-bottom: 16px; }
.toolbar { display: flex; align-items: center; flex-wrap: wrap; }
.hint { margin-left: 16px; color: #909399; font-size: 12px; }
</style>
