<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listKnowledgeNodes } from '../api/admin'
import type { KpNodeOverviewItem } from '../types'

const AXES = [
  { label: '全部轴', value: '' }, { label: '知识', value: 'knowledge' },
  { label: '能力', value: 'ability' }, { label: '考点', value: 'exam' },
]
const AXIS_LABEL: Record<string, string> = { knowledge: '知识', ability: '能力', exam: '考点' }
const STAGES = [{ label: '全部学段', value: '' }, { label: '小', value: '小' }, { label: '初', value: '初' }, { label: '高', value: '高' }]
const STATUSES = [
  { label: '启用', value: 'active' }, { label: '候选', value: 'candidate' },
  { label: '停用', value: 'retired' }, { label: '全部', value: '' },
]
const STATUS_TAG: Record<string, string> = { active: 'success', candidate: 'warning', retired: 'info' }
const STATUS_LABEL: Record<string, string> = { active: '启用', candidate: '候选', retired: '停用' }

const axis = ref('')
const stage = ref('')
const status = ref('active')
const q = ref('')
const rows = ref<KpNodeOverviewItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 30
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const data = await listKnowledgeNodes({
      axis: axis.value || undefined, stage: stage.value || undefined,
      status: status.value || undefined, q: q.value || undefined,
      skip: (page.value - 1) * pageSize, limit: pageSize,
    })
    rows.value = data.items
    total.value = data.total
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}
function reload() { page.value = 1; load() }

onMounted(load)
</script>

<template>
  <div>
    <div class="toolbar">
      <span>轴：</span>
      <el-select v-model="axis" style="width:110px" @change="reload">
        <el-option v-for="a in AXES" :key="a.value" :label="a.label" :value="a.value" />
      </el-select>
      <span style="margin-left:12px">学段：</span>
      <el-select v-model="stage" style="width:110px" @change="reload">
        <el-option v-for="s in STAGES" :key="s.value" :label="s.label" :value="s.value" />
      </el-select>
      <span style="margin-left:12px">状态：</span>
      <el-select v-model="status" style="width:100px" @change="reload">
        <el-option v-for="s in STATUSES" :key="s.value" :label="s.label" :value="s.value" />
      </el-select>
      <el-input v-model="q" placeholder="搜知识点名" clearable style="width:200px;margin-left:12px"
        @keyup.enter="reload" @clear="reload" />
      <el-button type="primary" style="margin-left:8px" @click="reload">查询</el-button>
      <span class="hint">知识点骨架(knowledge_nodes)总览。共 {{ total }} 个节点。完整度=六维讲解已配几维。</span>
    </div>

    <el-table v-loading="loading" :data="rows" border style="width:100%">
      <el-table-column prop="name" label="知识点" min-width="220" show-overflow-tooltip />
      <el-table-column label="轴" width="80" align="center">
        <template #default="{ row }">{{ AXIS_LABEL[row.axis] || row.axis }}</template>
      </el-table-column>
      <el-table-column prop="node_kind" label="子类型" width="100">
        <template #default="{ row }">{{ row.node_kind || '—' }}</template>
      </el-table-column>
      <el-table-column label="学段" width="110">
        <template #default="{ row }">{{ (row.applicable_stages || []).join('/') || '通用' }}</template>
      </el-table-column>
      <el-table-column label="状态" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="STATUS_TAG[row.status] || 'info'" size="small">{{ STATUS_LABEL[row.status] || row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="六维完整度" width="150">
        <template #default="{ row }">
          <el-progress :percentage="Math.round(row.dims_filled / 6 * 100)" :stroke-width="14"
            :status="row.dims_filled === 6 ? 'success' : (row.dims_filled === 0 ? 'exception' : undefined)"
            :format="() => `${row.dims_filled}/6`" />
        </template>
      </el-table-column>
      <el-table-column prop="unit_refs" label="引用单元" width="90" align="center" />
      <el-table-column prop="question_refs" label="引用真题" width="90" align="center" />
      <el-table-column prop="alias_count" label="别名" width="70" align="center" />
      <el-table-column prop="code" label="编码" min-width="140" show-overflow-tooltip />
    </el-table>

    <div class="pager">
      <el-pagination layout="total, prev, pager, next" :total="total" :page-size="pageSize"
        v-model:current-page="page" @current-change="load" />
    </div>
  </div>
</template>

<style scoped>
.toolbar { margin-bottom: 16px; display: flex; align-items: center; flex-wrap: wrap; }
.hint { margin-left: 16px; color: #909399; font-size: 12px; }
.pager { margin-top: 16px; display: flex; justify-content: flex-end; }
</style>
