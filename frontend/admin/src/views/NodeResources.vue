<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listNodeResources, addNodeResource, updateNodeResource, reviewNodeResource,
  listCurriculumUnits, unitContentOverview, publishUnit,
  versionDiff, approveVersion, rejectVersion,
} from '../api/admin'
import type { NodeResourceItem2, AdminCurriculumUnit, UnitContentNode, VersionDiffOut } from '../types'
import { lineDiff, type DiffLine } from '../utils/linediff'

const route = useRoute()

const status = ref('draft')
const typeFilter = ref('')
const rows = ref<NodeResourceItem2[]>([])
const total = ref(0)
const loading = ref(false)

const statusOptions = ['', 'draft', 'reviewing', 'published', 'retired']
const types = [
  { label: '全部类型', value: '' },
  { label: '讲解', value: 'lecture' },
  { label: '视频', value: 'video' },
  { label: '例句库', value: 'example' },
  { label: '写作范文', value: 'essay' },
  { label: '思维导图', value: 'mindmap' },
]
const dimensions = ['listening', 'vocabulary', 'grammar', 'reading', 'translation', 'writing']
const DIM_LABEL: Record<string, string> = {
  listening: '听力', vocabulary: '词汇', grammar: '语法',
  reading: '阅读', translation: '翻译', writing: '写作',
}

// ── 单元级过滤(教材→年级→学期→单元,从课程单元派生)──
const allUnits = ref<AdminCurriculumUnit[]>([])
const fTextbook = ref('')
const fGrade = ref('')
const fSemester = ref('')
const fUnitId = ref('')

const textbooks = computed(() => [...new Set(allUnits.value.map(u => u.textbook_version))])
const grades = computed(() => [...new Set(
  allUnits.value.filter(u => u.textbook_version === fTextbook.value).map(u => u.grade))])
const semesters = computed(() => [...new Set(
  allUnits.value.filter(u => u.textbook_version === fTextbook.value && u.grade === fGrade.value)
    .map(u => u.semester))])
const unitOptions = computed(() => allUnits.value.filter(u =>
  u.textbook_version === fTextbook.value && u.grade === fGrade.value && u.semester === fSemester.value)
  .sort((a, b) => a.unit_no - b.unit_no))

function onTextbookChange() { fGrade.value = ''; fSemester.value = ''; clearUnit() }
function onGradeChange() { fSemester.value = ''; clearUnit() }
function onSemesterChange() { clearUnit() }
function clearUnit() { fUnitId.value = ''; overview.value = []; load() }
function onUnitChange() { load(); loadOverview() }

// ── 补全总览(发布前预览每个知识点六维完整度)──
const overview = ref<UnitContentNode[]>([])
const overviewLoading = ref(false)
const currentUnitTitle = computed(() =>
  allUnits.value.find(u => u.unit_id === fUnitId.value)?.unit_title || '')

async function loadOverview() {
  if (!fUnitId.value) { overview.value = []; return }
  overviewLoading.value = true
  try { overview.value = (await unitContentOverview(fUnitId.value)).items }
  catch (e: any) { ElMessage.error(e?.message || '总览加载失败') }
  finally { overviewLoading.value = false }
}

function cellClass(cell: { status: string } | null): string {
  if (!cell) return 'cell-missing'
  if (cell.status === 'published') return 'cell-pub'
  return 'cell-draft'
}
const missingCount = computed(() =>
  overview.value.reduce((n, node) => n + dimensions.filter(d => !node.dims[d]).length, 0))
const draftCount = computed(() =>
  overview.value.reduce((n, node) =>
    n + dimensions.filter(d => node.dims[d] && node.dims[d]!.status !== 'published').length, 0))

