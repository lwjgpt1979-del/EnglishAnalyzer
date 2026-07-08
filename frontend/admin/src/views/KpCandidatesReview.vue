<script setup lang="ts">
import AppDialog from '../components/AppDialog.vue'
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listKpCandidates,
  listKpNodes,
  approveKpCandidate,
  mergeKpCandidate,
  rejectKpCandidate,
  getNodeTree,
} from '../api/admin'
import type { KpCandidateItem, KpCandidateStatus, KpNodeItem, NodeTreeItem } from '../types'

const status = ref<KpCandidateStatus>('pending')
const axis = ref<string>('')
const rows = ref<KpCandidateItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 50
const loading = ref(false)

const statusOptions: KpCandidateStatus[] = ['pending', 'approved', 'merged', 'rejected']
const axisOptions = [
  { label: '全部轴', value: '' },
  { label: '知识', value: 'knowledge' },
  { label: '能力', value: 'ability' },
  { label: '考试', value: 'exam' },
]
const stageOptions = ['小', '初', '高']

async function load() {
  loading.value = true
  try {
    const data = await listKpCandidates({
      status: status.value,
      axis: axis.value || undefined,
      skip: (page.value - 1) * pageSize,
      limit: pageSize,
    })
    rows.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function onFilterChange() {
  page.value = 1
  load()
}

// ── 通过（建节点）──────────────────────────────────────────
const approveDlg = ref(false)
const approving = ref<KpCandidateItem | null>(null)
const approveForm = ref({ axis: 'knowledge', stage: '' as string, node_kind: '',
                          parent_id: '' as string, asTop: false })
const parentTree = ref<NodeTreeItem[]>([])
const parentTreeProps = { label: 'name', children: 'children', value: 'id' }

async function loadParentTree() {
  try { parentTree.value = (await getNodeTree(approveForm.value.axis)).items }
  catch { parentTree.value = [] }
}
async function onApproveAxisChange() {
  approveForm.value.parent_id = ''      // 换轴 → 清上级,重载该轴树
  await loadParentTree()
}
async function openApprove(row: KpCandidateItem) {
  approving.value = row
  approveForm.value = {
    axis: row.suggested_axis || 'knowledge',
    stage: row.suggested_stage || '',
    node_kind: '', parent_id: '', asTop: false,
  }
  approveDlg.value = true
  await loadParentTree()
}

async function confirmApprove() {
  if (!approving.value) return
  // E3:强制做放置决策——选上级分类,或显式勾选"作为顶层"
  if (!approveForm.value.asTop && !approveForm.value.parent_id) {
    ElMessage.warning('请选择挂到的上级分类,或勾选"作为顶层节点"')
    return
  }
  await approveKpCandidate(approving.value.id, {
    axis: approveForm.value.axis,
    stage: approveForm.value.stage || null,
    node_kind: approveForm.value.node_kind || null,
    parent_id: approveForm.value.asTop ? null : (approveForm.value.parent_id || null),
  })
  ElMessage.success('已通过并挂到知识树')
  approveDlg.value = false
  await load()
}

// ── 归并（作为已有节点别名）────────────────────────────────
const mergeDlg = ref(false)
const merging = ref<KpCandidateItem | null>(null)
const mergeTarget = ref<string>('')
const nodeOptions = ref<KpNodeItem[]>([])
const nodeLoading = ref(false)

function openMerge(row: KpCandidateItem) {
  merging.value = row
  mergeTarget.value = ''
  nodeOptions.value = []
  mergeDlg.value = true
}

async function searchNodes(q: string) {
  nodeLoading.value = true
  try {
    const data = await listKpNodes({
      q: q || undefined,
      axis: merging.value?.suggested_axis || undefined,
      limit: 20,
    })
    nodeOptions.value = data.items
  } finally {
    nodeLoading.value = false
  }
}

async function confirmMerge() {
  if (!merging.value || !mergeTarget.value) {
    ElMessage.warning('请选择归并目标节点')
    return
  }
  await mergeKpCandidate(merging.value.id, mergeTarget.value)
  ElMessage.success('已归并为目标节点的别名')
  mergeDlg.value = false
  await load()
}

// ── 驳回 ───────────────────────────────────────────────────
async function onReject(row: KpCandidateItem) {
  const { value } = await ElMessageBox.prompt('请输入驳回理由', '驳回候选', {
    inputValidator: (v) => (v && v.trim() ? true : '理由必填'),
  })
  await rejectKpCandidate(row.id, value.trim())
  ElMessage.success('已驳回')
  await load()
}

onMounted(load)
</script>

<template>
  <div>
    <div class="toolbar">
      <span>状态：</span>
      <el-select v-model="status" style="width: 130px" @change="onFilterChange">
        <el-option v-for="s in statusOptions" :key="s" :label="s" :value="s" />
      </el-select>
      <span style="margin-left: 16px">轴：</span>
      <el-select v-model="axis" style="width: 130px" @change="onFilterChange">
        <el-option v-for="a in axisOptions" :key="a.value" :label="a.label" :value="a.value" />
      </el-select>
      <el-button style="margin-left: 12px" @click="load">刷新</el-button>
      <span class="hint">候选 = 受控匹配未命中的写法；通过=建标准节点，归并=并入已有节点的别名（治碎片化）</span>
    </div>

    <el-table v-loading="loading" :data="rows" border style="width: 100%">
      <el-table-column prop="raw_name" label="候选名" min-width="180" show-overflow-tooltip />
      <el-table-column prop="occur_count" label="出现次数" width="90" sortable />
      <el-table-column prop="suggested_axis" label="建议轴" width="90" />
      <el-table-column prop="suggested_stage" label="建议学段" width="90" />
      <el-table-column prop="source_type" label="来源" width="120" show-overflow-tooltip />
      <el-table-column prop="status" label="状态" width="90" />
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <template v-if="row.status === 'pending'">
            <el-button size="small" type="success" @click="openApprove(row)">通过</el-button>
            <el-button size="small" type="primary" @click="openMerge(row)">归并</el-button>
            <el-button size="small" type="danger" @click="onReject(row)">驳回</el-button>
          </template>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      style="margin-top: 16px; justify-content: flex-end"
      layout="total, prev, pager, next"
      :total="total" :page-size="pageSize" :current-page="page"
      @current-change="(p: number) => { page = p; load() }"
    />

    <!-- 通过：建节点 -->
    <AppDialog v-model="approveDlg" title="通过 → 建立标准节点" width="420px">
      <p v-if="approving" class="dlg-name">{{ approving.raw_name }}</p>
      <el-form label-width="72px">
        <el-form-item label="轴">
          <el-select v-model="approveForm.axis" style="width: 100%" @change="onApproveAxisChange">
            <el-option v-for="a in axisOptions.filter((x) => x.value)" :key="a.value" :label="a.label" :value="a.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="上级分类" required>
          <el-tree-select v-model="approveForm.parent_id" :data="parentTree" :props="parentTreeProps"
            check-strictly node-key="id" :disabled="approveForm.asTop" filterable
            placeholder="挂到知识树哪个分类下" style="width: 100%" />
          <el-checkbox v-model="approveForm.asTop" style="margin-top:6px">作为顶层节点(无上级)</el-checkbox>
        </el-form-item>
        <el-form-item label="学段">
          <el-select v-model="approveForm.stage" clearable placeholder="空=全学段通用" style="width: 100%">
            <el-option v-for="s in stageOptions" :key="s" :label="s" :value="s" />
          </el-select>
        </el-form-item>
        <el-form-item label="子类型">
          <el-input v-model="approveForm.node_kind" placeholder="如 句法/词汇（可空）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="approveDlg = false">取消</el-button>
        <el-button type="success" @click="confirmApprove">确认通过</el-button>
      </template>
    </AppDialog>

    <!-- 归并：选目标节点 -->
    <AppDialog v-model="mergeDlg" title="归并 → 作为已有节点的别名" width="480px">
      <p v-if="merging" class="dlg-name">{{ merging.raw_name }}</p>
      <el-select
        v-model="mergeTarget"
        filterable
        remote
        reserve-keyword
        placeholder="搜索目标节点名称"
        :remote-method="searchNodes"
        :loading="nodeLoading"
        style="width: 100%"
        @focus="searchNodes('')"
      >
        <el-option
          v-for="n in nodeOptions"
          :key="n.id"
          :label="`${n.name}（${n.axis}${n.node_kind ? '/' + n.node_kind : ''}）`"
          :value="n.id"
        />
      </el-select>
      <template #footer>
        <el-button @click="mergeDlg = false">取消</el-button>
        <el-button type="primary" @click="confirmMerge">确认归并</el-button>
      </template>
    </AppDialog>
  </div>
</template>

<style scoped>
.toolbar { margin-bottom: 16px; display: flex; align-items: center; flex-wrap: wrap; }
.hint { margin-left: 16px; color: #909399; font-size: 12px; }
.muted { color: #c0c4cc; }
.dlg-name { font-weight: 600; margin: 0 0 12px; }
</style>
