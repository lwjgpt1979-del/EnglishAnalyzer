<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listKnowledgeNodes, getKnowledgeNode, getNodeHub, updateKnowledgeNode,
  retireKnowledgeNode, restoreKnowledgeNode, deleteKnowledgeNode,
  getNodeTree, createKnowledgeNode, moveKnowledgeNode,
  getNodeLecture, upsertLectureSection, generateLectureSection, generateMissingLecture,
  setLectureSectionStatus, publishAllLecture,
  type NodeHub,
} from '../api/admin'
import type { KpNodeOverviewItem, KpNodeDetail, NodeTreeItem, LectureSectionCell } from '../types'
import { EditPen } from '@element-plus/icons-vue'
import AppDialog from '../components/AppDialog.vue'

const router = useRouter()
const STAGE_OPTS = ['小', '初', '高']

const STAGES = [{ label: '全部学段', value: '' }, { label: '小', value: '小' }, { label: '初', value: '初' }, { label: '高', value: '高' }]
const STATUSES = [
  { label: '启用', value: 'active' }, { label: '候选', value: 'candidate' },
  { label: '停用', value: 'retired' }, { label: '全部', value: '' },
]
const STATUS_TAG: Record<string, string> = { active: 'success', candidate: 'warning', retired: 'info' }
const STATUS_LABEL: Record<string, string> = { active: '启用', candidate: '候选', retired: '停用' }

const LINKED = [
  { label: '全部', value: '' }, { label: '已关联教材', value: 'unit' },
  { label: '已关联真题', value: 'question' }, { label: '同时关联教材+真题', value: 'both' },
]
const stage = ref('')
const status = ref('active')
const q = ref('')
const linked = ref('')          // 关联筛选:''=全部 / unit / question / both
const rows = ref<KpNodeOverviewItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 30
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const data = await listKnowledgeNodes({
      stage: stage.value || undefined,
      status: status.value || undefined, q: q.value || undefined,
      linked: (linked.value || undefined) as 'unit' | 'question' | 'both' | undefined,
      skip: (page.value - 1) * pageSize, limit: pageSize,
    })
    rows.value = data.items
    total.value = data.total
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}
function reload() { page.value = 1; load() }

// ── 知识分类树(F:单树,去 3 轴)──
const viewMode = ref<'tree' | 'list'>('tree')
const treeData = ref<NodeTreeItem[]>([])
const treeLoading = ref(false)
const treeStage = ref('')      // 树视图按学段过滤(空=全部)
const treeProps = { label: 'name', children: 'children' }

async function loadTree() {
  treeLoading.value = true
  try { treeData.value = (await getNodeTree('knowledge', true, treeStage.value || undefined)).items }
  catch (e: any) { ElMessage.error(e?.message || '加载树失败') }
  finally { treeLoading.value = false }
}
function switchView(m: 'tree' | 'list') {
  viewMode.value = m
  if (m === 'tree') loadTree(); else load()
}
async function addChild(parent: NodeTreeItem | null) {
  const { value } = await ElMessageBox.prompt(
    parent ? `在「${parent.name}」下新增子节点` : '新增顶层分类(词法/句法/篇章…)',
    '新增节点', { inputPattern: /\S/, inputErrorMessage: '名称不能为空' })
  try {
    await createKnowledgeNode({ name: value.trim(),
      parent_id: parent ? parent.id : null, axis: parent ? undefined : 'knowledge' })
    ElMessage.success('已新增')
    await loadTree()
  } catch (e: any) { ElMessage.error(e?.message || '新增失败') }
}
async function retireTreeNode(node: NodeTreeItem) {
  await ElMessageBox.confirm(`停用「${node.name}」?(子节点不受影响,可恢复)`, '停用', { type: 'warning' })
  try { await retireKnowledgeNode(node.id); ElMessage.success('已停用'); await loadTree() }
  catch (e: any) { ElMessage.error(e?.message || '停用失败') }
}
async function deleteTreeNode(node: NodeTreeItem) {
  try {
    await ElMessageBox.confirm(
      `永久删除「${node.name}」?将连带删除它的所有挂边(教材单元/真题/上传题/词汇/长难句/学生掌握 的关联、别名、关系)。` +
      `<br/><span style="color:#909399">不影响共享的词汇/题目主表;若它下面还有子节点会被拒绝(需先删子节点)。此操作不可恢复。</span>`,
      `删除节点`,
      { type: 'warning', confirmButtonText: '删除', confirmButtonClass: 'el-button--danger',
        cancelButtonText: '取消', dangerouslyUseHTMLString: true })
  } catch { return }
  try { await deleteKnowledgeNode(node.id); ElMessage.success('已删除'); await loadTree() }
  catch (e: any) { ElMessage.error(e?.message || '删除失败') }
}
// 拖拽移动:drop 到节点内部=成为其子;前后=成为其兄弟(同父)
function allowDrop(_drag: any, drop: any, type: string) {
  return type === 'inner' || drop.level >= 1
}
async function onNodeDrop(dragNode: any, dropNode: any, dropType: string) {
  const newParentId = dropType === 'inner' ? dropNode.data.id
    : (dropNode.parent && dropNode.parent.data.id ? dropNode.parent.data.id : null)
  try {
    await moveKnowledgeNode(dragNode.data.id, newParentId)
    ElMessage.success('已移动')
    await loadTree()
  } catch (e: any) { ElMessage.error(e?.message || '移动失败'); await loadTree() }
}

