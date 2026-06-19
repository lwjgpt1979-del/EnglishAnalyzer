<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import {
  listPlatformQuestions, extractRealQuestions, getExtractJob, bulkImportRealQuestions,
  genSimFromReal, reviewPlatformQuestion, listRegions, uploadImageViaPresign,
  type PlatformQuestion,
} from '../api/admin'

// ── 列表 ──
const typeFilter = ref('')          // ''=全部, real, sim
const statusFilter = ref('')
const rows = ref<PlatformQuestion[]>([])
const total = ref(0)
const loading = ref(false)
const typeOpts = [{ label: '全部', value: '' }, { label: '真题', value: 'real' }, { label: '仿真', value: 'sim' }]
const statusOpts = ['', 'draft', 'published', 'retired']

async function load() {
  loading.value = true
  try {
    const data = await listPlatformQuestions({
      type: typeFilter.value || undefined, status: statusFilter.value || undefined, limit: 50,
    })
    rows.value = data.items
    total.value = data.total
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}

async function onGenSim(row: PlatformQuestion) {
  const { value } = await ElMessageBox.prompt('预生成几道仿真?', '派生仿真', {
    inputValue: '3', inputPattern: /^[1-9]\d*$/, inputErrorMessage: '请输入正整数',
  })
  const r = await genSimFromReal(row.id, Number(value))
  ElMessage.success(`已生成 ${r.generated} 道仿真`)
  await load()
}

async function onReview(row: PlatformQuestion, approve: boolean) {
  await ElMessageBox.confirm(`确认${approve ? '通过发布' : '驳回'}该题?`, '确认', { type: 'warning' })
  await reviewPlatformQuestion(row.id, approve)
  ElMessage.success(approve ? '已发布' : '已驳回')
  await load()
}

// ── 上传抽题向导 ──
const VERSIONS = ['译林版', '人教版', '外研版', '北师大版']
const STAGES = ['小', '初', '高']          // 学段(对接 stage_hint:小/初/高)
const STAGE_LABEL: Record<string, string> = { 小: '小学', 初: '初中', 高: '高中' }
const GRADES: Record<string, string[]> = {
  小: ['三年级', '四年级', '五年级', '六年级'],
  初: ['七年级', '八年级', '九年级'],
  高: ['高一', '高二', '高三'],
}
const dlg = ref(false)
const step = ref(0)                 // 0=选源, 1=抽题中, 2=校对
// 批次元信息:教材+学段 必选;年级/学期/地区 选填
const EXAM_TYPES = [{ label: '普通(无)', value: '' }, { label: '中考', value: '中考' }, { label: '高考', value: '高考' }]
const QUESTION_TYPES = ['单选', '填空', '完型', '阅读', '写作', '判断', '连线']  // 与 ai_question_type_enum 对齐
const metaTextbook = ref('译林版')
const metaStage = ref('初')
const metaGrade = ref('')
const metaSemester = ref('')
const metaExamType = ref('')
// 地区:后端 region 表懒加载级联(省→市→区县→乡镇),code 与学生 user.city_code 同源
const regionPath = ref<string[]>([])
const regionLabels = ref<string[]>([])
const regionCascader = ref()
const regionProps = {
  lazy: true,
  async lazyLoad(node: any, resolve: (n: any[]) => void) {
    try {
      const rows = await listRegions(node.value || undefined)
      resolve(rows.map(r => ({ value: r.code, label: r.name, leaf: r.leaf })))
    } catch { resolve([]) }
  },
}
function onRegionChange() {
  const nodes = regionCascader.value?.getCheckedNodes?.()
  regionLabels.value = nodes?.[0]?.pathLabels || []
}
const pickedFile = ref<File | null>(null)       // PDF / Word(.docx)
const pickedImages = ref<File[]>([])             // 直传图片(走 OCR)
const uploadingImg = ref(false)
const imageUrlsText = ref('')
const extracting = ref(false)
const importing = ref(false)
let pollTimer: ReturnType<typeof setTimeout> | null = null

interface EditRow {
  question_no?: string | null; question_type: string; stem: string
  answer: string; explanation: string; difficulty: number | null; kp_names: string
}
const editRows = ref<EditRow[]>([])

function stopPoll() { if (pollTimer) { clearTimeout(pollTimer); pollTimer = null } }

function openDlg() {
  stopPoll()
  step.value = 0; pickedFile.value = null; pickedImages.value = []; uploadingImg.value = false; imageUrlsText.value = ''
  metaGrade.value = ''; metaSemester.value = ''; metaExamType.value = ''
  regionPath.value = []; regionLabels.value = []
  extracting.value = false; importing.value = false; editRows.value = []
  dlg.value = true
}

function batchMeta(): Record<string, unknown> {
  const m: Record<string, unknown> = { textbook_version: metaTextbook.value, stage: metaStage.value }
  if (metaGrade.value) m.grade = metaGrade.value
  if (metaSemester.value) m.semester = metaSemester.value
  if (metaExamType.value) m.exam_type = metaExamType.value
  const path = regionPath.value
  if (path.length) {        // code 与学生 user.city_code 同源 → 中考可按地区匹配
    m.province_code = path[0]
    if (path[1]) m.city_code = path[1]      // 市(4位)
    m.region_code = path[path.length - 1]   // 选到的最细级(可到区县/乡镇)
    if (regionLabels.value.length) m.region_name = regionLabels.value.join('')
  }
  return m
}

function onFileChange(f: any) { pickedFile.value = f.raw as File }
function onImagesChange(_f: any, list: any[]) { pickedImages.value = list.map(x => x.raw).filter(Boolean) }

async function startExtract() {
  if (!metaTextbook.value || !metaStage.value) { ElMessage.warning('请先选教材版本和学段'); return }
  const typedUrls = imageUrlsText.value.split('\n').map(s => s.trim()).filter(Boolean)
  if (!pickedFile.value && !pickedImages.value.length && !typedUrls.length) {
    ElMessage.warning('请选 PDF/Word 文件,或上传/粘贴图片'); return
  }
  extracting.value = true; step.value = 1
  try {
    let urls = typedUrls
    if (pickedImages.value.length) {        // 图片先直传 COS 拿 file_url
      uploadingImg.value = true
      const uploaded = await Promise.all(pickedImages.value.map(f => uploadImageViaPresign(f)))
      urls = [...uploaded, ...typedUrls]
      uploadingImg.value = false
    }
    // file(PDF/Word)优先;无 file 时走图片/URL 的 OCR
    const { job_id } = await extractRealQuestions({ file: pickedFile.value || undefined, imageUrls: urls })
    pollExtract(job_id)
  } catch (e: any) { extracting.value = false; uploadingImg.value = false; ElMessage.error(e?.message || '抽题失败') }
}

async function pollExtract(jobId: string) {
  try {
    const job = await getExtractJob(jobId)
    if (job.status === 'running') { pollTimer = setTimeout(() => pollExtract(jobId), 2500); return }
    extracting.value = false
    if (job.status === 'failed') { ElMessage.error(`抽题失败:${job.error || ''}`); step.value = 0; return }
    editRows.value = job.parsed.map(p => ({
      question_no: p.question_no, question_type: p.question_type || '单选',
      stem: p.stem || '', answer: p.answer || '', explanation: p.explanation || '',
      difficulty: null, kp_names: '',
    }))
    step.value = 2
    if (!editRows.value.length) ElMessage.warning('未抽到题,请检查文件或改用图片上传')
  } catch (e: any) { extracting.value = false; ElMessage.error(e?.message || '查询失败') }
}

async function doImport() {
  const items = editRows.value.filter(r => r.stem.trim()).map(r => ({
    stem: r.stem.trim(), answer: r.answer || null, question_type: r.question_type || null,
    explanation: r.explanation || null, difficulty: r.difficulty, question_no: r.question_no,
    kp_names: r.kp_names.split(/[,，]/).map(s => s.trim()).filter(Boolean),
  }))
  if (!items.length) { ElMessage.warning('没有可导入的题'); return }
  importing.value = true
  try {
    const r = await bulkImportRealQuestions(items, {
      status: 'published', stage_hint: metaStage.value, meta: batchMeta(),
    })
    ElMessage.success(`导入 ${r.imported} 题${r.failed ? `,失败 ${r.failed}` : ''}`)
    dlg.value = false
    await load()
  } catch (e: any) { ElMessage.error(e?.message || '导入失败') }
  finally { importing.value = false }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="toolbar">
      <span>类型:</span>
      <el-select v-model="typeFilter" style="width:110px" @change="load">
        <el-option v-for="t in typeOpts" :key="t.value" :label="t.label" :value="t.value" />
      </el-select>
      <span style="margin-left:16px">状态:</span>
      <el-select v-model="statusFilter" style="width:120px" @change="load">
        <el-option v-for="s in statusOpts" :key="s" :label="s || '全部'" :value="s" />
      </el-select>
      <el-button style="margin-left:12px" type="primary" @click="openDlg">+ 上传真题</el-button>
      <el-button @click="load">刷新</el-button>
      <span class="hint">真题挂知识节点;有真题的点其直生备选自动下架,可派生仿真供学生"有源"练习。共 {{ total }} 条</span>
    </div>

    <el-table v-loading="loading" :data="rows" border style="width:100%">
      <el-table-column label="类型" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.type === 'real' ? 'danger' : 'info'" size="small">
            {{ row.type === 'real' ? '真题' : '仿真' }}<span v-if="row.is_fallback">·备</span>
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="question_type" label="题型" width="80" />
      <el-table-column prop="stem" label="题干" min-width="280" show-overflow-tooltip />
      <el-table-column prop="answer" label="答案" width="90" show-overflow-tooltip />
      <el-table-column prop="difficulty" label="难度" width="60" align="center" />
      <el-table-column prop="status" label="状态" width="90" />
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button v-if="row.type === 'real'" size="small" @click="onGenSim(row)">派生仿真</el-button>
          <el-button v-if="row.status !== 'published'" size="small" type="success" @click="onReview(row, true)">发布</el-button>
          <el-button v-if="row.status !== 'retired'" size="small" type="danger" @click="onReview(row, false)">驳回</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dlg" title="上传真题 → 抽题 → 校对导入" width="900px" @close="stopPoll" :close-on-click-modal="false">
      <!-- 选源 -->
      <div v-if="step === 0">
        <el-form :inline="true" label-width="72px" style="margin-bottom:10px">
          <el-form-item label="教材版本" required>
            <el-select v-model="metaTextbook" style="width:140px">
              <el-option v-for="v in VERSIONS" :key="v" :label="v" :value="v" />
            </el-select>
          </el-form-item>
          <el-form-item label="学段" required>
            <el-select v-model="metaStage" style="width:100px" @change="metaGrade = ''">
              <el-option v-for="s in STAGES" :key="s" :label="STAGE_LABEL[s]" :value="s" />
            </el-select>
          </el-form-item>
          <el-form-item label="年级">
            <el-select v-model="metaGrade" clearable placeholder="选填" style="width:120px">
              <el-option v-for="g in GRADES[metaStage]" :key="g" :label="g" :value="g" />
            </el-select>
          </el-form-item>
          <el-form-item label="上下册">
            <el-select v-model="metaSemester" clearable placeholder="选填" style="width:100px">
              <el-option label="上册" value="上" /><el-option label="下册" value="下" />
            </el-select>
          </el-form-item>
          <el-form-item label="考试类型">
            <el-select v-model="metaExamType" style="width:120px">
              <el-option v-for="e in EXAM_TYPES" :key="e.value" :label="e.label" :value="e.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="地区">
            <el-cascader ref="regionCascader" v-model="regionPath" :props="regionProps"
              clearable placeholder="选填:省→市(中考按市)" style="width:240px" @change="onRegionChange" />
          </el-form-item>
        </el-form>
        <el-alert type="info" :closable="false" style="margin-bottom:12px"
          title="教材+学段必选(挂知识节点/匹配);年级/上下册/地区选填存档。文本版 PDF / Word(.docx)直接取字;扫描版/拍照请上传图片走 OCR。文件优先,有文件时忽略图片。" />
        <el-upload drag :auto-upload="false" :limit="1" :on-change="onFileChange" accept=".pdf,.docx">
          <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
          <div class="el-upload__text">拖入或点击选择 <b>真题 PDF / Word(.docx)</b>(文本版)</div>
        </el-upload>
        <div style="margin:16px 0 6px;color:#909399;font-size:13px">或:上传真题图片(扫描/拍照,走 OCR,可多张)</div>
        <el-upload :auto-upload="false" list-type="picture-card" multiple
          :on-change="onImagesChange" :on-remove="onImagesChange" accept="image/*">
          <el-icon><UploadFilled /></el-icon>
        </el-upload>
        <div style="margin:10px 0 6px;color:#c0c4cc;font-size:12px">高级:也可直接粘贴图片 URL(每行一个)</div>
        <el-input v-model="imageUrlsText" type="textarea" :rows="2" placeholder="https://.../p1.jpg&#10;https://.../p2.jpg" />
        <div style="text-align:right;margin-top:16px">
          <el-button type="primary" :loading="uploadingImg" @click="startExtract">
            {{ uploadingImg ? '图片上传中…' : '开始抽题' }}
          </el-button>
        </div>
      </div>

      <!-- 抽题中 -->
      <div v-else-if="step === 1" class="gen-loading">
        <div style="font-size:15px;font-weight:600">AI 抽题中…</div>
        <div style="font-size:13px;color:#909399;margin-top:6px">整卷拆题约 30–90 秒,可关窗口稍后重开</div>
        <el-progress :percentage="100" :indeterminate="true" :duration="2" style="width:320px;margin-top:16px" />
      </div>

      <!-- 校对 -->
      <div v-else-if="step === 2">
        <div style="margin-bottom:8px;color:#606266">抽出 {{ editRows.length }} 题,核对/编辑后导入(可填 KP 名挂知识节点)</div>
        <el-table :data="editRows" border size="small" max-height="440">
          <el-table-column label="#" width="48" align="center"><template #default="{ row }">{{ row.question_no }}</template></el-table-column>
          <el-table-column label="题干" min-width="240">
            <template #default="{ row }"><el-input v-model="row.stem" type="textarea" :rows="2" /></template>
          </el-table-column>
          <el-table-column label="答案" width="90"><template #default="{ row }"><el-input v-model="row.answer" /></template></el-table-column>
          <el-table-column label="题型" width="96"><template #default="{ row }">
            <el-select v-model="row.question_type" size="small">
              <el-option v-for="t in QUESTION_TYPES" :key="t" :label="t" :value="t" />
            </el-select>
          </template></el-table-column>
          <el-table-column label="难度" width="80"><template #default="{ row }"><el-input-number v-model="row.difficulty" :min="1" :max="5" size="small" controls-position="right" /></template></el-table-column>
          <el-table-column label="知识点(逗号分隔)" width="160"><template #default="{ row }"><el-input v-model="row.kp_names" placeholder="如:定语从句" /></template></el-table-column>
          <el-table-column label="" width="50" align="center">
            <template #default="{ $index }"><el-button size="small" type="danger" link @click="editRows.splice($index, 1)">删</el-button></template>
          </el-table-column>
        </el-table>
        <div style="text-align:right;margin-top:16px">
          <el-button @click="step = 0">上一步</el-button>
          <el-button type="primary" :loading="importing" @click="doImport">导入 {{ editRows.length }} 题</el-button>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.toolbar { margin-bottom: 16px; display: flex; align-items: center; flex-wrap: wrap; }
.hint { margin-left: 16px; color: #909399; font-size: 12px; }
.gen-loading { display: flex; flex-direction: column; align-items: center; padding: 40px 0; }
</style>
