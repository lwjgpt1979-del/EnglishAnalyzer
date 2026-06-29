<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listLectureNodes, splitLecture, createKnowledgeNode,
  getNodeChildren, updateKnowledgeNode, deleteKnowledgeNode,
  type LectureNode, type NodeChild } from '../api/admin'
import { Delete, Plus, Check } from '@element-plus/icons-vue'

const GRPS = [{ label: '全部', value: '' }, { label: '词法', value: '词法' }, { label: '句法', value: '句法' }]
const grp = ref('')
const rows = ref<LectureNode[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 10
const loading = ref(false)
const showFull = reactive<Record<string, boolean>>({})
const splitBusy = reactive<Record<string, boolean>>({})

// AI 拆分对话框:AI 建议的子考点可编辑(改名/增删),确认后才创建
const dlg = ref(false)
const dlgNode = ref<LectureNode | null>(null)
const dlgSubs = ref<string[]>([])
const dlgExisting = ref<string[]>([])
const dlgContent = ref('')
const dlgSaving = ref(false)

// 列表多选(批量删除考点节点本身)
const nodeSel = ref<string[]>([])
const nodeDeleting = ref(false)
function toggleNode(id: string, v: boolean) {
  if (v) { if (!nodeSel.value.includes(id)) nodeSel.value.push(id) }
  else nodeSel.value = nodeSel.value.filter(x => x !== id)
}
const pageAllSel = computed(() => rows.value.length > 0 && nodeSel.value.length === rows.value.length)
const pageSomeSel = computed(() => nodeSel.value.length > 0 && !pageAllSel.value)
function toggleNodeAll(v: boolean) { nodeSel.value = v ? rows.value.map(r => r.id) : [] }

async function load() {
  loading.value = true
  try {
    const d = await listLectureNodes({ grp: grp.value || undefined, skip: (page.value - 1) * pageSize, limit: pageSize })
    rows.value = d.items
    total.value = d.total
    nodeSel.value = []
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}
function reload() { page.value = 1; load() }

async function batchDeleteNodes() {
  const sel = rows.value.filter(r => nodeSel.value.includes(r.id))
  if (!sel.length) return
  const withKids = sel.filter(r => r.child_count > 0).length
  try {
    await ElMessageBox.confirm(
      `删除选中的 ${sel.length} 个考点节点?将连带删除其挂边(节点本身从知识图谱移除)。` +
      (withKids ? `其中 ${withKids} 个仍有下级子考点,会被拒绝删除——请先清空其子考点。` : '') + '不可恢复。',
      '批量删除考点',
      { type: 'warning', confirmButtonText: '删除', confirmButtonClass: 'el-button--danger', cancelButtonText: '取消' })
  } catch { return }
  nodeDeleting.value = true
  let ok = 0; let fail = 0
  try {
    for (const r of sel) {
      try { await deleteKnowledgeNode(r.id); ok++ }
      catch (e: any) { fail++; ElMessage.error(`「${r.name}」删除失败:${e?.message || ''}`) }
    }
  } finally { nodeDeleting.value = false }
  if (ok) ElMessage.success(`已删除 ${ok} 个考点${fail ? `,${fail} 个失败` : ''}`)
  await load()
}

async function doSplit(n: LectureNode) {
  splitBusy[n.id] = true
  try {
    const r = await splitLecture(n.id)
    dlgNode.value = n
    dlgContent.value = r.content || n.content
    dlgExisting.value = r.existing || []
    dlgSubs.value = r.subs.length ? [...r.subs] : ['']
    dlg.value = true
    if (!r.subs.length) ElMessage.info('AI 未拆出子考点(详解可能纯表格/过短),可手动添加')
  } catch (e: any) { ElMessage.error(e?.message || '拆分失败') }
  finally { splitBusy[n.id] = false }
}
function addSub() { dlgSubs.value.push('') }
function removeSub(i: number) { dlgSubs.value.splice(i, 1) }

// 编辑已有子考点弹框:改名 / 删除
const editDlg = ref(false)
const editNode = ref<LectureNode | null>(null)
const editKids = ref<NodeChild[]>([])
const editLoading = ref(false)
const editSel = ref<string[]>([])     // 选中的子考点 id
function toggleSel(id: string, v: boolean) {
  if (v) { if (!editSel.value.includes(id)) editSel.value.push(id) }
  else editSel.value = editSel.value.filter(x => x !== id)
}
const allSel = computed(() => editKids.value.length > 0 && editSel.value.length === editKids.value.length)
const someSel = computed(() => editSel.value.length > 0 && !allSel.value)
function toggleAll(v: boolean) { editSel.value = v ? editKids.value.map(k => k.id) : [] }

async function openEditChildren(n: LectureNode) {
  editNode.value = n
  editDlg.value = true
  editLoading.value = true
  editKids.value = []
  editSel.value = []
  try { editKids.value = await getNodeChildren(n.id) }
  catch (e: any) { ElMessage.error(e?.message || '加载子考点失败') }
  finally { editLoading.value = false }
}
async function batchDeleteKids() {
  const ids = [...editSel.value]
  if (!ids.length) return
  try {
    await ElMessageBox.confirm(
      `删除选中的 ${ids.length} 个子考点?将连带删除其挂边(有下级子节点的会被拒绝)。不可恢复。`, '批量删除',
      { type: 'warning', confirmButtonText: '删除', confirmButtonClass: 'el-button--danger', cancelButtonText: '取消' })
  } catch { return }
  let ok = 0
  for (const id of ids) {
    try { await deleteKnowledgeNode(id); editKids.value = editKids.value.filter(x => x.id !== id); ok++ }
    catch (e: any) { ElMessage.error(`删除失败:${e?.message || ''}`) }
  }
  editSel.value = editSel.value.filter(id => editKids.value.some(k => k.id === id))   // 失败的留着
  if (editNode.value) editNode.value.child_count = editKids.value.length
  if (ok) ElMessage.success(`已删除 ${ok} / ${ids.length} 个子考点`)
}
async function renameKid(k: NodeChild) {
  const name = (k.name || '').trim()
  if (!name) { ElMessage.warning('名称不能为空'); return }
  try { await updateKnowledgeNode(k.id, { name }); ElMessage.success('已保存') }
  catch (e: any) { ElMessage.error(e?.message || '保存失败') }
}
const editSaving = ref(false)
async function saveAllKids() {
  const targets = editKids.value.filter(k => (k.name || '').trim())
  if (!targets.length) { ElMessage.warning('没有可保存的子考点'); return }
  editSaving.value = true
  let ok = 0
  try {
    for (const k of targets) {
      try { await updateKnowledgeNode(k.id, { name: k.name.trim() }); ok++ }
      catch (e: any) { ElMessage.error(`「${k.name}」保存失败:${e?.message || ''}`) }
    }
    if (ok) ElMessage.success(`已保存 ${ok} / ${targets.length} 个子考点`)
  } finally { editSaving.value = false }
}
async function deleteKid(k: NodeChild) {
  try {
    await ElMessageBox.confirm(
      `删除子考点「${k.name}」?将连带删除其挂边(有下级子节点会被拒绝)。不可恢复。`, '删除子考点',
      { type: 'warning', confirmButtonText: '删除', confirmButtonClass: 'el-button--danger', cancelButtonText: '取消' })
  } catch { return }
  try {
    await deleteKnowledgeNode(k.id)
    editKids.value = editKids.value.filter(x => x.id !== k.id)
    if (editNode.value) editNode.value.child_count = Math.max(0, editNode.value.child_count - 1)
    ElMessage.success('已删除')
  } catch (e: any) { ElMessage.error(e?.message || '删除失败') }
}

async function confirmSplit() {
  const n = dlgNode.value
  if (!n) return
  const names = [...new Set(dlgSubs.value.map(s => s.trim()).filter(Boolean))]
  if (!names.length) { ElMessage.warning('请至少保留一个子考点'); return }
  dlgSaving.value = true
  let ok = 0
  try {
    for (const name of names) {
      try { await createKnowledgeNode({ name, parent_id: n.id }); ok++ }
      catch (e: any) { ElMessage.error(`「${name}」创建失败:${e?.message || ''}`) }
    }
    n.child_count += ok
    if (ok) ElMessage.success(`已在「${n.name}」下创建 ${ok} 个子考点`)
    dlg.value = false
  } finally { dlgSaving.value = false }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3 style="margin:0">详解拆分审核</h3>
      <span style="margin-left:8px">分类</span>
      <el-select v-model="grp" style="width:110px;margin-left:6px" @change="reload">
        <el-option v-for="g in GRPS" :key="g.value" :label="g.label" :value="g.value" />
      </el-select>
      <span class="hint">AI 读每条详解 → 拆出更细的子考点,弹框里可改名/增删,确认后在该考点下新建子考点(标 ✍人工)。共 {{ total }} 条有详解的考点。</span>
    </div>

    <div v-if="rows.length" class="sel-bar">
      <el-checkbox :model-value="pageAllSel" :indeterminate="pageSomeSel" @change="(v:any) => toggleNodeAll(!!v)">全选本页</el-checkbox>
      <span class="muted" style="margin-left:8px">已选 {{ nodeSel.length }} / {{ rows.length }}</span>
      <el-button type="danger" plain size="small" style="margin-left:12px"
        :loading="nodeDeleting" :disabled="!nodeSel.length" @click="batchDeleteNodes">
        <el-icon style="margin-right:2px"><Delete /></el-icon>批量删除选中{{ nodeSel.length ? `（${nodeSel.length}）` : '' }}
      </el-button>
    </div>

    <el-card v-for="n in rows" :key="n.id" shadow="never" class="node-card">
      <div class="node-head">
        <el-checkbox :model-value="nodeSel.includes(n.id)" @change="(v:any) => toggleNode(n.id, !!v)" style="margin-right:4px" />
        <span class="node-name">{{ n.name }}</span>
        <span class="node-code">{{ n.code }}</span>
        <el-button v-if="n.child_count" size="small" link type="primary" @click="openEditChildren(n)">编辑子考点 {{ n.child_count }}</el-button>
        <el-button size="small" type="primary" :loading="splitBusy[n.id]" style="margin-left:auto" @click="doSplit(n)">
          {{ n.child_count ? '重新 AI 拆分' : 'AI 拆分' }}
        </el-button>
      </div>

      <div class="lecture">
        <pre class="md">{{ showFull[n.id] ? n.content : n.content.slice(0, 160) }}{{ !showFull[n.id] && n.content.length > 160 ? '…' : '' }}</pre>
        <el-link v-if="n.content.length > 160" type="primary" :underline="false" @click="showFull[n.id] = !showFull[n.id]">
          {{ showFull[n.id] ? '收起' : '展开详解' }}
        </el-link>
      </div>
    </el-card>

    <div class="pager">
      <el-pagination layout="total, prev, pager, next" :total="total" :page-size="pageSize"
        v-model:current-page="page" @current-change="load" />
    </div>

    <!-- AI 拆分:可编辑 + 确认 -->
    <el-dialog v-model="dlg" :title="`AI 拆分子考点 · ${dlgNode?.name || ''}`" width="960px">
      <div class="dlg-hint">AI 读详解建议的子考点,**可改名 / 增删**;确认后在「{{ dlgNode?.name }}」下创建为子节点(标 ✍人工)。</div>
      <div v-if="dlgExisting.length" class="muted" style="margin-bottom:8px">已有子考点(不会重复):{{ dlgExisting.join('、') }}</div>

      <el-collapse class="ref-box">
        <el-collapse-item name="ref">
          <template #title><span class="ref-title">参考详解(点开)</span></template>
          <pre class="md">{{ dlgContent }}</pre>
        </el-collapse-item>
      </el-collapse>

      <div class="subs-label" style="margin:10px 0 4px">子考点(确认后逐个创建):</div>
      <div v-for="(s, i) in dlgSubs" :key="i" class="sub-row">
        <span class="idx">{{ i + 1 }}</span>
        <el-input v-model="dlgSubs[i]" size="small" placeholder="子考点名" maxlength="60" />
        <el-button size="small" link type="danger" @click="removeSub(i)"><el-icon><Delete /></el-icon></el-button>
      </div>
      <el-button size="small" link type="primary" style="margin-top:6px" @click="addSub"><el-icon style="margin-right:2px"><Plus /></el-icon>添加子考点</el-button>

      <template #footer>
        <el-button @click="dlg = false">取消</el-button>
        <el-button type="primary" :loading="dlgSaving" @click="confirmSplit">确认创建</el-button>
      </template>
    </el-dialog>

    <!-- 编辑已有子考点:改名 / 删除 -->
    <el-dialog v-model="editDlg" :title="`编辑子考点 · ${editNode?.name || ''}`" width="900px">
      <div v-loading="editLoading">
        <el-collapse v-if="editNode?.content" class="ref-box" style="margin-bottom:10px">
          <el-collapse-item name="ref">
            <template #title><span class="ref-title">参考详解（原文,点开)</span></template>
            <pre class="md">{{ editNode.content }}</pre>
          </el-collapse-item>
        </el-collapse>
        <el-empty v-if="!editLoading && !editKids.length" description="暂无子考点" :image-size="50" />
        <div v-if="editKids.length" class="kid-row kid-head">
          <el-checkbox :model-value="allSel" :indeterminate="someSel" @change="(v:any) => toggleAll(!!v)">全选</el-checkbox>
          <span class="muted" style="margin-left:8px">已选 {{ editSel.length }} / {{ editKids.length }}</span>
        </div>
        <div v-for="k in editKids" :key="k.id" class="kid-row">
          <el-checkbox :model-value="editSel.includes(k.id)" @change="(v:any) => toggleSel(k.id, !!v)" />
          <span class="idx">{{ k.code }}</span>
          <el-input v-model="k.name" size="small" maxlength="60" />
          <el-tag v-if="k.child_count" size="small" type="info" title="该子考点下还有下级">下级 {{ k.child_count }}</el-tag>
          <el-button size="small" type="primary" plain @click="renameKid(k)"><el-icon><Check /></el-icon></el-button>
          <el-button size="small" type="danger" plain @click="deleteKid(k)"><el-icon><Delete /></el-icon></el-button>
        </div>
        <div class="muted" style="margin-top:8px">改名后点 ✓ 保存;删除会连带其挂边、且有下级时会被拒绝。</div>
      </div>
      <template #footer>
        <el-button @click="editDlg = false">关闭</el-button>
        <el-button type="danger" plain :disabled="!editSel.length" @click="batchDeleteKids">
          删除选中{{ editSel.length ? `（${editSel.length}）` : '' }}
        </el-button>
        <el-button type="primary" :loading="editSaving" :disabled="!editKids.length" @click="saveAllKids">全部保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 6px; margin-bottom: 16px; flex-wrap: wrap; }
.sel-bar { display: flex; align-items: center; padding: 8px 12px; margin-bottom: 10px;
  background: #f5f7fa; border: 1px solid #ebeef5; border-radius: 6px; }
.hint { margin-left: 14px; color: #909399; font-size: 12px; }
.node-card { margin-bottom: 12px; }
.node-head { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.node-name { font-weight: 600; font-size: 15px; }
.node-code { font-family: monospace; font-size: 12px; color: #909399; }
.lecture { margin-bottom: 8px; }
.md { white-space: pre-wrap; word-break: break-word; font-size: 12px; line-height: 1.6; color: #606266;
  background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; padding: 8px 10px; margin: 0 0 4px; max-height: 260px; overflow: auto; }
.muted { color: #909399; font-size: 12px; }
.pager { margin-top: 14px; display: flex; justify-content: flex-end; }
.dlg-hint { font-size: 13px; color: #606266; margin-bottom: 8px; }
.ref-box { border: 1px solid #ebeef5; border-radius: 6px; padding: 0 10px; background: #fafcff; }
.ref-title { font-size: 13px; color: #409eff; }
.subs-label { font-size: 12px; color: #909399; }
.sub-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.kid-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.kid-row .idx { width: 90px; font-family: monospace; font-size: 11px; color: #909399; text-align: left; }
.idx { width: 20px; text-align: center; color: #c0c4cc; font-size: 12px; flex-shrink: 0; }
</style>