// 一键发布整单元
const publishing = ref(false)
async function onPublishUnit() {
  if (!fUnitId.value) return
  const warn = missingCount.value
    ? `当前还有 ${missingCount.value} 个维度缺讲解(发布后这些维度学生看不到)。仍要发布已就绪的 ${draftCount.value} 条草稿吗？`
    : `确认发布本单元 ${draftCount.value} 条草稿讲解？发布后学生可见。`
  if (!draftCount.value && !missingCount.value) { ElMessage.info('本单元讲解已全部发布'); return }
  await ElMessageBox.confirm(warn, '发布本单元', { type: missingCount.value ? 'warning' : 'info' })
  publishing.value = true
  try {
    const r = await publishUnit(fUnitId.value)
    ElMessage.success(`已发布 ${r.published} 条${r.missing_dims ? `,仍缺 ${r.missing_dims} 维度未补全` : ''}`)
    await load(); await loadOverview()
  } catch (e: any) { ElMessage.error(e?.message || '发布失败') }
  finally { publishing.value = false }
}

async function load() {
  loading.value = true
  try {
    const data = await listNodeResources({
      status: status.value,                       // '' = 全部
      resource_type: typeFilter.value || undefined,
      unit_id: fUnitId.value || undefined,
      limit: 100,
    })
    rows.value = data.items
    total.value = data.total
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}

async function onReview(row: NodeResourceItem2, approve: boolean) {
  await ElMessageBox.confirm(`确认${approve ? '通过发布' : '驳回'}该资源？`, '确认', { type: 'warning' })
  await reviewNodeResource(row.id, approve)
  ElMessage.success(approve ? '已发布' : '已驳回')
  await load()
  await loadOverview()
}

// ── 待审新版对比 + 审核(C2)──
const diffOpen = ref(false)
const diffLoading = ref(false)
const diffBusy = ref(false)
const diffVersionId = ref('')
const diffCtx = ref('')                       // 知识点 · 维度 标题
const diffData = ref<VersionDiffOut | null>(null)
const diffLines = computed<DiffLine[]>(() =>
  diffData.value ? lineDiff(diffData.value.base.content_md, diffData.value.incoming.content_md) : [])

async function openDiff(node: UnitContentNode, dim: string) {
  const vid = node.dims[dim]?.pending_version_id
  if (!vid) return
  diffVersionId.value = vid
  diffCtx.value = `${node.name} · ${DIM_LABEL[dim] || dim}`
  diffOpen.value = true
  diffLoading.value = true
  diffData.value = null
  try { diffData.value = await versionDiff(vid) }
  catch (e: any) { ElMessage.error(e?.message || '加载对比失败') }
  finally { diffLoading.value = false }
}
async function onApproveVersion() {
  diffBusy.value = true
  try {
    await approveVersion(diffVersionId.value)
    ElMessage.success('已通过,新版替换线上')
    diffOpen.value = false
    await load(); await loadOverview()
  } catch (e: any) { ElMessage.error(e?.message || '操作失败') }
  finally { diffBusy.value = false }
}
async function onRejectVersion() {
  diffBusy.value = true
  try {
    await rejectVersion(diffVersionId.value)
    ElMessage.success('已驳回,线上不变')
    diffOpen.value = false
    await load(); await loadOverview()
  } catch (e: any) { ElMessage.error(e?.message || '操作失败') }
  finally { diffBusy.value = false }
}

// ── 新增 / 补全缺失维度 ──
const addDlg = ref(false)
const form = ref({ node_id: '', node_name: '', resource_type: 'lecture', dimension: 'grammar',
                   title: '', content_md: '', media_url: '', status: 'draft' })

function openAdd(prefill?: Partial<typeof form.value>) {
  form.value = { node_id: '', node_name: '', resource_type: 'lecture', dimension: 'grammar',
                 title: '', content_md: '', media_url: '', status: 'draft', ...prefill }
  addDlg.value = true
}
function fillMissing(node: UnitContentNode, dim: string) {
  openAdd({ node_id: node.node_id, node_name: node.name, resource_type: 'lecture', dimension: dim })
}

async function confirmAdd() {
  if (!form.value.node_id.trim()) { ElMessage.warning('请填知识节点 node_id'); return }
  const body: any = {
    node_id: form.value.node_id.trim(), resource_type: form.value.resource_type,
    title: form.value.title || undefined, content_md: form.value.content_md || undefined,
    media_url: form.value.media_url || undefined, status: form.value.status,
  }
  if (form.value.resource_type === 'lecture') body.dimension = form.value.dimension
  try {
    await addNodeResource(body)
    ElMessage.success('已保存')
    addDlg.value = false
    await load()
    await loadOverview()
  } catch (e: any) { ElMessage.error(e?.message || '保存失败') }
}

// ── 编辑已有资源 ──
const editDlg = ref(false)
const editForm = ref<{ id: string; title: string; content_md: string; media_url: string }>(
  { id: '', title: '', content_md: '', media_url: '' })
function openEdit(row: NodeResourceItem2) {
  editForm.value = { id: row.id, title: row.title || '', content_md: row.content_md || '', media_url: row.media_url || '' }
  editDlg.value = true
}
async function confirmEdit() {
  try {
    await updateNodeResource(editForm.value.id, {
      title: editForm.value.title || undefined,
      content_md: editForm.value.content_md || undefined,
      media_url: editForm.value.media_url || undefined,
    })
    ElMessage.success('已保存')
    editDlg.value = false
    await load()
  } catch (e: any) { ElMessage.error(e?.message || '保存失败') }
}

onMounted(async () => {
  try { allUnits.value = await listCurriculumUnits() } catch { /* 忽略 */ }
  // 从单元页跳转携带 unit_id → 预置过滤
  const qUnit = route.query.unit_id as string | undefined
  if (qUnit) {
    const u = allUnits.value.find(x => x.unit_id === qUnit)
    if (u) {
      fTextbook.value = u.textbook_version; fGrade.value = u.grade
      fSemester.value = u.semester; fUnitId.value = u.unit_id
      status.value = ''            // 跳转补全场景:默认看全部状态
      await loadOverview()
    }
  }
  await load()
})
</script>

<template>
  <div>
    <div class="toolbar">
      <span>状态：</span>
      <el-select v-model="status" style="width: 120px" @change="load">
        <el-option v-for="s in statusOptions" :key="s" :label="s || '全部'" :value="s" />
      </el-select>
      <span style="margin-left: 12px">类型：</span>
      <el-select v-model="typeFilter" style="width: 120px" @change="load">
        <el-option v-for="t in types" :key="t.value" :label="t.label" :value="t.value" />
      </el-select>
      <el-divider direction="vertical" />
      <span>教材：</span>
      <el-select v-model="fTextbook" clearable placeholder="全部" style="width: 130px" @change="onTextbookChange">
        <el-option v-for="t in textbooks" :key="t" :label="t" :value="t" />
      </el-select>
      <el-select v-model="fGrade" clearable placeholder="年级" style="width: 100px; margin-left:8px"
        :disabled="!fTextbook" @change="onGradeChange">
        <el-option v-for="g in grades" :key="g" :label="g" :value="g" />
      </el-select>
      <el-select v-model="fSemester" clearable placeholder="学期" style="width: 80px; margin-left:8px"
        :disabled="!fGrade" @change="onSemesterChange">
        <el-option v-for="s in semesters" :key="s" :label="s" :value="s" />
      </el-select>
      <el-select v-model="fUnitId" clearable placeholder="单元" style="width: 200px; margin-left:8px"
        :disabled="!fSemester" @change="onUnitChange">
        <el-option v-for="u in unitOptions" :key="u.unit_id"
          :label="`U${u.unit_no} ${u.unit_title}`" :value="u.unit_id" />
      </el-select>
      <el-button style="margin-left: 12px" type="success" @click="openAdd()">+ 新增资源</el-button>
      <el-button @click="load">刷新</el-button>
    </div>

    <!-- 单元补全总览:每个知识点六维完整度,红=缺(点击补全) 黄=草稿 绿=已发布 -->
    <el-card v-if="fUnitId" class="overview" shadow="never" v-loading="overviewLoading">
      <div class="ov-head">
        <b>📋 {{ currentUnitTitle }} · 补全总览</b>
        <span class="ov-sum">知识点 {{ overview.length }} · 缺失维度
          <b :class="missingCount ? 'warn' : 'ok'">{{ missingCount }}</b>
          <template v-if="!missingCount"> ✓ 全部就绪</template>
          <template v-if="draftCount"> · 待发布草稿 <b class="warn">{{ draftCount }}</b></template>
        </span>
        <el-button v-if="overview.length" size="small" type="success" :loading="publishing"
          :disabled="!draftCount" @click="onPublishUnit">🚀 一键发布本单元</el-button>
        <span class="ov-legend"><i class="dot cell-missing" />缺<i class="dot cell-draft" />草稿<i class="dot cell-pub" />已发布<em style="margin-left:10px">🆕 待审新版(点击对比)</em></span>
      </div>
      <el-empty v-if="!overviewLoading && !overview.length" description="该单元暂无对齐的知识图谱节点(先在单元页「对齐图谱」)" />
      <table v-else class="ov-table">
        <thead>
          <tr><th class="kp">知识点</th><th v-for="d in dimensions" :key="d">{{ DIM_LABEL[d] }}</th></tr>
        </thead>
        <tbody>
          <tr v-for="node in overview" :key="node.node_id">
            <td class="kp" :title="node.name">{{ node.name }}</td>
            <td v-for="d in dimensions" :key="d">
              <span v-if="node.dims[d]"
                :class="['cell', cellClass(node.dims[d]), node.dims[d]!.pending_version_id ? 'clickable' : '']"
                :title="node.dims[d]!.pending_version_id ? '有待审新版,点击对比' : ''"
                @click="node.dims[d]!.pending_version_id && openDiff(node, d)">
                {{ node.dims[d]!.status === 'published' ? '已发布' : '草稿' }}
                <em v-if="node.dims[d]!.pending_version_id" class="newbadge">🆕</em>
              </span>
              <span v-else class="cell cell-missing clickable" @click="fillMissing(node, d)">补全</span>
            </td>
          </tr>
        </tbody>
      </table>
    </el-card>

    <el-table v-loading="loading" :data="rows" border style="width: 100%">
      <el-table-column prop="node_name" label="知识点" min-width="140" show-overflow-tooltip>
        <template #default="{ row }"><span :class="{ muted: !row.node_name }">{{ row.node_name || row.node_id }}</span></template>
      </el-table-column>
      <el-table-column prop="resource_type" label="类型" width="80" />
      <el-table-column label="维度" width="80">
        <template #default="{ row }">{{ row.dimension ? DIM_LABEL[row.dimension] || row.dimension : '—' }}</template>
      </el-table-column>
      <el-table-column prop="title" label="标题" min-width="120" show-overflow-tooltip />
      <el-table-column prop="content_md" label="正文" min-width="180" show-overflow-tooltip />
      <el-table-column prop="status" label="状态" width="80" />
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <template v-if="row.status !== 'published'">
            <el-button size="small" type="success" @click="onReview(row, true)">发布</el-button>
            <el-button size="small" type="danger" @click="onReview(row, false)">驳回</el-button>
          </template>
          <span v-else class="muted">已发布</span>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="addDlg" title="新增 / 补全知识节点资源" width="540px">
      <el-form label-width="90px">
        <el-form-item label="知识点">
          <span v-if="form.node_name" style="font-weight:600">{{ form.node_name }}</span>
          <el-input v-else v-model="form.node_id" placeholder="knowledge_nodes.id" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.resource_type" style="width:100%">
            <el-option v-for="t in types.filter(x=>x.value)" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.resource_type === 'lecture'" label="维度">
          <el-select v-model="form.dimension" style="width:100%">
            <el-option v-for="d in dimensions" :key="d" :label="DIM_LABEL[d]" :value="d" />
          </el-select>
        </el-form-item>
        <el-form-item label="标题"><el-input v-model="form.title" /></el-form-item>
        <el-form-item label="正文"><el-input v-model="form.content_md" type="textarea" :rows="4" /></el-form-item>
        <el-form-item label="媒体URL"><el-input v-model="form.media_url" placeholder="视频/音频/图 直链" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addDlg = false">取消</el-button>
        <el-button type="success" @click="confirmAdd">保存(草稿)</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="editDlg" title="编辑资源" width="540px">
      <el-form label-width="90px">
        <el-form-item label="标题"><el-input v-model="editForm.title" /></el-form-item>
        <el-form-item label="正文"><el-input v-model="editForm.content_md" type="textarea" :rows="5" /></el-form-item>
        <el-form-item label="媒体URL"><el-input v-model="editForm.media_url" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDlg = false">取消</el-button>
        <el-button type="primary" @click="confirmEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 待审新版对比抽屉:左=当前线上,右=新版;通过则替换、驳回则线上不变 -->
    <el-drawer v-model="diffOpen" :title="`对比待审新版 · ${diffCtx}`" size="62%" direction="rtl">
      <div v-loading="diffLoading">
        <div v-if="diffData" class="diff-meta">
          <span class="side base">{{ diffData.base.label }}</span>
          <span class="arrow">→</span>
          <span class="side incoming">{{ diffData.incoming.label }}</span>
          <span style="margin-left:auto;color:#909399;font-size:12px">行级对比:<i class="ln del" />删除 <i class="ln add" />新增</span>
        </div>
        <div class="diff-box">
          <div v-for="(l, i) in diffLines" :key="i" :class="['diff-line', l.type]">
            <span class="gutter">{{ l.type === 'add' ? '+' : l.type === 'del' ? '-' : '' }}</span>
            <span class="txt">{{ l.text || ' ' }}</span>
          </div>
          <el-empty v-if="!diffLoading && !diffLines.length" description="无内容" />
        </div>
      </div>
      <template #footer>
        <el-button @click="diffOpen = false">关闭</el-button>
        <el-button type="danger" plain :loading="diffBusy" @click="onRejectVersion">驳回</el-button>
        <el-button type="success" :loading="diffBusy" @click="onApproveVersion">通过 · 替换线上</el-button>
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>
.toolbar { margin-bottom: 16px; display: flex; align-items: center; flex-wrap: wrap; gap: 4px 0; }
.muted { color: #c0c4cc; }
.overview { margin-bottom: 16px; }
.ov-head { display: flex; align-items: center; gap: 18px; margin-bottom: 10px; flex-wrap: wrap; }
.ov-sum { color: #606266; font-size: 13px; }
.ov-sum .warn { color: #e6a23c; } .ov-sum .ok { color: #67c23a; }
.ov-legend { margin-left: auto; color: #909399; font-size: 12px; display: flex; align-items: center; gap: 4px; }
.ov-legend .dot { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-left: 10px; }
.ov-table { border-collapse: collapse; width: 100%; font-size: 13px; }
.ov-table th, .ov-table td { border: 1px solid #ebeef5; padding: 6px 8px; text-align: center; }
.ov-table th { background: #fafafa; color: #606266; font-weight: 500; }
.ov-table .kp { text-align: left; max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cell { display: inline-block; min-width: 44px; padding: 2px 6px; border-radius: 4px; font-size: 12px; }
.cell-pub { background: #f0f9eb; color: #67c23a; }
.cell-draft { background: #fdf6ec; color: #e6a23c; }
.cell-missing { background: #fef0f0; color: #f56c6c; border: 1px dashed #fbc4c4; }
.clickable { cursor: pointer; }
.cell-missing.clickable:hover { background: #f56c6c; color: #fff; }
.newbadge { font-style: normal; margin-left: 2px; }
/* diff 抽屉 */
.diff-meta { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; font-size: 13px; }
.diff-meta .side { padding: 2px 10px; border-radius: 4px; }
.diff-meta .base { background: #fef0f0; color: #f56c6c; }
.diff-meta .incoming { background: #f0f9eb; color: #67c23a; }
.diff-meta .ln { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin: 0 4px 0 10px; vertical-align: middle; }
.diff-meta .ln.del { background: #fde2e2; } .diff-meta .ln.add { background: #e1f3d8; }
.diff-box { border: 1px solid #ebeef5; border-radius: 6px; overflow: auto; max-height: calc(100vh - 220px);
  font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 12.5px; }
.diff-line { display: flex; white-space: pre-wrap; word-break: break-word; padding: 1px 0; }
.diff-line .gutter { flex: 0 0 22px; text-align: center; color: #c0c4cc; user-select: none; }
.diff-line .txt { flex: 1; padding-right: 10px; }
.diff-line.add { background: #f0f9eb; } .diff-line.add .gutter { color: #67c23a; }
.diff-line.del { background: #fef0f0; } .diff-line.del .gutter { color: #f56c6c; }
</style>