// ── 节点详情 + 维护(D2)──
const detailOpen = ref(false)
const detailLoading = ref(false)
const detailBusy = ref(false)
const detail = ref<KpNodeDetail | null>(null)
const hub = ref<NodeHub | null>(null)
const edit = ref({ name: '', node_kind: '', applicable_stages: [] as string[], description: '' })

async function openDetail(id: string) {
  detailOpen.value = true
  detailLoading.value = true
  detail.value = null; hub.value = null
  try {
    const [d, h] = await Promise.all([getKnowledgeNode(id), getNodeHub(id)])
    detail.value = d
    hub.value = h
    edit.value = { name: d.name, node_kind: d.node_kind || '',
                   applicable_stages: d.applicable_stages || [], description: d.description || '' }
  } catch (e: any) { ElMessage.error(e?.message || '加载详情失败') }
  finally { detailLoading.value = false }
}
function gotoQuestions() { router.push({ path: '/platform-questions' }) }
async function saveEdit() {
  if (!detail.value) return
  if (!edit.value.name.trim()) { ElMessage.warning('名称不能为空'); return }
  detailBusy.value = true
  try {
    detail.value = await updateKnowledgeNode(detail.value.id, {
      name: edit.value.name.trim(), node_kind: edit.value.node_kind || null,
      applicable_stages: edit.value.applicable_stages, description: edit.value.description || null })
    ElMessage.success('已保存')
    await (viewMode.value === 'tree' ? loadTree() : load())
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
    await (viewMode.value === 'tree' ? loadTree() : load())
  } catch (e: any) { ElMessage.error(e?.message || '操作失败') }
  finally { detailBusy.value = false }
}
// ── 讲解补全(kp_lecture:按类型环节)──────────────────────────────────────────
const lecBusy = ref('')          // 正在 AI 生成的 section_key,'__all__'=一键补全
const editDlg = ref(false)
const editSection = ref<LectureSectionCell | null>(null)
const editMd = ref('')
const editSaving = ref(false)

async function reloadLecture() {
  if (!detail.value) return
  detail.value.lecture = await getNodeLecture(detail.value.id)
}
async function genSection(key: string) {
  if (!detail.value) return
  lecBusy.value = key
  try {
    await generateLectureSection(detail.value.id, key)
    await reloadLecture()
    ElMessage.success('AI 已生成草稿,确认后发布')
  } catch (e: any) { ElMessage.error(e?.message || 'AI 生成失败') }
  finally { lecBusy.value = '' }
}
async function genMissing() {
  if (!detail.value) return
  lecBusy.value = '__all__'
  try {
    const { generated } = await generateMissingLecture(detail.value.id)
    await reloadLecture()
    ElMessage.success(generated ? `AI 已补 ${generated} 个环节(草稿)` : '没有缺失环节')
  } catch (e: any) { ElMessage.error(e?.message || 'AI 补全失败') }
  finally { lecBusy.value = '' }
}
async function toggleSection(s: LectureSectionCell) {
  if (!detail.value) return
  const next = s.status === 'published' ? 'draft' : 'published'
  try {
    await setLectureSectionStatus(detail.value.id, s.section_key, next)
    await reloadLecture(); await load()
  } catch (e: any) { ElMessage.error(e?.message || '操作失败') }
}
async function publishAll(status: 'draft' | 'published') {
  if (!detail.value) return
  try {
    await publishAllLecture(detail.value.id, status)
    await reloadLecture(); await load()
    ElMessage.success(status === 'published' ? '已整点发布' : '已整点下架')
  } catch (e: any) { ElMessage.error(e?.message || '操作失败') }
}
function openEdit(s: LectureSectionCell) {
  editSection.value = s
  editMd.value = s.content_md || ''
  editDlg.value = true
}
async function saveSection() {
  if (!detail.value || !editSection.value) return
  editSaving.value = true
  try {
    await upsertLectureSection(detail.value.id, editSection.value.section_key, { content_md: editMd.value })
    editDlg.value = false
    await reloadLecture(); await load()
    ElMessage.success('已保存(草稿)')
  } catch (e: any) { ElMessage.error(e?.message || '保存失败') }
  finally { editSaving.value = false }
}

