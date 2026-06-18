<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import {
  listCurriculumUnits, generateUnitContent,
  uploadCurriculumPdf, generateFromPdf, generateSemester,
  reextractUnit, listUnitNodes,
  type UnitSegment, type UnitGenerateResult, type GenerateFromPdfOut,
} from '../api/admin'
import type { AdminCurriculumUnit, AdminUnitNodeItem } from '../types'

// ── 单元列表 ──────────────────────────────────────────────────────────────────
const rows = ref<AdminCurriculumUnit[]>([])
const loading = ref(false)
const generating = ref<Record<string, boolean>>({})

const filterTextbook = ref('')
const filterGrade    = ref('')
const filterSemester = ref('')

const textbookOptions = computed(() => [...new Set(rows.value.map(r => r.textbook_version))])
const gradeOptions    = computed(() => [...new Set(rows.value.map(r => r.grade))])
const semesterOptions = computed(() => [...new Set(rows.value.map(r => r.semester))])

const filteredRows = computed(() => rows.value.filter(r => {
  if (filterTextbook.value && r.textbook_version !== filterTextbook.value) return false
  if (filterGrade.value    && r.grade            !== filterGrade.value)    return false
  if (filterSemester.value && r.semester         !== filterSemester.value) return false
  return true
}))

async function load() {
  loading.value = true
  try { rows.value = await listCurriculumUnits() }
  catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}

async function onGenerate(row: AdminCurriculumUnit) {
  await ElMessageBox.confirm(
    `确认为「${row.textbook_version} ${row.grade} ${row.semester}学期 Unit ${row.unit_no}」生成内容？\n草稿状态，需在"内容审核"发布后学生可见。`,
    '生成确认', { type: 'warning', confirmButtonText: '生成', cancelButtonText: '取消' },
  )
  generating.value[row.unit_id] = true
  try {
    const result = await generateUnitContent(row.unit_id)
    ElMessage.success(`生成完成！KP 数: ${result.kp_count}，内容条数: ${result.content_count}`)
    const idx = rows.value.findIndex(r => r.unit_id === row.unit_id)
    if (idx !== -1) rows.value[idx] = { ...rows.value[idx], ...result }
  } catch (e: any) {
    ElMessage.error(e?.message || '生成失败')
  } finally {
    generating.value[row.unit_id] = false
  }
}

// ── 知识图谱对齐（R1）────────────────────────────────────────
const aligning = ref<Record<string, boolean>>({})
const nodesDlg = ref(false)
const nodesLoading = ref(false)
const unitNodes = ref<AdminUnitNodeItem[]>([])
const nodesUnitTitle = ref('')

async function onAlign(row: AdminCurriculumUnit) {
  aligning.value[row.unit_id] = true
  try {
    const r = await reextractUnit(row.unit_id)
    ElMessage.success(`对齐完成：命中 ${r.matched}、新建边 ${r.edges_created}、待审候选 ${r.candidate}`)
  } catch (e: any) {
    ElMessage.error(e?.message || '对齐失败')
  } finally {
    aligning.value[row.unit_id] = false
  }
}

async function onViewNodes(row: AdminCurriculumUnit) {
  nodesUnitTitle.value = `${row.textbook_version} ${row.grade} ${row.semester} U${row.unit_no}`
  nodesDlg.value = true
  nodesLoading.value = true
  try {
    unitNodes.value = (await listUnitNodes(row.unit_id)).items
  } catch (e: any) {
    ElMessage.error(e?.message || '加载失败')
  } finally {
    nodesLoading.value = false
  }
}

function rateColor(rate: number) {
  if (rate >= 1) return '#67C23A'
  if (rate > 0)  return '#E6A23C'
  return '#F56C6C'
}

// ── PDF 上传 Dialog ──────────────────────────────────────────────────────────

