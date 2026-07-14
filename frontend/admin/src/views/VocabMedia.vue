<script setup lang="ts">
import AppDialog from '../components/AppDialog.vue'
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listVocabMedia, generateVocabMedia, generateVocabI2I, suggestVocabImagePrompt, getVocabImageConfig, setVocabImageStyle, getVocabVoiceOptions, setVocabWordVoice, generateVocabGif, reviewVocabMedia, updateVocabMedia, deleteVocabWords, vocabTextbookOptions, vocabUnitOptions, listVocabMediaAssets, selectVocabMediaAsset, deleteVocabMediaAsset, type VocabUnitOption, type VocabMediaAssets, type VocabVoiceOption } from '../api/admin'
import type { AdminVocabMediaItem } from '../types'
import { Refresh, Cpu, CircleCheck, CircleClose, EditPen, VideoPlay, Search, Delete, Film, Files, Upload } from '@element-plus/icons-vue'

const rows = ref<AdminVocabMediaItem[]>([])
const total = ref(0)
const loading = ref(false)
const generating = ref<Record<string, boolean>>({})
const selected = ref<AdminVocabMediaItem[]>([])

// 筛选（服务端：搜索全库，非当前页）
const filterStatus = ref('draft')
const filterOrigin = ref('')      // ''=全部来源 / 'student'=学生端即时生成(待复核)
const searchWord = ref('')
const fTextbook = ref('')
const fGrade = ref('')
const fSemester = ref('')
const fUnit = ref('')
const opts = ref<{ textbook_versions: string[]; grades: string[]; semesters: string[] }>(
  { textbook_versions: [], grades: [], semesters: [] })
const unitOpts = ref<VocabUnitOption[]>([])
const page = ref(1)
const limit = 20

async function loadOptions() {
  try { opts.value = await vocabTextbookOptions() } catch { /* 静默 */ }
}
async function loadUnitOptions() {
  try {
    unitOpts.value = await vocabUnitOptions({
      textbook: fTextbook.value || undefined, grade: fGrade.value || undefined,
      semester: fSemester.value || undefined })
  } catch { unitOpts.value = [] }
}
// 教材/年级/学期 变更 → 单元选项重载 + 清空已选单元 + 回第 1 页
async function onScopeChange() {
  fUnit.value = ''
  await loadUnitOptions()
  reload()
}