onMounted(loadTree)
</script>

<template>
  <div>
    <div class="toolbar">
      <el-radio-group v-model="viewMode" @change="switchView($event as any)">
        <el-radio-button value="tree">树视图</el-radio-button>
        <el-radio-button value="list">列表</el-radio-button>
      </el-radio-group>
      <span class="hint" style="margin-left:12px">受控知识树:后台定结构,教材/真题生成只能映射到树上既有节点。</span>
    </div>

    <!-- 树视图 -->
    <div v-if="viewMode === 'tree'">
      <div class="toolbar">
        <el-button type="primary" @click="addChild(null)">+ 新增顶层分类</el-button>
        <span style="margin:0 6px 0 10px">学段：</span>
        <el-select v-model="treeStage" style="width:110px" @change="loadTree">
          <el-option v-for="s in STAGES" :key="s.value" :label="s.label" :value="s.value" />
        </el-select>
        <el-button style="margin-left:8px" @click="loadTree">刷新</el-button>
        <span class="hint">知识分类树(词法/句法/篇章→考点)。学段过滤:只看某学段适用的考点(分类为通用脚手架,各学段共用)。拖拽可移动层级。点名称看详情。</span>
      </div>
      <el-tree v-loading="treeLoading" :data="treeData" :props="treeProps" node-key="id"
        draggable :allow-drop="allowDrop" @node-drop="onNodeDrop"
        :expand-on-click-node="false" default-expand-all style="max-width:900px">
        <template #default="{ data }">
          <span class="tnode">
            <el-link type="primary" @click.stop="openDetail(data.id)">{{ data.name }}</el-link>
            <span v-if="data.source === 'manual'" class="cnt cnt-m" title="人工新建的考点"><el-icon style="vertical-align:-2px"><EditPen /></el-icon> 人工</span>
            <span class="tmeta" v-if="data.node_kind">{{ data.node_kind }}</span>
            <span v-if="data.applicable_stages && data.applicable_stages.length" class="cnt cnt-s"
              title="适用学段">{{ data.applicable_stages.join('/') }}</span>
            <span v-if="data.unit_refs" class="cnt cnt-u" title="教材单元挂载数(含子节点)">教 {{ data.unit_refs }}</span>
            <span v-if="data.question_refs" class="cnt cnt-q" title="真题挂载数(含子节点)">真 {{ data.question_refs }}</span>
            <span class="tops">
              <el-button link size="small" type="primary" @click.stop="addChild(data)">+ 子节点</el-button>
              <el-button link size="small" type="warning" @click.stop="retireTreeNode(data)">停用</el-button>
              <el-button link size="small" type="danger" @click.stop="deleteTreeNode(data)">删除</el-button>
            </span>
          </span>
        </template>
      </el-tree>
    </div>

    <!-- 列表视图 -->
    <div v-else>
    <div class="toolbar">
      <span>学段：</span>
      <el-select v-model="stage" style="width:110px" @change="reload">
        <el-option v-for="s in STAGES" :key="s.value" :label="s.label" :value="s.value" />
      </el-select>
      <span style="margin-left:12px">状态：</span>
      <el-select v-model="status" style="width:100px" @change="reload">
        <el-option v-for="s in STATUSES" :key="s.value" :label="s.label" :value="s.value" />
      </el-select>
      <span style="margin-left:12px">关联：</span>
      <el-select v-model="linked" style="width:170px" @change="reload">
        <el-option v-for="l in LINKED" :key="l.value" :label="l.label" :value="l.value" />
      </el-select>
      <el-input v-model="q" placeholder="搜知识点名" clearable style="width:200px;margin-left:12px"
        @keyup.enter="reload" @clear="reload" />
      <el-button type="primary" style="margin-left:8px" @click="reload">查询</el-button>
      <span class="hint">知识点骨架(knowledge_nodes)总览。共 {{ total }} 个节点。讲解完整度=该考点类型模板的教学环节已配几个。</span>
    </div>

    <el-table v-loading="loading" :data="rows" border style="width:100%">
      <el-table-column prop="name" label="知识点" min-width="220" show-overflow-tooltip>
        <template #default="{ row }">
          <el-link type="primary" @click="openDetail(row.id)">{{ row.name }}</el-link>
          <span v-if="row.source === 'manual'" class="manual-tag" title="人工新建的考点"><el-icon style="vertical-align:-2px"><EditPen /></el-icon> 人工</span>
        </template>
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
      <el-table-column label="讲解完整度" width="150">
        <template #default="{ row }">
          <el-progress :percentage="row.lecture_total ? Math.round(row.lecture_filled / row.lecture_total * 100) : 0" :stroke-width="14"
            :status="row.lecture_total && row.lecture_filled === row.lecture_total ? 'success' : (row.lecture_filled === 0 ? 'exception' : undefined)"
            :format="() => `${row.lecture_filled}/${row.lecture_total}`" />
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
    </div><!-- /列表视图 -->

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
            <el-form-item label="子类型"><el-input v-model="edit.node_kind" placeholder="如 板块/专题/考点" /></el-form-item>
            <el-form-item label="适用学段">
              <el-checkbox-group v-model="edit.applicable_stages">
                <el-checkbox v-for="s in STAGE_OPTS" :key="s" :value="s">{{ s }}</el-checkbox>
              </el-checkbox-group>
            </el-form-item>
            <el-form-item label="描述"><el-input v-model="edit.description" type="textarea" :rows="2" /></el-form-item>
            <el-form-item><el-button type="primary" :loading="detailBusy" @click="saveEdit">保存修改</el-button></el-form-item>
          </el-form>

          <el-divider content-position="left">
            讲解补全 · {{ detail.lecture.kp_type_label }}类({{ detail.lecture.filled }}/{{ detail.lecture.total }})
          </el-divider>
          <div class="lec-tools">
            <el-button size="small" type="primary" plain :loading="lecBusy === '__all__'"
              @click="genMissing">AI 一键补全缺失</el-button>
            <el-button size="small" type="success" plain @click="publishAll('published')">整点发布</el-button>
            <el-button size="small" plain @click="publishAll('draft')">整点下架</el-button>
          </div>
          <div class="lec-list">
            <div v-for="s in detail.lecture.sections" :key="s.section_key" class="lec-sec">
              <div class="lec-head">
                <span class="lec-title">{{ s.title }}</span>
                <el-tag size="small" :type="s.status === 'published' ? 'success' : (s.status === 'draft' ? 'warning' : 'info')" effect="plain">
                  {{ s.status === 'published' ? '已发布' : (s.status === 'draft' ? '草稿' : '缺') }}
                </el-tag>
                <span v-if="s.source === 'ai'" class="lec-ai">AI</span>
                <div style="flex:1" />
                <el-button size="small" text type="primary" :loading="lecBusy === s.section_key"
                  @click="genSection(s.section_key)">AI 生成</el-button>
                <el-button size="small" text @click="openEdit(s)">编辑</el-button>
                <el-button v-if="s.has_content" size="small" text
                  :type="s.status === 'published' ? 'warning' : 'success'"
                  @click="toggleSection(s)">{{ s.status === 'published' ? '下架' : '发布' }}</el-button>
              </div>
              <pre v-if="s.content_md" class="lec-md">{{ s.content_md }}</pre>
              <div v-else class="lec-empty">（未填写）</div>
            </div>
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

          <el-divider content-position="left">反向关联 · 教材单元({{ hub ? hub.units.length : 0 }})</el-divider>
          <el-empty v-if="!hub || !hub.units.length" description="未被任何教材单元引用" :image-size="40" />
          <ul v-else class="d-list">
            <li v-for="u in hub.units" :key="u.unit_id">{{ u.textbook_version }} · {{ u.grade }}{{ u.semester }} · {{ u.unit_title }}</li>
          </ul>

          <el-divider content-position="left">
            反向关联 · 真题({{ hub ? hub.real_questions.length : 0 }}) / 仿真({{ hub ? hub.sim_questions.length : 0 }})
            <el-button link type="primary" size="small" @click="gotoQuestions">去平台真题 →</el-button>
          </el-divider>
          <el-empty v-if="!hub || (!hub.real_questions.length && !hub.sim_questions.length)" description="暂无真题/仿真挂到本点" :image-size="40" />
          <template v-else>
            <ul class="d-list" v-if="hub.real_questions.length">
              <li v-for="qq in hub.real_questions" :key="qq.id">
                <el-tag size="small" type="danger" effect="plain">真</el-tag>
                <span class="muted">{{ qq.paper_name }} · {{ qq.section }} {{ qq.question_no }}</span> {{ qq.stem }}
              </li>
            </ul>
            <ul class="d-list" v-if="hub.sim_questions.length">
              <li v-for="qq in hub.sim_questions" :key="qq.id">
                <el-tag size="small" type="info" effect="plain">仿</el-tag> {{ qq.stem }}
              </li>
            </ul>
          </template>

          <el-divider content-position="left">关系边({{ hub ? hub.relations.length : 0 }})</el-divider>
          <el-empty v-if="!hub || !hub.relations.length" description="暂无关系" :image-size="40" />
          <div v-else>
            <el-tag v-for="r in hub.relations" :key="r.node_id + r.relation" size="small" effect="plain" style="margin:3px"
              @click="openDetail(r.node_id)" class="rel-tag">{{ r.relation }} → {{ r.name }}</el-tag>
          </div>

          <el-divider content-position="left" v-if="detail.aliases.length">别名</el-divider>
          <div class="d-aliases" v-if="detail.aliases.length">
            <el-tag v-for="a in detail.aliases" :key="a.alias" size="small" effect="plain" style="margin:2px">{{ a.alias }}</el-tag>
          </div>
        </template>
      </div>
    </el-drawer>

    <!-- 编辑讲解环节 -->
    <AppDialog v-model="editDlg" :title="editSection ? `编辑讲解 · ${editSection.title}` : '编辑讲解'" width="720px">
      <el-input v-model="editMd" type="textarea" :rows="16" placeholder="该环节讲解正文(Markdown)" />
      <template #footer>
        <el-button @click="editDlg = false">取消</el-button>
        <el-button type="primary" :loading="editSaving" @click="saveSection">保存(草稿)</el-button>
      </template>
    </AppDialog>
  </div>