const VERSIONS     = ['译林版', '人教版', '外研版', '北师大版']
const GRADES       = ['小学5年级', '小学6年级', '七年级', '八年级', '九年级']
const SEMS         = ['上', '下']

const pdfDialogVisible = ref(false)
const pdfStep          = ref(0)          // 0=信息, 1=上传, 2=分单元, 3=生成中/结果

// step 0
const pdfTextbook = ref('译林版')
const pdfGrade    = ref('七年级')
const pdfSemester = ref('上')

// step 1
const pdfFile          = ref<File | null>(null)
const pdfUploading     = ref(false)
const pdfFileId        = ref('')
const pdfTotalPages    = ref(0)
const pdfAutoSuccess   = ref(false)
const pdfPageOffset    = ref(0)        // 印刷页码 = PDF 页序 − offset
const pdfUploadErr     = ref('')

function printedPage(pdfNo: number): string {
  return pdfPageOffset.value > 0 ? `印刷 P${pdfNo - pdfPageOffset.value}` : ''
}

// step 2
const segments     = ref<UnitSegment[]>([])
const segErr       = ref('')

// step 3
const pdfGenerating = ref(false)
const pdfGenResult  = ref<GenerateFromPdfOut | null>(null)

function openPdfDialog() {
  pdfStep.value       = 0
  pdfFile.value       = null
  pdfFileId.value     = ''
  pdfTotalPages.value = 0
  pdfAutoSuccess.value= false
  pdfPageOffset.value = 0
  pdfUploadErr.value  = ''
  segments.value      = []
  segErr.value        = ''
  pdfGenResult.value  = null
  pdfDialogVisible.value = true
}

function onFileChange(uploadFile: any) {
  pdfFile.value = uploadFile.raw as File
  pdfUploadErr.value = ''
}

async function doUpload() {
  if (!pdfFile.value) { ElMessage.warning('请先选择 PDF 文件'); return }
  pdfUploading.value = true
  pdfUploadErr.value = ''
  try {
    const out = await uploadCurriculumPdf(pdfFile.value)
    pdfFileId.value     = out.file_id
    pdfTotalPages.value = out.total_pages
    pdfAutoSuccess.value= out.auto_split_success
    pdfPageOffset.value = out.page_offset ?? 0
    segments.value      = out.auto_split_success
      ? out.auto_segments.map(s => ({ ...s }))
      : []
    pdfStep.value = 2
  } catch (e: any) {
    pdfUploadErr.value = e?.message || '上传失败'
  } finally {
    pdfUploading.value = false
  }
}

function addSegment() {
  const last    = segments.value[segments.value.length - 1]
  const nextNo  = segments.value.length + 1
  const start   = last ? last.end_page + 1 : 1
  segments.value.push({ unit_no: nextNo, start_page: start, end_page: Math.min(start + 19, pdfTotalPages.value || 999), detected_title: null })
}

function removeSegment(i: number) { segments.value.splice(i, 1) }

async function startPdfGenerate() {
  segErr.value = ''
  if (!segments.value.length) { segErr.value = '请至少添加一个单元'; return }
  for (const s of segments.value) {
    if (s.end_page < s.start_page) { segErr.value = `Unit ${s.unit_no} 结束页不能小于起始页`; return }
  }
  pdfStep.value    = 3
  pdfGenerating.value = true
  pdfGenResult.value  = null
  try {
    pdfGenResult.value = await generateFromPdf(pdfFileId.value, {
      textbook_version: pdfTextbook.value,
      grade: pdfGrade.value,
      semester: pdfSemester.value,
      segments: segments.value,
    })
    if (pdfGenResult.value.success_count > 0) {
      ElMessage.success(`成功生成 ${pdfGenResult.value.success_count} 个单元`)
      await load()
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '生成失败')
  } finally {
    pdfGenerating.value = false
  }
}

// ── 一键生成学期 Dialog ───────────────────────────────────────────────────────

