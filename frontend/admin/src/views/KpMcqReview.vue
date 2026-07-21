<script setup lang="ts">
import { onMounted, ref, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppDialog from '../components/AppDialog.vue'
import {
  listKpMcqs, fixKpMcq, editKpMcq, deleteKpMcq, batchDeleteKpMcq, kpMcqRevisions,
  setKpMcqThreshold, type KpMcqItem, type KpMcqRevision,
} from '../api/kpMcq'

const rows = ref<KpMcqItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const minReport = ref(1)
const loading = ref(false)
const selected = ref<KpMcqItem[]>([])
const threshold = ref(3)
const fixingId = ref('')

async function load() {
  loading.value = true
  try {
    const data = await listKpMcqs({ min_report: minReport.value, skip: (page.value - 1) * pageSize, limit: pageSize })
    rows.value = data.items
    total.value = data.total
    threshold.value = data.threshold
  } finally { loading.value = false }
}
function reload() { page.value = 1; load() }

async function saveThreshold() {
  const r = await setKpMcqThreshold(threshold.value)
  threshold.value = r.threshold
  ElMessage.success(`报错阈值已设为 ${r.threshold}（≥该值 AI 自动修正）`)
}

async function aiFix(row: KpMcqItem) {
  await ElMessageBox.confirm(`让 AI 审校并修正这道题?（会改正答案/解析/干扰项,记入修改记录,报错计数清零）`, 'AI 修正', { type: 'info' })
  fixingId.value = row.id
  try {
    const r = await fixKpMcq(row.id)
    if (r && r.id) { ElMessage.success('AI 已修正'); load() }
    else ElMessage.warning('修正失败（可能 dev-mock 或返回为空）')
  } finally { fixingId.value = '' }
}
async function remove(row: KpMcqItem) {
  await ElMessageBox.confirm(`删除这道题?`, '删除', { type: 'warning' })
  await deleteKpMcq(row.id); ElMessage.success('已删除'); load()
}
async function batchRemove() {
  if (!selected.value.length) return
  await ElMessageBox.confirm(`删除选中的 ${selected.value.length} 道题?`, '批量删除', { type: 'warning' })
  await batchDeleteKpMcq(selected.value.map(r => r.id))
  ElMessage.success('已删除'); selected.value = []; load()
}

// —— 编辑弹框 ——
const editOpen = ref(false)
const editForm = reactive({ id: '', stem: '', options: [] as string[], answer: '', explanation: '' })
function openEdit(row: KpMcqItem) {
  Object.assign(editForm, { id: row.id, stem: row.stem, options: [...row.options], answer: row.answer, explanation: row.explanation })
  editOpen.value = true
}
async function saveEdit() {
  const opts = editForm.options.map(o => o.trim()).filter(Boolean)
  if (opts.length < 2 || !editForm.answer.trim() || !editForm.stem.trim()) { ElMessage.error('选项≥2、答案、题干必填'); return }
  if (!opts.includes(editForm.answer.trim())) { ElMessage.error('答案必须是选项之一'); return }
  await editKpMcq(editForm.id, { stem: editForm.stem.trim(), options: opts, answer: editForm.answer.trim(), explanation: editForm.explanation.trim() })
  ElMessage.success('已保存'); editOpen.value = false; load()
}

// —— 修改记录弹框 ——
const revOpen = ref(false)
const revList = ref<KpMcqRevision[]>([])
const revLoading = ref(false)
async function openRevisions(row: KpMcqItem) {
  revOpen.value = true; revLoading.value = true; revList.value = []
  try { revList.value = await kpMcqRevisions(row.id) } finally { revLoading.value = false }
}

onMounted(load)
</script>

<template>
  <div class="page">
    <div class="toolbar">
      <h2>考点题复核</h2>
      <span class="hint">学生「换一题」= 报错的 AI 考点题。报错次数 ≥ 阈值会自动 AI 修正;也可在此手动修正/编辑/删除。</span>
    </div>

    <div class="toolbar">
      <span>报错次数 ≥</span>
      <el-input-number v-model="minReport" :min="0" :max="99" size="small" @change="reload" />
      <el-divider direction="vertical" />
      <span>自动修正阈值</span>
      <el-input-number v-model="threshold" :min="1" :max="99" size="small" />
      <el-button size="small" @click="saveThreshold">保存阈值</el-button>
      <el-button size="small" type="danger" :disabled="!selected.length" @click="batchRemove">
        批量删除{{ selected.length ? `(${selected.length})` : '' }}
      </el-button>
    </div>

    <el-table v-loading="loading" :data="rows" border style="width: 100%"
              @selection-change="(rs: KpMcqItem[]) => selected = rs">
      <el-table-column type="selection" width="44" />
      <el-table-column prop="word" label="目标词" width="130" />
      <el-table-column prop="dimension_label" label="维度" width="100" />
      <el-table-column label="题干" min-width="240">
        <template #default="{ row }"><span style="line-height:1.5">{{ row.stem }}</span></template>
      </el-table-column>
      <el-table-column label="选项 / 答案" min-width="220">
        <template #default="{ row }">
          <div style="line-height:1.6">
            <span v-for="(o, i) in row.options" :key="i"
                  :style="{ color: o === row.answer ? '#0F6E56' : '#606266', fontWeight: o === row.answer ? 600 : 400 }">
              {{ o }}<span v-if="i < row.options.length - 1"> · </span>
            </span>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="report_count" label="报错" width="80" sortable align="center">
        <template #default="{ row }"><el-tag type="danger">{{ row.report_count }}</el-tag></template>
      </el-table-column>
      <el-table-column label="操作" width="260" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" :loading="fixingId === row.id" @click="aiFix(row)">AI 修正</el-button>
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" @click="openRevisions(row)">修改记录</el-button>
          <el-button size="small" type="danger" text @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination class="pager" layout="total, prev, pager, next, jumper"
      :total="total" :page-size="pageSize" v-model:current-page="page" @current-change="load" />

    <!-- 编辑 -->
    <AppDialog v-model="editOpen" title="编辑考点题" width="640px">
      <el-form label-width="64px">
        <el-form-item label="题干"><el-input v-model="editForm.stem" type="textarea" :rows="2" /></el-form-item>
        <el-form-item v-for="(_, i) in editForm.options" :key="i" :label="`选项${i + 1}`">
          <el-input v-model="editForm.options[i]" />
        </el-form-item>
        <el-form-item label="答案">
          <el-select v-model="editForm.answer" style="width:100%">
            <el-option v-for="(o, i) in editForm.options.filter(x => x.trim())" :key="i" :label="o" :value="o.trim()" />
          </el-select>
        </el-form-item>
        <el-form-item label="解析"><el-input v-model="editForm.explanation" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editOpen = false">取消</el-button>
        <el-button type="primary" @click="saveEdit">保存</el-button>
      </template>
    </AppDialog>

    <!-- 修改记录 -->
    <AppDialog v-model="revOpen" title="修改记录" width="720px">
      <div v-loading="revLoading">
        <el-empty v-if="!revLoading && !revList.length" description="暂无修改记录" />
        <el-timeline v-else>
          <el-timeline-item v-for="r in revList" :key="r.id"
            :timestamp="(r.created_at ? new Date(r.created_at).toLocaleString() : '') + ' · ' + (r.trigger === 'auto' ? 'AI自动' : '人工/后台')"
            placement="top">
            <div class="rev">
              <div class="rev-col">
                <div class="rev-h">修改前</div>
                <div class="rev-q">{{ r.before?.stem }}</div>
                <div class="rev-a">答案: {{ r.before?.answer }}</div>
                <div class="rev-e">{{ r.before?.explanation }}</div>
              </div>
              <div class="rev-arrow">→</div>
              <div class="rev-col">
                <div class="rev-h ok">修改后</div>
                <div class="rev-q">{{ r.after?.stem }}</div>
                <div class="rev-a ok">答案: {{ r.after?.answer }}</div>
                <div class="rev-e">{{ r.after?.explanation }}</div>
              </div>
            </div>
          </el-timeline-item>
        </el-timeline>
      </div>
    </AppDialog>
  </div>
</template>

<style scoped>
.page { padding: 16px; }
.toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }
.toolbar h2 { margin: 0; }
.hint { color: #909399; font-size: 13px; }
.pager { margin-top: 16px; justify-content: flex-end; }
.rev { display: flex; gap: 10px; align-items: stretch; }
.rev-col { flex: 1; background: #f7f8fa; border-radius: 8px; padding: 10px; }
.rev-arrow { display: flex; align-items: center; color: #c0c4cc; font-size: 20px; }
.rev-h { font-size: 12px; color: #909399; margin-bottom: 6px; }
.rev-h.ok { color: #0F6E56; }
.rev-q { font-size: 13px; color: #303133; line-height: 1.5; }
.rev-a { font-size: 12px; color: #A32D2D; margin-top: 4px; }
.rev-a.ok { color: #0F6E56; }
.rev-e { font-size: 12px; color: #909399; margin-top: 4px; line-height: 1.5; }
</style>