</template>

<style scoped>
.lec-tools { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.lec-list { display: flex; flex-direction: column; gap: 12px; }
.lec-sec { border: 1px solid var(--el-border-color-lighter); border-radius: 8px; padding: 10px 12px; }
.lec-head { display: flex; align-items: center; gap: 8px; }
.lec-title { font-weight: 600; }
.lec-ai { font-size: 11px; color: var(--el-color-primary); border: 1px solid var(--el-color-primary-light-5);
  border-radius: 4px; padding: 0 4px; }
.lec-md { white-space: pre-wrap; word-break: break-word; font-size: 13px; line-height: 1.6;
  background: var(--el-fill-color-lighter); border-radius: 6px; padding: 8px 10px; margin: 8px 0 0;
  max-height: 220px; overflow: auto; }
.lec-empty { color: var(--el-text-color-placeholder); font-size: 13px; margin-top: 6px; }
.toolbar { margin-bottom: 16px; display: flex; align-items: center; flex-wrap: wrap; }
.hint { margin-left: 16px; color: #909399; font-size: 12px; }
.pager { margin-top: 16px; display: flex; justify-content: flex-end; }
.muted { color: #c0c4cc; font-size: 12px; }
.tnode { display: flex; align-items: center; gap: 10px; flex: 1; padding-right: 8px; }
.tmeta { font-size: 11px; color: #909399; background: #f4f4f5; padding: 0 6px; border-radius: 3px; }
.cnt { font-size: 11px; padding: 0 6px; border-radius: 8px; }
.cnt-u { color: #409eff; background: #ecf5ff; }
.cnt-q { color: #e6a23c; background: #fdf6ec; }
.cnt-s { color: #67c23a; background: #f0f9eb; }
.cnt-m { color: #e6a23c; background: #fdf6ec; font-weight: 600; }
.manual-tag { margin-left: 8px; font-size: 11px; color: #e6a23c; background: #fdf6ec; padding: 0 6px; border-radius: 8px; }
.tops { margin-left: auto; visibility: hidden; }
.tnode:hover .tops { visibility: visible; }
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
.d-lecture .sub { font-size: 13px; color: #606266; margin: 6px 0 4px; }
.md { white-space: pre-wrap; word-break: break-word; font-family: var(--el-font-family, sans-serif);
  font-size: 13px; line-height: 1.6; color: #303133; background: #fafafa; border: 1px solid #ebeef5;
  border-radius: 6px; padding: 10px 12px; margin: 0 0 10px; max-height: 360px; overflow: auto; }
.d-list { margin: 0; padding-left: 18px; font-size: 13px; color: #303133; }
.d-list li { margin: 4px 0; }
.rel-tag { cursor: pointer; }
</style>
