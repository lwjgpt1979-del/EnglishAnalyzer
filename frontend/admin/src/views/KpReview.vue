<script setup lang="ts">
import { onMounted, ref, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppDialog from '../components/AppDialog.vue'
import {
  listReportedKp, fixReportedKp, editKpRelation, deleteKpRelation, batchDeleteKpRelation,
  hideKpRelation, unhideKpRelation, batchHideKpRelation, listKpRelationReports,
  kpReviewRecords, setKpThreshold,
  type KpRelationItem, type KpReviewRecord, type KpRelationReportItem,
} from '../api/kp'

const rows = ref<KpRelationItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const minReport = ref(1)
const hiddenFilter = ref<'exclude' | 'only' | 'all' | 'ai_prehide'>('exclude')
const loading = ref(false)
const selected = ref<KpRelationItem[]>([])
const threshold = ref(3)
const fixingWord = ref('')

async function load() {
  loading.value = true
  try {
    const isAi = hiddenFilter.value === 'ai_prehide'
    const data = await listReportedKp({
      min_report: isAi ? 0 : minReport.value,
      skip: (page.value - 1) * pageSize, limit: pageSize,
      hidden: isAi ? 'only' : hiddenFilter.value,
      hide_origin: isAi ? 'ai_prehide' : undefined,
    })
    rows.value = data.items
    total.value = data.total
    threshold.value = data.threshold
  } finally { loading.value = false }
}
function reload() { page.value = 1; load() }

async function saveThreshold() {
  const r = await setKpThreshold(threshold.value)
  threshold.value = r.threshold
  ElMessage.success(`报错阈值已设为 ${r.threshold}（有凭证举报加权 +2；≥阈值进复核 / 低峰 AI 修正）`)
}

async function aiFix(row: KpRelationItem) {
  await ElMessageBox.confirm(
    `让 AI 审校修正「${row.word}」被报错达阈值(≥${threshold.value})的考点?（会删错项/改表述,记入审校记录,报错计数清零）`,
    'AI 修正', { type: 'info' })
  fixingWord.value = row.word_id
  try {
    const r = await fixReportedKp(row.word_id)
    if (r.no_reported) ElMessage.warning('该词暂无达阈值的报错考点')
    else if (r.fixed) { ElMessage.success(`AI 已审校：删 ${r.deleted ?? 0} 条 / 改 ${r.fixed_n ?? 0} 条`); load() }
    else ElMessage.warning('修正失败（可能 dev-mock 或 LLM 返回为空）')
  } finally { fixingWord.value = '' }
}
async function remove(row: KpRelationItem) {
  await ElMessageBox.confirm(`删除这条考点?「${row.dim_label}: ${row.text}」`, '删除', { type: 'warning' })
  await deleteKpRelation(row.id); ElMessage.success('已删除'); load()
}
async function batchRemove() {
  if (!selected.value.length) return
  await ElMessageBox.confirm(`删除选中的 ${selected.value.length} 条考点?`, '批量删除', { type: 'warning' })
  await batchDeleteKpRelation(selected.value.map(r => r.id))
  ElMessage.success('已删除'); selected.value = []; load()
}
async function hideOne(row: KpRelationItem) {
  const { value } = await ElMessageBox.prompt('下架备注(可选)', `下架「${row.text}」`, {
    confirmButtonText: '确认下架', inputPlaceholder: '核实结论…', inputValue: '',
  }).catch(() => ({ value: null as string | null }))
  if (value === null) return
  await hideKpRelation(row.id, value || '')
  ElMessage.success('已下架（学生不可见；同 text 不会被 LLM 回写）'); load()
}
async function unhideOne(row: KpRelationItem) {
  await unhideKpRelation(row.id)
  ElMessage.success('已恢复上架'); load()
}
async function batchHide() {
  if (!selected.value.length) return
  await ElMessageBox.confirm(`下架选中的 ${selected.value.length} 条?`, '批量下架', { type: 'warning' })
  const r = await batchHideKpRelation(selected.value.map(x => x.id))
  ElMessage.success(`已下架 ${r.hidden} 条`); selected.value = []; load()
}

// —— 编辑弹框 ——
const editOpen = ref(false)
const editForm = reactive({ id: '', word: '', dim_label: '', text: '', zh: '', note: '' })
function openEdit(row: KpRelationItem) {
  Object.assign(editForm, { id: row.id, word: row.word, dim_label: row.dim_label, text: row.text, zh: row.zh, note: row.note })
  editOpen.value = true
}
async function saveEdit() {
  if (!editForm.text.trim()) { ElMessage.error('考点内容必填'); return }
  await editKpRelation(editForm.id, { text: editForm.text.trim(), zh: editForm.zh.trim(), note: editForm.note.trim() })
  ElMessage.success('已保存'); editOpen.value = false; load()
}

// —— 凭证明细 ——
const evOpen = ref(false)
const evList = ref<KpRelationReportItem[]>([])
const evLoading = ref(false)
const evTitle = ref('')
async function openEvidence(row: KpRelationItem) {
  evOpen.value = true; evLoading.value = true; evList.value = []
  evTitle.value = `${row.word} · ${row.dim_label} · ${row.text}`
  try { evList.value = await listKpRelationReports(row.id) } finally { evLoading.value = false }
}

// —— 审校记录 ——
const revOpen = ref(false)
const revList = ref<KpReviewRecord[]>([])
const revLoading = ref(false)
const revWord = ref('')
async function openReviews(row: KpRelationItem) {
  revOpen.value = true; revLoading.value = true; revList.value = []; revWord.value = row.word
  try { revList.value = await kpReviewRecords(row.word_id) } finally { revLoading.value = false }
}
function beforeText(rec: KpReviewRecord, id: string): string {
  const b = (rec.before || []).find(x => x.id === id)
  return b ? `【${b.dim}】${b.text}${b.zh ? ' / ' + b.zh : ''}` : id
}

onMounted(load)
</script>

<template>
  <div class="page">
    <div class="toolbar">
      <h2>考点复核</h2>
      <span class="hint">生成即上架；学生有凭证举报后在此核实。下架=对学生隐藏。AI 预隐=低峰扫中考高频近义/易混（只隐纯 LLM 行），可恢复。</span>
    </div>

    <div class="toolbar">
      <span>报错加权 ≥</span>
      <el-input-number v-model="minReport" :min="0" :max="99" size="small" @change="reload" />
      <el-divider direction="vertical" />
      <span>状态</span>
      <el-radio-group v-model="hiddenFilter" size="small" @change="reload">
        <el-radio-button value="exclude">待核实</el-radio-button>
        <el-radio-button value="only">已下架</el-radio-button>
        <el-radio-button value="ai_prehide">AI 预隐</el-radio-button>
        <el-radio-button value="all">全部</el-radio-button>
      </el-radio-group>
      <el-divider direction="vertical" />
      <span>AI 修正阈值</span>
      <el-input-number v-model="threshold" :min="1" :max="99" size="small" />
      <el-button size="small" @click="saveThreshold">保存阈值</el-button>
      <el-button size="small" type="warning" :disabled="!selected.length" @click="batchHide">
        批量下架{{ selected.length ? `(${selected.length})` : '' }}
      </el-button>
      <el-button size="small" type="danger" :disabled="!selected.length" @click="batchRemove">
        批量删除{{ selected.length ? `(${selected.length})` : '' }}
      </el-button>
    </div>

    <el-table v-loading="loading" :data="rows" border style="width: 100%"
              @selection-change="(rs: KpRelationItem[]) => selected = rs">
      <el-table-column type="selection" width="44" />
      <el-table-column prop="word" label="目标词" width="110" />
      <el-table-column label="义项" width="100">
        <template #default="{ row }"><span style="color:#909399">{{ row.gloss || '—' }}</span></template>
      </el-table-column>
      <el-table-column prop="dim_label" label="维度" width="100" />
      <el-table-column label="考点内容" min-width="220">
        <template #default="{ row }">
          <div style="line-height:1.5">
            <span>{{ row.text }}</span>
            <span v-if="row.zh" style="color:#606266"> / {{ row.zh }}</span>
            <div v-if="row.note" style="color:#909399;font-size:12px">备注: {{ row.note }}</div>
            <el-tag v-if="row.hidden" size="small" type="info" style="margin-top:4px">
              {{ row.hide_origin === 'ai_prehide' ? 'AI 预隐' : '已下架' }}
            </el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="凭证" min-width="200">
        <template #default="{ row }">
          <div v-if="row.evidence?.count" style="line-height:1.45;font-size:13px">
            <el-tag size="small" type="warning">{{ row.evidence.latest_reason_label || row.evidence.latest_reason }}</el-tag>
            <span style="color:#909399;margin-left:6px">×{{ row.evidence.count }}</span>
            <div v-if="row.evidence.latest_detail" style="color:#606266;margin-top:2px">{{ row.evidence.latest_detail }}</div>
            <div v-if="row.evidence.latest_suggested" style="color:#0F6E56">建议: {{ row.evidence.latest_suggested }}</div>
            <el-button size="small" text type="primary" @click="openEvidence(row)">全部凭证</el-button>
          </div>
          <span v-else style="color:#c0c4cc">无凭证明细</span>
        </template>
      </el-table-column>
      <el-table-column prop="report_count" label="加权" width="72" sortable align="center">
        <template #default="{ row }"><el-tag type="danger">{{ row.report_count }}</el-tag></template>
      </el-table-column>
      <el-table-column label="操作" width="340" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!row.hidden" size="small" type="warning" @click="hideOne(row)">下架</el-button>
          <el-button v-else size="small" type="success" @click="unhideOne(row)">恢复</el-button>
          <el-button size="small" type="primary" :loading="fixingWord === row.word_id" @click="aiFix(row)">AI 修正</el-button>
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" @click="openReviews(row)">审校</el-button>
          <el-button size="small" type="danger" text @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination class="pager" layout="total, prev, pager, next, jumper"
      :total="total" :page-size="pageSize" v-model:current-page="page" @current-change="load" />

    <AppDialog v-model="editOpen" title="编辑考点" width="560px">
      <div class="edit-head">{{ editForm.word }} · {{ editForm.dim_label }}</div>
      <el-form label-width="64px">
        <el-form-item label="内容"><el-input v-model="editForm.text" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="中文"><el-input v-model="editForm.zh" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="editForm.note" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editOpen = false">取消</el-button>
        <el-button type="primary" @click="saveEdit">保存</el-button>
      </template>
    </AppDialog>

    <AppDialog v-model="evOpen" :title="`举报凭证 · ${evTitle}`" width="640px">
      <div v-loading="evLoading">
        <el-empty v-if="!evLoading && !evList.length" description="暂无凭证" />
        <div v-for="e in evList" :key="e.id" class="ev-card">
          <div class="ev-h">
            <el-tag size="small">{{ e.reason_label }}</el-tag>
            <span class="ev-t">{{ e.created_at ? new Date(e.created_at).toLocaleString() : '' }}</span>
          </div>
          <div v-if="e.detail" class="ev-line">说明：{{ e.detail }}</div>
          <div v-if="e.suggested" class="ev-line ok">建议正确项：{{ e.suggested }}</div>
        </div>
      </div>
    </AppDialog>

    <AppDialog v-model="revOpen" :title="`审校记录 · ${revWord}`" width="680px">
      <div v-loading="revLoading">
        <el-empty v-if="!revLoading && !revList.length" description="暂无审校记录" />
        <el-timeline v-else>
          <el-timeline-item v-for="r in revList" :key="r.id"
            :timestamp="(r.created_at ? new Date(r.created_at).toLocaleString() : '') + ' · ' + (r.after?.trigger === 'reported' ? '报错修正' : 'AI自审')"
            placement="top">
            <div class="rev">
              <div v-if="r.after?.deleted?.length" class="rev-block">
                <div class="rev-h del">删除 {{ r.after.deleted.length }} 条</div>
                <div v-for="id in r.after.deleted" :key="id" class="rev-line">{{ beforeText(r, id) }}</div>
              </div>
              <div v-if="r.after?.fixed?.length" class="rev-block">
                <div class="rev-h ok">修正 {{ r.after.fixed.length }} 条</div>
                <div v-for="id in r.after.fixed" :key="id" class="rev-line">{{ beforeText(r, id) }}</div>
              </div>
              <div v-if="!r.after?.deleted?.length && !r.after?.fixed?.length" class="rev-line ok">
                复核 {{ (r.before || []).length }} 条,均判定正确无需改动
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
.edit-head { color: #606266; font-size: 13px; margin-bottom: 10px; }
.rev { background: #f7f8fa; border-radius: 8px; padding: 10px; }
.rev-block { margin-bottom: 8px; }
.rev-h { font-size: 12px; margin-bottom: 4px; }
.rev-h.del { color: #A32D2D; }
.rev-h.ok { color: #0F6E56; }
.rev-line { font-size: 13px; color: #303133; line-height: 1.5; }
.rev-line.ok { color: #909399; }
.ev-card { background: #f7f8fa; border-radius: 8px; padding: 10px 12px; margin-bottom: 8px; }
.ev-h { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.ev-t { color: #909399; font-size: 12px; }
.ev-line { font-size: 13px; color: #303133; line-height: 1.5; }
.ev-line.ok { color: #0F6E56; }
</style>