async function load() {
  loading.value = true
  try {
    const result = await listVocabMedia({
      media_status: filterStatus.value, q: searchWord.value || undefined,
      media_origin: filterOrigin.value || undefined,
      textbook: fTextbook.value || undefined, grade: fGrade.value || undefined,
      semester: fSemester.value || undefined, unit_id: fUnit.value || undefined,
      skip: (page.value - 1) * limit, limit,
    })
    rows.value = result.items
    total.value = result.total
  } catch (e: any) {
    ElMessage.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}
function reload() { page.value = 1; load() }

// 音频播放（内联）
let audioEl: HTMLAudioElement | null = null
function play(url: string | null) {
  if (!url) return
  try {
    if (audioEl) audioEl.pause()
    audioEl = new Audio(url)
    audioEl.play().catch(() => ElMessage.warning('音频播放失败'))
  } catch { ElMessage.warning('音频播放失败') }
}
function audioCount(row: AdminVocabMediaItem) {
  return (row.word_audio_url ? 1 : 0) + (row.en_desc_audio_url ? 1 : 0)
}

// 系统隐性描述:主要要求模板(primary) + 风格(styles) + 固定风格(style),来自「配图配置」页
const imgCfg = ref<{ primary: string; styles: string[]; style: string } | null>(null)
async function loadImgCfg(force = false) {
  if (imgCfg.value && !force) return
  try {
    const c = await getVocabImageConfig()
    imgCfg.value = { primary: c.primary, styles: c.styles, style: c.style || '' }
  } catch { /* 静默 */ }
}
// 风格中文名(默认 5 种);自定义风格无映射则显英文原文
const STYLE_ZH: Record<string, string> = {
  'flat vector illustration, bright cheerful colors': '扁平矢量 · 明快配色',
  'cute kawaii cartoon style, soft pastel colors': '卡哇伊卡通 · 柔和马卡龙',
  'simple watercolor illustration, gentle warm tones': '水彩手绘 · 暖调',
  'clean minimalist illustration with light soft shading': '极简 · 轻柔阴影',
  'friendly rounded 3D render, soft studio lighting': '圆润 3D · 柔光',
}
function styleLabel(s: string) { return STYLE_ZH[s] ? `${STYLE_ZH[s]} — ${s}` : s }
// 选定固定风格:持久化到配图配置,之后所有词默认此风格;空=恢复随机
async function onPickStyle(s: string) {
  try {
    const c = await setVocabImageStyle(s)
    if (imgCfg.value) imgCfg.value.style = c.style || ''
    ElMessage.success(s ? `已设默认风格：${STYLE_ZH[s] || s}` : '已恢复随机风格')
  } catch (e: any) { ElMessage.error(e?.message || '设置风格失败') }
}

// 音色(全局默认,原理同风格):可选列表 + 当前选用
const voiceOpts = ref<VocabVoiceOption[]>([])
const voiceSel = ref('')
let voiceLoaded = false
async function loadVoices(force = false) {
  if (voiceLoaded && !force) return
  try {
    const r = await getVocabVoiceOptions()
    voiceOpts.value = r.voices; voiceSel.value = r.selected || ''; voiceLoaded = true
  } catch { /* 静默 */ }
}
async function onPickVoice(v: string) {
  try {
    await setVocabWordVoice(v); voiceSel.value = v
    const lbl = voiceOpts.value.find(o => o.id === v)?.label
    ElMessage.success(v ? `已设默认音色：${lbl || v}` : '已恢复按词自动选男/女')
  } catch (e: any) { ElMessage.error(e?.message || '设置音色失败') }
}

// —— 单个生成:弹框(打开时不调大模型),按需点「用 AI 生成画面描述」才调 ——
const promptDlg = ref({ visible: false, word_id: '', word: '', prompt: '', suggesting: false, generating: false })
// 图生图:原图(上传 base64 或图片地址)+ 重绘幅度
const i2i = ref({ url: '', b64: '', preview: '', strength: 0.6, busy: false })
async function openGenerate(row: AdminVocabMediaItem) {
  // 打开只准备状态(纯 GET 只读展示构成,不调大模型);画面描述留空
  promptDlg.value = { visible: true, word_id: row.word_id, word: row.word, prompt: '', suggesting: false, generating: false }
  i2i.value = { url: '', b64: '', preview: '', strength: 0.6, busy: false }
  loadImgCfg(); loadVoices()
}
// 上传原图 → 读为 base64 预览(不立即上传后端)
function onI2IFile(uploadFile: any) {
  const file: File = uploadFile.raw || uploadFile
  if (!file) return
  if (file.size > 8 * 1024 * 1024) { ElMessage.warning('图片过大(>8MB),请压缩后再传'); return }
  const reader = new FileReader()
  reader.onload = () => { i2i.value.b64 = String(reader.result || ''); i2i.value.preview = i2i.value.b64; i2i.value.url = '' }
  reader.readAsDataURL(file)
}
async function confirmI2I() {
  const d = promptDlg.value
  if (!i2i.value.b64 && !i2i.value.url.trim()) { ElMessage.warning('请上传原图或填图片地址'); return }
  i2i.value.busy = true
  try {
    const result = await generateVocabI2I(d.word_id, {
      source_b64: i2i.value.b64 || undefined,
      source_url: i2i.value.b64 ? undefined : i2i.value.url.trim(),
      prompt: d.prompt.trim() || undefined,
      strength: i2i.value.strength,
    })
    ElMessage.success(`「${d.word}」图生图完成（原图+结果已记入版本）`)
    patchRow(result)
    if (filterStatus.value && filterStatus.value !== result.media_status) {
      rows.value = rows.value.filter(r => r.word_id !== d.word_id)
    }
    d.visible = false
  } catch (e: any) {
    ElMessage.error(e?.message || '图生图失败')
  } finally {
    i2i.value.busy = false
  }
}
async function suggestPrompt() {
  const d = promptDlg.value
  d.suggesting = true
  try {
    d.prompt = (await suggestVocabImagePrompt(d.word_id)).prompt || ''
  } catch (e: any) { ElMessage.warning(e?.message || 'AI 生成失败,可手动填写') }
  finally { d.suggesting = false }
}
async function confirmGenerate() {
  const d = promptDlg.value
  d.generating = true
  try {
    const result = await generateVocabMedia(d.word_id, { brief: d.prompt.trim() || undefined })
    ElMessage.success(`「${d.word}」媒体生成完成（草稿）`)
    patchRow(result)
    if (filterStatus.value && filterStatus.value !== result.media_status) {
      rows.value = rows.value.filter(r => r.word_id !== d.word_id)
    }
    d.visible = false
  } catch (e: any) {
    ElMessage.error(e?.message || '生成失败')
  } finally {
    d.generating = false
  }
}

const isVideo = (u: string) => /\.(mp4|webm|mov)(\?|$)/i.test(u || '')

const gifgen = ref<Record<string, boolean>>({})
async function onGenerateGif(row: AdminVocabMediaItem) {
  gifgen.value[row.word_id] = true
  try {
    const r = await generateVocabGif(row.word_id)
    if (r.gif_status === 'skip') {
      ElMessage.info(`「${row.word}」无需动图（静态图即可表达）`)
    } else if (r.gif_status === 'generated') {
      ElMessage.success(`「${row.word}」动图生成完成（草稿）`)
      patchRow(r)
    } else {
      ElMessage.warning(`「${row.word}」需要动图但生成失败（免费档可能限流），请稍后重试`)
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '动图生成失败')
  } finally {
    gifgen.value[row.word_id] = false
  }
}

async function onReview(row: AdminVocabMediaItem, approve: boolean) {
  try {
    const result = await reviewVocabMedia(row.word_id, approve)
    ElMessage.success(`「${row.word}」已${approve ? '发布' : '驳回'}`)
    patchRow(result)
    if (filterStatus.value === 'draft') rows.value = rows.value.filter(r => r.word_id !== row.word_id)
  } catch (e: any) {
    ElMessage.error(e?.message || '操作失败')
  }
}

// —— 版本历史(图/音/GIF 保留所有版本,可人工选用/删除)——
const emptyAssets = (): VocabMediaAssets => ({ image: [], audio: [], gif: [] })
const verDlg = ref({ visible: false, word_id: '', word: '', loading: false, busy: '', assets: emptyAssets() })
async function openVersions(row: AdminVocabMediaItem) {
  verDlg.value = { visible: true, word_id: row.word_id, word: row.word, loading: true, busy: '', assets: emptyAssets() }
  try { verDlg.value.assets = await listVocabMediaAssets(row.word_id) }
  catch (e: any) { ElMessage.error(e?.message || '加载版本失败') }
  finally { verDlg.value.loading = false }
}
// 选用/删除后:刷新版本列表 + 用镜像回填该行(图/音/GIF)
function applyAssetsToRow(a: VocabMediaAssets) {
  const row = rows.value.find(r => r.word_id === verDlg.value.word_id)
  if (!row) return
  row.image_urls = a.image.filter(x => x.selected).map(x => x.url)
  row.word_audio_url = a.audio.find(x => x.selected)?.url || null
  row.gif_url = a.gif.find(x => x.selected)?.url || null
}
async function pickVersion(id: string) {
  verDlg.value.busy = id
  try { verDlg.value.assets = await selectVocabMediaAsset(id); applyAssetsToRow(verDlg.value.assets); ElMessage.success('已选用该版本') }
  catch (e: any) { ElMessage.error(e?.message || '选用失败') }
  finally { verDlg.value.busy = '' }
}
async function removeVersion(id: string) {
  try { await ElMessageBox.confirm('删除这个版本?不可恢复。', '删除版本', { type: 'warning' }) } catch { return }
  verDlg.value.busy = id
  try { verDlg.value.assets = await deleteVocabMediaAsset(id); applyAssetsToRow(verDlg.value.assets); ElMessage.success('已删除') }
  catch (e: any) { ElMessage.error(e?.message || '删除失败') }
  finally { verDlg.value.busy = '' }
}

// —— 批量操作 ——
const batch = ref({ running: false, total: 0, done: 0, ok: 0, failed: 0, skipped: 0, label: '' })

// 批量生成:弹框逐词展示 AI 建议提示词(可编辑)+ 两个「跳过已有」开关(图片/音频,默认跳过)
interface BatchPromptItem { word_id: string; word: string; prompt: string; loading: boolean; hasImage: boolean; hasAudio: boolean }
const batchDlg = ref({ visible: false, running: false, skipImg: true, skipAudio: true, items: [] as BatchPromptItem[] })
// 按当前「跳过已有」勾选,实时算将生成/跳过多少
const batchPlan = computed(() => {
  const { skipImg, skipAudio, items } = batchDlg.value
  let skip = 0
  for (const it of items) {
    const doImg = !(skipImg && it.hasImage)
    const doAud = !(skipAudio && it.hasAudio)
    if (!doImg && !doAud) skip++
  }
  return { total: items.length, skip, todo: items.length - skip }
})
function openBatchGenerate() {
  if (!selected.value.length) return
  // 打开不调大模型:各词画面描述留空(留空=生成时 AI 自动);需要可点「取建议」按需生成
  loadImgCfg(); loadVoices()   // 载入全局风格+音色设置(供弹框顶部选择器)
  batchDlg.value = {
    visible: true, running: false, skipImg: true, skipAudio: true,   // 默认跳过已有
    items: selected.value.map(r => ({
      word_id: r.word_id, word: r.word, prompt: '', loading: false,
      hasImage: !!(r.image_urls?.length),
      hasAudio: !!(r.word_audio_url || r.en_desc_audio_url),
    })),
  }
}
async function suggestBatchRow(it: BatchPromptItem) {
  it.loading = true
  try { it.prompt = (await suggestVocabImagePrompt(it.word_id)).prompt || '' }
  catch { ElMessage.warning(`「${it.word}」建议生成失败`) }
  finally { it.loading = false }
}
async function suggestBatchAll() {
  await Promise.all(batchDlg.value.items.filter(it => !it.prompt.trim()).map(suggestBatchRow))
}
function removeBatchRow(row: BatchPromptItem) {
  batchDlg.value.items = batchDlg.value.items.filter(it => it.word_id !== row.word_id)
  if (!batchDlg.value.items.length) { batchDlg.value.visible = false; ElMessage.info('已清空,取消批量') }
}
const GEN_CONCURRENCY = 4    // 批量生成并发数(同时出图/TTS 别太高,避免被限流)
async function confirmBatchGenerate() {
  const { skipImg, skipAudio } = batchDlg.value
  // 按「跳过已有」开关,给每个词算出要不要出图/配音;两者都跳过则整词跳过
  const jobs = batchDlg.value.items.map(it => ({
    it,
    do_images: !(skipImg && it.hasImage),
    do_audio: !(skipAudio && it.hasAudio),
  })).map(j => ({ ...j, skip: !j.do_images && !j.do_audio }))
  const todo = jobs.filter(j => !j.skip)
  const skipped = jobs.length - todo.length
  if (!todo.length) { ElMessage.info('按当前「跳过已有」设置,选中的词都无需生成'); return }
  batch.value = { running: true, total: todo.length, done: 0, ok: 0, failed: 0, skipped, label: '媒体' }
  batchDlg.value.running = true
  // 并发工作池:GEN_CONCURRENCY 个 worker 共享游标,各自取下一个词生成
  let idx = 0
  async function worker() {
    while (idx < todo.length) {
      const { it, do_images, do_audio } = todo[idx++]
      try {
        patchRow(await generateVocabMedia(it.word_id, {
          brief: it.prompt.trim() || undefined, do_images, do_audio,
        }))
        batch.value.ok++
      } catch { batch.value.failed++ }
      batch.value.done++
    }
  }
  await Promise.all(Array.from({ length: Math.min(GEN_CONCURRENCY, todo.length) }, worker))
  batchDlg.value.running = false
  batch.value.running = false
  batchDlg.value.visible = false
  ElMessage.success(`批量生成完成：成功 ${batch.value.ok}${batch.value.failed ? `，失败 ${batch.value.failed}` : ''}${skipped ? `，跳过 ${skipped}` : ''}`)
  load()
}
async function batchGif() {
  if (!selected.value.length) return
  try {
    await ElMessageBox.confirm(
      `对选中的 ${selected.value.length} 个词生成动图（图生视频）：仅动作/过程类词会生成，复用现有配图当首帧调已配置的图生视频服务（异步生成每词约 0.5–4 分钟），名词/静态词自动跳过。是否继续？`,
      '批量生成动图', { type: 'warning' })
  } catch { return }
  const items = [...selected.value]
  batch.value = { running: true, total: items.length, done: 0, ok: 0, failed: 0, skipped: 0, label: 'GIF' }
  for (const row of items) {
    try {
      const r = await generateVocabGif(row.word_id)
      if (r.gif_status === 'skip') batch.value.skipped++
      else if (r.gif_status === 'generated') { patchRow(r); batch.value.ok++ }
      else batch.value.failed++
    } catch { batch.value.failed++ }
    batch.value.done++
  }
  batch.value.running = false
  ElMessage.success(`批量 GIF 完成：生成 ${batch.value.ok}，静态跳过 ${batch.value.skipped}${batch.value.failed ? `，失败 ${batch.value.failed}` : ''}`)
  load()
}
async function batchReview(approve: boolean) {
  if (!selected.value.length) return
  const label = approve ? '发布' : '驳回'
  try {
    await ElMessageBox.confirm(`批量${label}选中的 ${selected.value.length} 个词的媒体？`, label,
      { type: approve ? 'info' : 'warning' })
  } catch { return }
  let ok = 0
  for (const row of [...selected.value]) {
    try { await reviewVocabMedia(row.word_id, approve); ok++ } catch { /* 跳过失败项 */ }
  }
  ElMessage.success(`已${label} ${ok} 个`)
  selected.value = []
  load()
}
async function batchDelete() {
  if (!selected.value.length) return
  const n = selected.value.length
  try {
    await ElMessageBox.confirm(
      `彻底删除选中的 ${n} 个词条？将从整个词力通移除：词库词条 + 课程单元挂载 + 学生学习记录 + 媒体 + 词单。此操作不可恢复！`,
      '批量删除词条', { type: 'error', confirmButtonText: '确认删除', confirmButtonClass: 'el-button--danger' })
  } catch { return }
  try {
    const res = await deleteVocabWords(selected.value.map(r => r.word_id))
    ElMessage.success(`已删除 ${res.deleted} 个词条`)
    selected.value = []
    load()
  } catch (e: any) {
    ElMessage.error(e?.message || '删除失败')
  }
}

// 编辑弹窗
const editDialogVisible = ref(false)
const editingRow = ref<AdminVocabMediaItem | null>(null)
const editEnDesc = ref('')
const editImageUrls = ref('')
const editMeaning = ref('')
const editPos = ref('')
function openEdit(row: AdminVocabMediaItem) {
  editingRow.value = row
  editEnDesc.value = row.en_description ?? ''
  editImageUrls.value = (row.image_urls ?? []).join('\n')
  editMeaning.value = row.meaning ?? ''
  editPos.value = row.pos ?? ''
  editDialogVisible.value = true
}
async function onSaveEdit() {
  if (!editingRow.value) return
  const urls = editImageUrls.value.split('\n').map(s => s.trim()).filter(Boolean)
  try {
    const result = await updateVocabMedia(editingRow.value.word_id, {
      en_description: editEnDesc.value || undefined,
      image_urls: urls.length ? urls : undefined,
      meaning: editMeaning.value.trim(),
      pos: editPos.value.trim(),
    })
    ElMessage.success('保存成功')
    patchRow(result)
    editDialogVisible.value = false
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  }
}

function patchRow(updated: AdminVocabMediaItem) {
  const idx = rows.value.findIndex(r => r.word_id === updated.word_id)
  if (idx !== -1) rows.value[idx] = updated
}

function statusTag(status: string): 'warning' | 'success' | 'info' {
  return status === 'draft' ? 'warning' : status === 'published' ? 'success' : 'info'
}
function statusLabel(status: string): string {
  return { draft: '草稿', published: '已发布', retired: '已驳回' }[status] ?? status
}

onMounted(() => { loadOptions(); loadUnitOptions(); load() })
</script>

<template>
  <div class="page">
    <!-- 筛选 + 批量工具栏 -->
    <div class="toolbar">
      <el-select v-model="filterStatus" style="width: 110px" @change="reload">
        <el-option label="全部状态" value="" />
        <el-option label="草稿" value="draft" />
        <el-option label="已发布" value="published" />
        <el-option label="已驳回" value="retired" />
      </el-select>
      <el-select v-model="filterOrigin" style="width: 150px" @change="reload">
        <el-option label="全部来源" value="" />
        <el-option label="学生端生成(待复核)" value="student" />
      </el-select>
      <el-select v-model="fTextbook" placeholder="教材版本" clearable style="width: 130px" @change="onScopeChange">
        <el-option v-for="t in opts.textbook_versions" :key="t" :label="t" :value="t" />
      </el-select>
      <el-select v-model="fGrade" placeholder="年级" clearable style="width: 120px" @change="onScopeChange">
        <el-option v-for="g in opts.grades" :key="g" :label="g" :value="g" />
      </el-select>
      <el-select v-model="fSemester" placeholder="上/下册" clearable style="width: 100px" @change="onScopeChange">
        <el-option v-for="s in opts.semesters" :key="s" :label="s + '册'" :value="s" />
      </el-select>
      <el-select v-model="fUnit" placeholder="单元" clearable filterable style="width: 220px" @change="reload">
        <el-option v-for="u in unitOpts" :key="u.id" :label="`U${u.unit_no} ${u.unit_title}`" :value="u.id" />
      </el-select>
      <el-input v-model="searchWord" placeholder="搜索单词（全库）" clearable style="width: 180px"
        :prefix-icon="Search" @keyup.enter="reload" @clear="reload" />
      <el-button :loading="loading" @click="reload"><el-icon><Refresh /></el-icon>&nbsp;刷新</el-button>

      <div class="spacer" />

      <template v-if="selected.length">
        <span class="sel-hint">已选 {{ selected.length }}</span>
        <el-button type="primary" :icon="Cpu" @click="openBatchGenerate">批量生成</el-button>
        <el-button type="primary" plain :icon="Film" @click="batchGif">批量生成GIF</el-button>
        <el-button type="success" :icon="CircleCheck" @click="batchReview(true)">批量发布</el-button>
        <el-button type="warning" plain :icon="CircleClose" @click="batchReview(false)">批量驳回</el-button>
        <el-button type="danger" :icon="Delete" @click="batchDelete">批量删除</el-button>
      </template>
      <span class="count">共 {{ total }} 个词</span>
    </div>

    <!-- 批量生成进度 -->
    <el-alert v-if="batch.running || (batch.total > 0 && batch.done < batch.total)" type="info" :closable="false" class="gen-bar">
      <template #title>
        批量{{ batch.label }}生成中：{{ batch.done }} / {{ batch.total }}（成功 {{ batch.ok }}<span v-if="batch.skipped">，静态跳过 {{ batch.skipped }}</span><span v-if="batch.failed">，失败 {{ batch.failed }}</span>）
        <el-progress :percentage="batch.total ? Math.round(batch.done / batch.total * 100) : 0" :stroke-width="10" style="margin-top:6px" />
      </template>
    </el-alert>

    <!-- 词列表 -->
    <el-table v-loading="loading" :data="rows" border style="width: 100%" row-key="word_id"
              @selection-change="(rs: AdminVocabMediaItem[]) => selected = rs">
      <el-table-column type="selection" width="44" reserve-selection />
      <el-table-column prop="word" label="单词" width="150" fixed="left" />
      <el-table-column label="词性" width="80" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.pos" size="small" type="info" effect="plain">{{ row.pos }}</el-tag>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="130" align="center">
        <template #default="{ row }">
          <el-tag :type="statusTag(row.media_status)" size="small">{{ statusLabel(row.media_status) }}</el-tag>
          <el-tag v-if="row.media_origin === 'student'" type="warning" size="small" effect="dark"
            style="margin-left:4px" title="学生端「加入学习」即时生成,待复核">学生</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="配图 / 动图" width="160" align="center">
        <template #default="{ row }">
          <div class="thumbs">
            <el-image v-for="(u, i) in (row.image_urls || []).slice(0, 2)" :key="i" :src="u"
              :preview-src-list="row.image_urls" :initial-index="i" fit="cover"
              class="thumb" preview-teleported hide-on-click-modal />
            <video v-if="row.gif_url && isVideo(row.gif_url)" :src="row.gif_url"
              class="thumb thumb-gif" autoplay loop muted playsinline title="动图(图生视频)" />
            <el-image v-else-if="row.gif_url" :src="row.gif_url" :preview-src-list="[row.gif_url]" fit="cover"
              class="thumb thumb-gif" preview-teleported hide-on-click-modal title="动图" />
            <span v-if="!(row.image_urls?.length) && !row.gif_url" class="muted">—</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="发音" width="120" align="center">
        <template #default="{ row }">
          <el-button-group v-if="audioCount(row)">
            <el-tooltip content="单词发音" placement="top">
              <el-button size="small" :disabled="!row.word_audio_url" @click="play(row.word_audio_url)">
                <el-icon><VideoPlay /></el-icon>词
              </el-button>
            </el-tooltip>
            <el-tooltip content="描述发音" placement="top">
              <el-button size="small" :disabled="!row.en_desc_audio_url" @click="play(row.en_desc_audio_url)">
                <el-icon><VideoPlay /></el-icon>述
              </el-button>
            </el-tooltip>
          </el-button-group>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="英文描述" min-width="220" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.en_description" class="desc">{{ row.en_description }}</span>
          <span v-else class="muted">暂无</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="300" fixed="right" align="center">
        <template #default="{ row }">
          <el-button size="small" :loading="generating[row.word_id]" @click="openGenerate(row)">
            <el-icon><Cpu /></el-icon>&nbsp;生成
          </el-button>
          <el-tooltip content="生成动图 GIF（动作/过程词）" placement="top">
            <el-button size="small" :loading="gifgen[row.word_id]" @click="onGenerateGif(row)">
              <el-icon><Film /></el-icon>&nbsp;GIF
            </el-button>
          </el-tooltip>
          <el-tooltip content="发布" placement="top">
            <el-button size="small" type="success" :icon="CircleCheck"
              :disabled="row.media_status === 'published'" @click="onReview(row, true)" />
          </el-tooltip>
          <el-tooltip content="驳回" placement="top">
            <el-button size="small" type="danger" plain :icon="CircleClose"
              :disabled="row.media_status === 'retired'" @click="onReview(row, false)" />
          </el-tooltip>
          <el-tooltip content="版本(选用/删除历史图·音·GIF)" placement="top">
            <el-button size="small" :icon="Files" @click="openVersions(row)" />
          </el-tooltip>
          <el-tooltip content="编辑描述/配图" placement="top">
            <el-button size="small" :icon="EditPen" @click="openEdit(row)" />
          </el-tooltip>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div class="pager">
      <el-pagination
        v-model:current-page="page" :page-size="limit" :total="total"
        layout="total, prev, pager, next, jumper" @current-change="load" />
    </div>

    <!-- 编辑弹窗 -->
    <AppDialog v-model="editDialogVisible" :title="`编辑：${editingRow?.word}`" width="560px">
      <el-form label-width="100px">
        <el-form-item label="中文词义">
          <el-input v-model="editMeaning" placeholder="该词的中文释义（配图/AI 生成都以此为准）" />
        </el-form-item>
        <el-form-item label="词性">
          <el-input v-model="editPos" style="width:160px" placeholder="如 v. / n. / prep." />
        </el-form-item>
        <el-form-item label="英文描述">
          <el-input v-model="editEnDesc" type="textarea" :rows="4" placeholder="用英文描述单词含义…" />
        </el-form-item>
        <el-form-item label="图片 URLs">
          <el-input v-model="editImageUrls" type="textarea" :rows="3" placeholder="每行一条图片 URL" />
        </el-form-item>
        <el-form-item v-if="editImageUrls.trim()" label="预览">
          <div class="thumbs">
            <el-image v-for="(u, i) in editImageUrls.split('\n').map(s => s.trim()).filter(Boolean)" :key="i"
              :src="u" fit="cover" class="thumb-lg" preview-teleported
              :preview-src-list="editImageUrls.split('\n').map(s => s.trim()).filter(Boolean)" :initial-index="i" />
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="onSaveEdit">保存</el-button>
      </template>
    </AppDialog>

    <!-- 媒体版本:图/音/GIF 保留所有版本,可人工选用/删除 -->
    <AppDialog v-model="verDlg.visible" :title="`媒体版本：${verDlg.word}`" width="720px">
      <div v-loading="verDlg.loading">
        <!-- 图片 -->
        <div class="ver-sec">
          <div class="ver-h">图片 <span class="muted">共 {{ verDlg.assets.image.length }} 版</span></div>
          <div v-if="!verDlg.assets.image.length" class="muted">暂无</div>
          <div v-else class="ver-grid">
            <div v-for="a in verDlg.assets.image" :key="a.id" class="ver-card" :class="{ sel: a.selected }">
              <el-image :src="a.url" fit="cover" class="ver-thumb" :preview-src-list="[a.url]" preview-teleported hide-on-click-modal />
              <div class="ver-meta">{{ a.style || '—' }}</div>
              <div class="ver-ops">
                <el-tag v-if="a.selected" type="success" size="small">当前</el-tag>
                <el-button v-else size="small" :loading="verDlg.busy === a.id" @click="pickVersion(a.id)">选用</el-button>
                <el-button size="small" text :icon="Delete" :disabled="a.selected" @click="removeVersion(a.id)" />
              </div>
            </div>
          </div>
        </div>
        <!-- GIF/动图 -->
        <div class="ver-sec">
          <div class="ver-h">动图 <span class="muted">共 {{ verDlg.assets.gif.length }} 版</span></div>
          <div v-if="!verDlg.assets.gif.length" class="muted">暂无</div>
          <div v-else class="ver-grid">
            <div v-for="a in verDlg.assets.gif" :key="a.id" class="ver-card" :class="{ sel: a.selected }">
              <video v-if="isVideo(a.url)" :src="a.url" class="ver-thumb" autoplay loop muted playsinline />
              <el-image v-else :src="a.url" fit="cover" class="ver-thumb" :preview-src-list="[a.url]" preview-teleported />
              <div class="ver-ops">
                <el-tag v-if="a.selected" type="success" size="small">当前</el-tag>
                <el-button v-else size="small" :loading="verDlg.busy === a.id" @click="pickVersion(a.id)">选用</el-button>
                <el-button size="small" text :icon="Delete" :disabled="a.selected" @click="removeVersion(a.id)" />
              </div>
            </div>
          </div>
        </div>
        <!-- 音频 -->
        <div class="ver-sec">
          <div class="ver-h">单词发音 <span class="muted">共 {{ verDlg.assets.audio.length }} 版</span></div>
          <div v-if="!verDlg.assets.audio.length" class="muted">暂无</div>
          <div v-for="a in verDlg.assets.audio" :key="a.id" class="ver-row">
            <el-button size="small" :icon="VideoPlay" @click="play(a.url)">试听</el-button>
            <span class="muted">{{ a.created_at?.slice(0, 16)?.replace('T', ' ') }}</span>
            <el-tag v-if="a.selected" type="success" size="small">当前</el-tag>
            <el-button v-else size="small" :loading="verDlg.busy === a.id" @click="pickVersion(a.id)">选用</el-button>
            <el-button size="small" text :icon="Delete" :disabled="a.selected" @click="removeVersion(a.id)" />
          </div>
        </div>
      </div>
      <template #footer><el-button @click="verDlg.visible = false">关闭</el-button></template>
    </AppDialog>

    <!-- 单个生成:画面描述(可编辑) + 最终提示词构成(只读) -->
    <AppDialog v-model="promptDlg.visible" :title="`生成配图：${promptDlg.word}`" width="680px">
      <div class="fld-label">
        <span>画面描述提示词</span>
        <el-button size="small" :loading="promptDlg.suggesting" @click="suggestPrompt">
          <el-icon><Cpu /></el-icon>&nbsp;用 AI 生成
        </el-button>
      </div>
      <el-input v-model="promptDlg.prompt" type="textarea" :rows="5"
        placeholder="描述这张图要画什么(主体/动作/场景);物体/量词类不必画人。留空=生成时由 AI 自动生成" />

      <div class="fld-label" style="margin-top:14px">
        <span>图片风格（全局默认）</span>
        <el-select :model-value="imgCfg?.style || ''" size="small" style="width:360px"
          placeholder="选一个固定风格" @change="onPickStyle">
          <el-option label="🎲 随机（每张不同）" value="" />
          <el-option v-for="s in (imgCfg?.styles || [])" :key="s" :label="styleLabel(s)" :value="s" />
        </el-select>
      </div>
      <div class="fld-label" style="margin-top:8px">
        <span>单词音色（全局默认）</span>
        <el-select :model-value="voiceSel" size="small" style="width:360px"
          placeholder="选一个固定音色" @change="onPickVoice">
          <el-option label="🎧 自动（按词选男/女）" value="" />
          <el-option v-for="v in voiceOpts" :key="v.id" :label="v.label" :value="v.id" />
        </el-select>
      </div>
      <div class="muted" style="margin:4px 0 0">风格/音色选定后所有单词生成都用它,再次选择即更改;选「随机/自动」恢复默认。</div>

      <el-collapse style="margin-top:14px">
        <el-collapse-item name="compose">
          <template #title>最终提示词构成（只读）—— 送 AI 出图的完整内容</template>
          <div class="compose">
            <div class="cp-row"><b>① 画面描述</b><span>{{ promptDlg.prompt || '(留空 → 生成时 AI 自动生成)' }}</span></div>
            <div class="cp-row"><b>② 主要要求模板</b><span>{{ imgCfg?.primary || '(加载中…)' }}
              <em>（系统隐性;生成时自动填入词与词义。在「配图生成/配置」页可改）</em></span></div>
            <div class="cp-row"><b>③ 风格</b><span>{{ imgCfg?.style ? styleLabel(imgCfg.style)
              : ('随机其一：' + (imgCfg?.styles || []).join('  /  ')) }}
              <em>（在上方「图片风格」选择,全局默认）</em></span></div>
            <div class="cp-note">最终 = ① + ② + “Style: ③”。①留空时后端自动产出①。</div>
          </div>
        </el-collapse-item>
      </el-collapse>

      <!-- 图生图:基于原图(上传/地址)生成变体 -->
      <div class="i2i-box">
        <div class="fld-label"><b>图生图</b><span class="muted">基于原图生成变体;上方「画面描述」当变体提示词(可空)。原图与结果都记入版本。</span></div>
        <div class="i2i-src">
          <el-upload :show-file-list="false" :auto-upload="false" accept="image/*" :on-change="onI2IFile">
            <el-button size="small" :icon="Upload">上传原图</el-button>
          </el-upload>
          <span class="muted">或</span>
          <el-input v-model="i2i.url" size="small" placeholder="图片地址 https://…" style="width:320px"
            @input="i2i.b64 = ''; i2i.preview = i2i.url" clearable />
          <el-image v-if="i2i.preview || i2i.url" :src="i2i.preview || i2i.url" fit="cover" class="i2i-thumb"
            :preview-src-list="[i2i.preview || i2i.url]" preview-teleported />
        </div>
        <div class="i2i-src">
          <span class="muted">重绘幅度</span>
          <el-slider v-model="i2i.strength" :min="0.2" :max="0.9" :step="0.05" style="width:240px" />
          <span class="muted">{{ i2i.strength.toFixed(2) }}(越大越偏离原图)</span>
          <el-button type="warning" plain size="small" :loading="i2i.busy"
            :disabled="!i2i.b64 && !i2i.url.trim()" @click="confirmI2I">确定图生图</el-button>
        </div>
      </div>

      <template #footer>
        <el-button @click="promptDlg.visible = false">取消</el-button>
        <el-button type="primary" :loading="promptDlg.generating" @click="confirmGenerate">确定生成(文生图)</el-button>
      </template>
    </AppDialog>

    <!-- 批量生成:逐词提示词编辑 -->
    <AppDialog v-model="batchDlg.visible" :title="`批量生成配图（${batchDlg.items.length} 词）`" width="760px">
      <div class="fld-label" style="margin-bottom:10px">
        <span>图片风格（全局默认）</span>
        <el-select :model-value="imgCfg?.style || ''" size="small" style="width:300px"
          placeholder="选一个固定风格" @change="onPickStyle">
          <el-option label="🎲 随机（每张不同）" value="" />
          <el-option v-for="s in (imgCfg?.styles || [])" :key="s" :label="styleLabel(s)" :value="s" />
        </el-select>
        <span>音色</span>
        <el-select :model-value="voiceSel" size="small" style="width:220px"
          placeholder="选一个固定音色" @change="onPickVoice">
          <el-option label="🎧 自动" value="" />
          <el-option v-for="v in voiceOpts" :key="v.id" :label="v.label" :value="v.id" />
        </el-select>
      </div>
      <div class="fld-label" style="margin-bottom:10px">
        <span>已有资源</span>
        <el-checkbox v-model="batchDlg.skipImg" :disabled="batchDlg.running">跳过已有图片</el-checkbox>
        <el-checkbox v-model="batchDlg.skipAudio" :disabled="batchDlg.running">跳过已有音频</el-checkbox>
        <span class="muted">勾选=已有的不重新生成(省钱);取消勾选=覆盖重生。</span>
      </div>
      <div class="fld-label" style="margin-bottom:10px">
        <el-tag type="success" size="small">将生成 {{ batchPlan.todo }} 词</el-tag>
        <el-tag v-if="batchPlan.skip" type="info" size="small">跳过 {{ batchPlan.skip }} 词(已有资源)</el-tag>
        <span class="muted">共 {{ batchPlan.total }} 词。想生成被跳过的,取消上面对应勾选。</span>
      </div>
      <div class="fld-label" style="margin-bottom:10px">
        <span class="muted">打开不自动调大模型。留空的词按 AI 自动生成;可逐条「取建议」或「全部取建议」后编辑。</span>
        <el-button size="small" :disabled="batchDlg.running" @click="suggestBatchAll">
          <el-icon><Cpu /></el-icon>&nbsp;全部取建议(空白项)
        </el-button>
      </div>
      <el-table :data="batchDlg.items" border size="small" max-height="52vh">
        <el-table-column label="单词" width="170">
          <template #default="{ row }">
            {{ row.word }}
            <el-tag v-if="row.hasImage" type="info" size="small" style="margin-left:4px">图</el-tag>
            <el-tag v-if="row.hasAudio" type="info" size="small" style="margin-left:2px">音</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="画面描述提示词(可编辑,留空=AI 自动)">
          <template #default="{ row }">
            <el-input v-model="row.prompt" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }"
              :placeholder="row.loading ? 'AI 生成中…' : '留空=AI 自动生成'" :disabled="row.loading" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" align="center">
          <template #default="{ row }">
            <el-button size="small" :loading="row.loading" :disabled="batchDlg.running"
              @click="suggestBatchRow(row)">取建议</el-button>
            <el-tooltip content="从本次批量移除该词" placement="top">
              <el-button size="small" text :icon="Delete" :disabled="batchDlg.running"
                @click="removeBatchRow(row)" />
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="batchDlg.running" style="margin-top:10px">
        <el-progress :percentage="batch.total ? Math.round(batch.done / batch.total * 100) : 0" />
        <span class="muted">进度 {{ batch.done }}/{{ batch.total }}（成功 {{ batch.ok }}，失败 {{ batch.failed }}）</span>
      </div>
      <template #footer>
        <el-button :disabled="batchDlg.running" @click="batchDlg.visible = false">取消</el-button>
        <el-button type="primary" :loading="batchDlg.running" @click="confirmBatchGenerate">确定批量生成</el-button>
      </template>
    </AppDialog>
  </div>