const semDialogVisible = ref(false)
const semTextbook      = ref('译林版')
const semGrade         = ref('七年级')
const semSemester      = ref('上')
const semUnitCount     = ref(6)
const semGenerating    = ref(false)
const semResults       = ref<UnitGenerateResult[]>([])

function openSemDialog() {
  semResults.value    = []
  semGenerating.value = false
  semDialogVisible.value = true
}

async function doGenerateSem() {
  await ElMessageBox.confirm(
    `将用 DeepSeek AI 重新生成「${semTextbook.value} ${semGrade.value} ${semSemester.value}学期」全部 ${semUnitCount.value} 个单元内容，并覆盖已有数据。确认继续？`,
    '确认生成', { type: 'warning', confirmButtonText: '开始生成', cancelButtonText: '取消' },
  )
  semGenerating.value = true
  semResults.value    = []
  try {
    const rows = await generateSemester({
      textbook_version: semTextbook.value,
      grade: semGrade.value,
      semester: semSemester.value,
      unit_count: semUnitCount.value,
    })
    semResults.value = rows as UnitGenerateResult[]
    const ok = rows.filter(r => r.status === 'ok').length
    ElMessage.success(`生成完成，成功 ${ok}/${rows.length} 个单元`)
    await load()
  } catch (e: any) {
    ElMessage.error(e?.message || '生成失败')
  } finally {
    semGenerating.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <!-- 工具栏 -->
    <div class="toolbar">
      <el-select v-model="filterTextbook" placeholder="教材版本" clearable style="width:140px">
        <el-option v-for="t in textbookOptions" :key="t" :label="t" :value="t" />
      </el-select>
      <el-select v-model="filterGrade" placeholder="年级" clearable style="width:140px">
        <el-option v-for="g in gradeOptions" :key="g" :label="g" :value="g" />
      </el-select>
      <el-select v-model="filterSemester" placeholder="学期" clearable style="width:100px">
        <el-option v-for="s in semesterOptions" :key="s" :label="s+'学期'" :value="s" />
      </el-select>
      <el-button @click="load" :loading="loading">🔄 刷新</el-button>
      <span class="stat-txt">
        共 {{ filteredRows.length }} 个单元 ·
        已完成 {{ filteredRows.filter(r => r.content_rate >= 1).length }} 个
      </span>
      <div style="flex:1" />
      <el-button type="success" @click="openSemDialog">🤖 一键 AI 生成学期</el-button>
      <el-button type="primary" @click="openPdfDialog">📄 上传教材 PDF</el-button>
    </div>

    <!-- 单元表格 -->
    <el-table v-loading="loading" :data="filteredRows" border style="width:100%">
      <el-table-column prop="textbook_version" label="教材"   width="90" />
      <el-table-column prop="grade"            label="年级"   width="110" />
      <el-table-column prop="semester"         label="学期"   width="70">
        <template #default="{ row }">{{ row.semester }}学期</template>
      </el-table-column>
      <el-table-column prop="unit_no"    label="Unit"  width="60" align="center" />
      <el-table-column prop="unit_title" label="单元标题" min-width="160" show-overflow-tooltip />
      <el-table-column prop="kp_count"   label="KP数"  width="70" align="center" />
      <el-table-column label="内容完成度" width="200">
        <template #default="{ row }">
          <div style="display:flex;align-items:center;gap:8px">
            <el-progress :percentage="Math.round(row.content_rate * 100)" :color="rateColor(row.content_rate)" :stroke-width="8" style="flex:1" />
            <span style="font-size:12px;white-space:nowrap;color:#606266">{{ row.content_count }}/{{ row.kp_count * 6 }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="290" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" :loading="generating[row.unit_id]" @click="onGenerate(row)">
            🤖 生成内容
          </el-button>
          <el-button size="small" type="success" :loading="aligning[row.unit_id]" @click="onAlign(row)">
            🧩 对齐图谱
          </el-button>
          <el-button size="small" @click="onViewNodes(row)">查看节点</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ── 单元知识图谱节点 Dialog ── -->
    <el-dialog v-model="nodesDlg" :title="`单元知识图谱节点 · ${nodesUnitTitle}`" width="560px">
      <el-table v-loading="nodesLoading" :data="unitNodes" border style="width:100%">
        <el-table-column prop="name" label="知识点" min-width="160" show-overflow-tooltip />
        <el-table-column prop="axis" label="轴" width="80" />
        <el-table-column prop="node_kind" label="子类型" width="100" />
        <el-table-column prop="source" label="来源" width="110" />
      </el-table>
      <el-empty v-if="!nodesLoading && !unitNodes.length" description="该单元暂无对齐的知识图谱节点" />
    </el-dialog>

    <!-- ── PDF 上传 Dialog ── -->
    <el-dialog
      v-model="pdfDialogVisible"
      title="上传教材 PDF 生成课程内容"
      width="680px"
      :close-on-click-modal="false"
    >
      <el-steps :active="pdfStep" finish-status="success" style="margin-bottom:28px">
        <el-step title="教材信息" />
        <el-step title="上传文件" />
        <el-step title="单元划分" />
        <el-step title="生成内容" />
      </el-steps>

      <!-- Step 0：教材信息 -->
      <div v-if="pdfStep === 0">
        <el-form label-width="90px">
          <el-form-item label="教材版本">
            <el-select v-model="pdfTextbook" style="width:200px">
              <el-option v-for="v in VERSIONS" :key="v" :label="v" :value="v" />
            </el-select>
          </el-form-item>
          <el-form-item label="年级">
            <el-select v-model="pdfGrade" style="width:200px">
              <el-option v-for="g in GRADES" :key="g" :label="g" :value="g" />
            </el-select>
          </el-form-item>
          <el-form-item label="学期">
            <el-select v-model="pdfSemester" style="width:200px">
              <el-option v-for="s in SEMS" :key="s" :label="s+'学期'" :value="s" />
            </el-select>
          </el-form-item>
        </el-form>
        <div style="text-align:right;margin-top:16px">
          <el-button type="primary" @click="pdfStep = 1">下一步</el-button>
        </div>
      </div>

      <!-- Step 1：上传文件 -->
      <div v-if="pdfStep === 1">
        <div class="meta-tag">{{ pdfTextbook }} · {{ pdfGrade }} · {{ pdfSemester }}学期</div>
        <el-upload
          drag
          :auto-upload="false"
          :limit="1"
          accept=".pdf"
          :on-change="onFileChange"
          :show-file-list="true"
          style="margin-bottom:16px"
        >
          <el-icon style="font-size:40px;color:#c0c4cc"><UploadFilled /></el-icon>
          <div style="margin-top:8px;font-size:14px;color:#606266">将 PDF 拖到此处，或<em style="color:#409eff">点击选择</em></div>
          <div style="font-size:12px;color:#909399;margin-top:4px">仅支持 .pdf 格式，上限 100MB</div>
        </el-upload>
        <el-alert v-if="pdfUploadErr" :title="pdfUploadErr" type="error" style="margin-bottom:12px" :closable="false" />
        <div style="text-align:right;display:flex;justify-content:space-between">
          <el-button @click="pdfStep = 0">上一步</el-button>
          <el-button type="primary" :loading="pdfUploading" :disabled="!pdfFile" @click="doUpload">
            上传并识别单元
          </el-button>
        </div>
      </div>

      <!-- Step 2：单元划分 -->
      <div v-if="pdfStep === 2">
        <div class="meta-tag">{{ pdfTextbook }} · {{ pdfGrade }} · {{ pdfSemester }}学期 · 共 {{ pdfTotalPages }} 页</div>

        <el-alert
          v-if="pdfAutoSuccess"
          :title="`✅ 自动识别到 ${segments.length} 个单元，可直接生成。也可手动调整下方分界。`"
          type="success" :closable="false" style="margin-bottom:12px"
        />
        <el-alert
          v-else
          title="未能自动识别单元分界，请手动填写各单元起止页码。"
          type="warning" :closable="false" style="margin-bottom:12px"
        />
        <div v-if="pdfPageOffset > 0" class="offset-tip">
          下方为 PDF 页序;本书 PDF 比印刷页码多 {{ pdfPageOffset }} 页 → 印刷页码 = PDF 页序 − {{ pdfPageOffset }}(各页已标「印刷 P」)
        </div>

        <!-- 分段列表 -->
        <el-table :data="segments" border size="small" style="margin-bottom:12px">
          <el-table-column label="单元" width="80" align="center">
            <template #default="{ row }">Unit {{ row.unit_no }}</template>
          </el-table-column>
          <el-table-column label="起始页(PDF)" width="120" align="center">
            <template #default="{ row }">
              <el-input-number v-model="row.start_page" :min="1" :max="pdfTotalPages" size="small" controls-position="right" />
              <div v-if="pdfPageOffset > 0" class="printed-hint">{{ printedPage(row.start_page) }}</div>
            </template>
          </el-table-column>
          <el-table-column label="结束页(PDF)" width="120" align="center">
            <template #default="{ row }">
              <el-input-number v-model="row.end_page" :min="row.start_page" :max="pdfTotalPages" size="small" controls-position="right" />
              <div v-if="pdfPageOffset > 0" class="printed-hint">{{ printedPage(row.end_page) }}</div>
            </template>
          </el-table-column>
          <el-table-column label="识别标题" min-width="120" show-overflow-tooltip>
            <template #default="{ row }">
              <span style="color:#909399;font-size:12px">{{ row.detected_title || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="" width="60" align="center">
            <template #default="{ $index }">
              <el-button link type="danger" size="small" @click="removeSegment($index)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-button link type="primary" @click="addSegment" style="margin-bottom:12px">+ 添加单元</el-button>

        <el-alert v-if="segErr" :title="segErr" type="error" :closable="false" style="margin-bottom:12px" />

        <div style="display:flex;justify-content:space-between">
          <el-button @click="pdfStep = 1">上一步</el-button>
          <el-button type="primary" :disabled="!segments.length" @click="startPdfGenerate">
            开始生成（{{ segments.length }} 个单元）
          </el-button>
        </div>
      </div>

      <!-- Step 3：生成中 / 结果 -->
      <div v-if="pdfStep === 3">
        <div v-if="pdfGenerating" class="gen-loading">
          <el-icon class="spinning"><i class="el-icon-loading" /></el-icon>
          <div style="font-size:15px;font-weight:600;margin-top:12px">AI 生成中，请稍候…</div>
          <div style="font-size:13px;color:#909399;margin-top:6px">
            约 {{ segments.length * 20 }}–{{ segments.length * 30 }} 秒，请勿关闭窗口
          </div>
          <el-progress :percentage="0" status="" style="width:300px;margin-top:16px" :striped="true" :striped-flow="true" :duration="10" />
        </div>

        <div v-else-if="pdfGenResult">
          <div class="result-summary">
            <el-tag type="success" size="large">✅ 成功 {{ pdfGenResult.success_count }} 个单元</el-tag>
            <el-tag v-if="pdfGenResult.error_count" type="danger" size="large" style="margin-left:8px">
              ❌ 失败 {{ pdfGenResult.error_count }} 个单元
            </el-tag>
          </div>
          <el-table :data="pdfGenResult.results" border size="small" style="margin-top:16px">
            <el-table-column label="状态" width="60" align="center">
              <template #default="{ row }">
                <el-tag :type="row.status === 'ok' ? 'success' : 'danger'" size="small">
                  {{ row.status === 'ok' ? '✅' : '❌' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="单元" width="70" align="center">
              <template #default="{ row }">Unit {{ row.unit_no }}</template>
            </el-table-column>
            <el-table-column prop="unit_title" label="标题" min-width="140" show-overflow-tooltip />
            <el-table-column label="KP / 词" width="90" align="center">
              <template #default="{ row }">
                <span v-if="row.status === 'ok'">{{ row.kp_count }} / {{ row.word_count }}</span>
                <span v-else style="color:#F56C6C;font-size:12px">{{ row.error }}</span>
              </template>
            </el-table-column>
          </el-table>
          <div style="text-align:right;margin-top:16px">
            <el-button @click="pdfDialogVisible = false">关闭</el-button>
          </div>
        </div>
      </div>
    </el-dialog>

    <!-- ── 一键 AI 生成学期 Dialog ── -->
    <el-dialog v-model="semDialogVisible" title="一键 AI 生成学期内容" width="500px" :close-on-click-modal="false">
      <el-form label-width="90px" style="margin-bottom:8px">
        <el-form-item label="教材版本">
          <el-select v-model="semTextbook" style="width:200px">
            <el-option v-for="v in VERSIONS" :key="v" :label="v" :value="v" />
          </el-select>
        </el-form-item>
        <el-form-item label="年级">
          <el-select v-model="semGrade" style="width:200px">
            <el-option v-for="g in GRADES" :key="g" :label="g" :value="g" />
          </el-select>
        </el-form-item>
        <el-form-item label="学期">
          <el-select v-model="semSemester" style="width:200px">
            <el-option v-for="s in SEMS" :key="s" :label="s+'学期'" :value="s" />
          </el-select>
        </el-form-item>
        <el-form-item label="单元数">
          <el-input-number v-model="semUnitCount" :min="1" :max="12" />
        </el-form-item>
      </el-form>

      <el-alert
        title="⚠️ 将覆盖该学期已有课程内容，直接调用 DeepSeek AI 生成，约 60–120 秒。"
        type="warning" :closable="false" style="margin-bottom:16px"
      />

      <!-- 生成结果列表 -->
      <el-table v-if="semResults.length" :data="semResults" border size="small" style="margin-bottom:16px">
        <el-table-column label="状态" width="60" align="center">
          <template #default="{ row }">
            <el-tag :type="row.status === 'ok' ? 'success' : 'danger'" size="small">
              {{ row.status === 'ok' ? '✅' : '❌' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="单元" width="70" align="center">
          <template #default="{ row }">Unit {{ row.unit_no }}</template>
        </el-table-column>
        <el-table-column prop="unit_title" label="标题" min-width="120" show-overflow-tooltip />
        <el-table-column label="KP/词" width="80" align="center">
          <template #default="{ row }">{{ row.kp_count }}/{{ row.word_count }}</template>
        </el-table-column>
      </el-table>

      <template #footer>
        <el-button @click="semDialogVisible = false">关闭</el-button>
        <el-button type="primary" :loading="semGenerating" :disabled="semGenerating" @click="doGenerateSem">
          {{ semGenerating ? `生成中（预计 ${semUnitCount * 20}s）…` : '开始生成' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex; gap: 12px; align-items: center;
  flex-wrap: wrap; margin-bottom: 16px;
}
.stat-txt { color: #909399; font-size: 13px; }
.meta-tag {
  display: inline-block; background: #f0f9ff; color: #0369a1;
  font-size: 13px; padding: 4px 10px; border-radius: 4px; margin-bottom: 16px;
}
.gen-loading {
  display: flex; flex-direction: column; align-items: center;
  padding: 40px 0; gap: 8px;
}
.spinning { font-size: 36px; animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.result-summary { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.offset-tip { color: #b45309; background: #fffbeb; font-size: 12px;
  padding: 6px 10px; border-radius: 4px; margin-bottom: 10px; }
.printed-hint { color: #2563eb; font-size: 11px; margin-top: 2px; }
</style>
