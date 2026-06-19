<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listKnowledgeNodes, getKnowledgeNode, updateKnowledgeNode,
  retireKnowledgeNode, restoreKnowledgeNode,
} from '../api/admin'
import type { KpNodeOverviewItem, KpNodeDetail } from '../types'

const router = useRouter()
const DIMS = ['listening', 'vocabulary', 'grammar', 'reading', 'translation', 'writing']
const DIM_LABEL: Record<string, string> = {
  listening: '听力', vocabulary: '词汇', grammar: '语法', reading: '阅读', translation: '翻译', writing: '写作' }
const STAGE_OPTS = ['小', '初', '高']

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

// ── 节点详情 + 维护(D2)──
const detailOpen = ref(false)
const detailLoading = ref(false)
const detailBusy = ref(false)
const detail = ref<KpNodeDetail | null>(null)
const edit = ref({ name: '', node_kind: '', applicable_stages: [] as string[], description: '' })

async function openDetail(id: string) {
  detailOpen.value = true
  detailLoading.value = true
  detail.value = null
  try {
    const d = await getKnowledgeNode(id)
    detail.value = d
    edit.value = { name: d.name, node_kind: d.node_kind || '',
                   applicable_stages: d.applicable_stages || [], description: d.description || '' }
  } catch (e: any) { ElMessage.error(e?.message || '加载详情失败') }
  finally { detailLoading.value = false }
}
function dimClass(cell: { status: string } | null): string {
  if (!cell) return 'cell-missing'
  return cell.status === 'published' ? 'cell-pub' : 'cell-draft'
}
async function saveEdit() {
  if (!detail.value) return
  if (!edit.value.name.trim()) { ElMessage.warning('名称不能为空'); return }
  detailBusy.value = true
  try {
    detail.value = await updateKnowledgeNode(detail.value.id, {
      name: edit.value.name.trim(), node_kind: edit.value.node_kind || null,
      applicable_stages: edit.value.applicable_stages, description: edit.value.description || null })
    ElMessage.success('已保存')
    await load()
  } catch (e: any) { ElMessage.error(e?.message || '保存失败') }
  finally { detailBusy.value = false }
}
async function toggleStatus() {
  if (!detail.value) return
  const retire = detail.value.status === 'active'
  await ElMessageBox.confirm(
    retire ? '停用该节点?学生/真题引用保留,学生不再新挂该点,可随时恢复。' : '恢复为启用?',
    retire ? '停用' : '恢复', { type: 'warning' })
  detailBusy.value = true
  try {
    const r = retire ? await retireKnowledgeNode(detail.value.id) : await restoreKnowledgeNode(detail.value.id)
    detail.value.status = r.status
    ElMessage.success(retire ? '已停用' : '已恢复')
    await load()
  } catch (e: any) { ElMessage.error(e?.message || '操作失败') }
  finally { detailBusy.value = false }
}
function goSupplement() {
  const u = detail.value?.units[0]
  if (u) router.push({ path: '/node-resources', query: { unit_id: u.unit_id } })
  else ElMessage.info('该节点暂未挂到任何单元,无法定位补全页')
}

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
      <el-table-column prop="name" label="知识点" min-width="220" show-overflow-tooltip>
        <template #default="{ row }">
          <el-link type="primary" @click="openDetail(row.id)">{{ row.name }}</el-link>
        </template>
      </el-table-column>
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

    <!-- 节点详情 + 维护抽屉 -->
    <el-drawer v-model="detailOpen" :title="detail ? detail.name : '节点详情'" size="50%" direction="rtl">
      <div v-loading="detailLoading">
        <template v-if="detail">
          <div class="d-head">
            <el-tag size="small" :type="detail.status === 'active' ? 'success' : 'info'">
              {{ detail.status === 'active' ? '启用' : (detail.status === 'retired' ? '停用' : detail.status) }}
            </el-tag>
            <span class="d-code">{{ detail.code }}</span>
            <span class="d-src">来源 {{ detail.source }}</span>
            <el-button size="small" style="margin-left:auto"
              :type="detail.status === 'active' ? 'danger' : 'success'" plain
              :loading="detailBusy" @click="toggleStatus">
              {{ detail.status === 'active' ? '停用' : '恢复' }}
            </el-button>
          </div>

          <el-form label-width="76px" class="d-form">
            <el-form-item label="名称"><el-input v-model="edit.name" /></el-form-item>
            <el-form-item label="轴"><span>{{ detail.axis }}(不可改)</span></el-form-item>
            <el-form-item label="子类型"><el-input v-model="edit.node_kind" placeholder="如 句法/词汇/题型" /></el-form-item>
            <el-form-item label="适用学段">
              <el-checkbox-group v-model="edit.applicable_stages">
                <el-checkbox v-for="s in STAGE_OPTS" :key="s" :value="s">{{ s }}</el-checkbox>
              </el-checkbox-group>
            </el-form-item>
            <el-form-item label="描述"><el-input v-model="edit.description" type="textarea" :rows="2" /></el-form-item>
            <el-form-item><el-button type="primary" :loading="detailBusy" @click="saveEdit">保存修改</el-button></el-form-item>
          </el-form>

          <el-divider content-position="left">六维讲解完整度</el-divider>
          <div class="d-dims">
            <span v-for="d in DIMS" :key="d" :class="['cell', dimClass(detail.dims[d])]">
              {{ DIM_LABEL[d] }}：{{ detail.dims[d] ? (detail.dims[d]!.status === 'published' ? '已发布' : '草稿') : '缺' }}
            </span>
            <el-button size="small" type="warning" plain style="margin-left:8px" @click="goSupplement">📝 去补全</el-button>
          </div>

          <el-divider content-position="left">学生掌握分布</el-divider>
          <div class="d-mastery">
            <span>学习人数 <b>{{ detail.mastery.learners }}</b></span>
            <span v-if="detail.mastery.avg != null">平均掌握 <b>{{ (detail.mastery.avg * 100).toFixed(0) }}%</b></span>
            <el-tag type="success" effect="plain">掌握 {{ detail.mastery.mastered }}</el-tag>
            <el-tag type="warning" effect="plain">一般 {{ detail.mastery.mid }}</el-tag>
            <el-tag type="danger" effect="plain">薄弱 {{ detail.mastery.weak }}</el-tag>
            <span v-if="!detail.mastery.learners" class="muted">暂无学生学习数据</span>
          </div>

          <el-divider content-position="left">引用</el-divider>
          <div class="d-refs">
            <el-tag type="danger" effect="plain">真题 {{ detail.question_real }}</el-tag>
            <el-tag type="info" effect="plain">仿真 {{ detail.question_sim }}</el-tag>
            <span class="muted" style="margin-left:8px">别名 {{ detail.aliases.length }}</span>
          </div>
          <div class="d-units">
            <div class="sub">被以下单元引用({{ detail.units.length }}):</div>
            <el-empty v-if="!detail.units.length" description="未挂到任何单元" :image-size="48" />
            <ul v-else>
              <li v-for="u in detail.units" :key="u.unit_id">
                {{ u.textbook_version }} · {{ u.grade }}{{ u.semester }} · {{ u.unit_title }}
              </li>
            </ul>
          </div>
          <div class="d-aliases" v-if="detail.aliases.length">
            <div class="sub">别名:</div>
            <el-tag v-for="a in detail.aliases" :key="a.alias" size="small" effect="plain" style="margin:2px">{{ a.alias }}</el-tag>
          </div>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.toolbar { margin-bottom: 16px; display: flex; align-items: center; flex-wrap: wrap; }
.hint { margin-left: 16px; color: #909399; font-size: 12px; }
.pager { margin-top: 16px; display: flex; justify-content: flex-end; }
.muted { color: #c0c4cc; font-size: 12px; }
.d-head { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
.d-code { font-family: monospace; font-size: 12px; color: #909399; }
.d-src { font-size: 12px; color: #909399; }
.d-form { max-width: 520px; }
.d-dims { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.d-dims .cell { padding: 3px 10px; border-radius: 4px; font-size: 12px; }
.cell-pub { background: #f0f9eb; color: #67c23a; }
.cell-draft { background: #fdf6ec; color: #e6a23c; }
.cell-missing { background: #fef0f0; color: #f56c6c; border: 1px dashed #fbc4c4; }
.d-mastery { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; font-size: 13px; }
.d-refs { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.d-units .sub, .d-aliases .sub { font-size: 13px; color: #606266; margin: 8px 0 4px; }
.d-units ul { margin: 0; padding-left: 18px; font-size: 13px; color: #303133; }
.d-units li { margin: 3px 0; }
</style>