</template>

<style scoped>
.page { padding: 4px; }
.toolbar { margin-bottom: 16px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.toolbar .spacer { flex: 1; }
.sel-hint { color: var(--el-color-primary); font-weight: 600; font-size: 13px; }
.count { color: #909399; font-size: 13px; }
.gen-bar { margin-bottom: 12px; }
.thumbs { display: flex; gap: 4px; align-items: center; justify-content: center; }
.thumb { width: 38px; height: 38px; border-radius: 4px; border: 1px solid var(--el-border-color-lighter); }
.thumb-gif { border-color: var(--el-color-primary); box-shadow: 0 0 0 1px var(--el-color-primary-light-5); }
.thumb-lg { width: 72px; height: 72px; border-radius: 6px; border: 1px solid var(--el-border-color-lighter); }
.more { font-size: 12px; color: #909399; }
.muted { color: #c0c4cc; font-size: 13px; }
.desc { color: #606266; font-size: 13px; }
.pager { margin-top: 16px; display: flex; justify-content: flex-end; }
.fld-label { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; font-weight: 600; }
.fld-label .muted { font-weight: 400; }
.compose { font-size: 13px; color: #606266; line-height: 1.6; }
.compose .cp-row { display: flex; gap: 10px; margin-bottom: 8px; }
.compose .cp-row b { flex: 0 0 108px; color: #303133; }
.compose .cp-row em { color: #909399; font-style: normal; }
.compose .cp-note { color: #909399; border-top: 1px dashed var(--el-border-color-lighter); padding-top: 8px; }
.ver-sec { margin-bottom: 18px; }
.ver-h { font-weight: 600; color: #303133; margin-bottom: 8px; }
.ver-grid { display: flex; flex-wrap: wrap; gap: 12px; }
.ver-card { width: 128px; border: 1px solid var(--el-border-color-lighter); border-radius: 8px; padding: 6px; }
.ver-card.sel { border-color: var(--el-color-success); box-shadow: 0 0 0 1px var(--el-color-success-light-5); }
.ver-thumb { width: 116px; height: 88px; border-radius: 6px; object-fit: cover; display: block; background: #f5f7fa; }
.ver-meta { font-size: 12px; color: #909399; margin: 4px 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ver-ops { display: flex; align-items: center; gap: 6px; }
.ver-row { display: flex; align-items: center; gap: 10px; padding: 6px 0; border-bottom: 1px dashed var(--el-border-color-lighter); }
.i2i-box { margin-top: 14px; padding: 12px; border: 1px solid var(--el-border-color-lighter); border-radius: 8px; background: var(--el-fill-color-lighter); }
.i2i-src { display: flex; align-items: center; gap: 10px; margin-top: 10px; flex-wrap: wrap; }
.i2i-thumb { width: 56px; height: 56px; border-radius: 6px; }
</style>
