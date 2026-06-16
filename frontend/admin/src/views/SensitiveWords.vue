<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listSensitiveWords, addSensitiveWord, batchAddSensitiveWords,
  updateSensitiveWord, deleteSensitiveWord, type SensitiveWordItem,
} from '../api/admin'

const rows = ref<SensitiveWordItem[]>([])
const total = ref(0)
const loading = ref(false)
const category = ref('all')
const q = ref('')

const CAT: Record<string, string> = { political: '政治敏感', porn: '色情', violence: '暴力', ad: '广告引流', other: '其他' }
const ACT: Record<string, string> = { block: '阻断', mask: '打码' }

async function load() {
  loading.value = true
  try {
    const r = await listSensitiveWords({ category: category.value, q: q.value || undefined, limit: 500 })
    rows.value = r.items; total.value = r.total
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}

// 新增
const dialog = ref(false)
const form = reactive({ word: '', category: 'other', action: 'block' })
function openAdd() { Object.assign(form, { word: '', category: 'other', action: 'block' }); dialog.value = true }
async function save() {
  if (!form.word.trim()) { ElMessage.warning('请输入敏感词'); return }
  try { await addSensitiveWord({ ...form }); ElMessage.success('已添加'); dialog.value = false; await load() }
  catch (e: any) { ElMessage.error(e?.message || '添加失败') }
}

// 批量导入
const batchDialog = ref(false)
const batchForm = reactive({ text: '', category: 'other', action: 'block' })
function openBatch() { Object.assign(batchForm, { text: '', category: 'other', action: 'block' }); batchDialog.value = true }
async function saveBatch() {
  const words = batchForm.text.split(/[\s,，\n]+/).map(s => s.trim()).filter(Boolean)
  if (!words.length) { ElMessage.warning('请输入敏感词（换行或逗号分隔）'); return }
  try {
    const r = await batchAddSensitiveWords({ words, category: batchForm.category, action: batchForm.action })
    ElMessage.success(`已导入 ${r.added} 个`); batchDialog.value = false; await load()
  } catch (e: any) { ElMessage.error(e?.message || '导入失败') }
}

async function toggle(r: SensitiveWordItem) {
  try { await updateSensitiveWord(r.id, { is_active: !r.is_active }); await load() }
  catch (e: any) { ElMessage.error(e?.message || '操作失败') }
}
async function setAction(r: SensitiveWordItem, action: string) {
  try { await updateSensitiveWord(r.id, { action }); await load() }
  catch (e: any) { ElMessage.error(e?.message || '操作失败') }
}
async function remove(r: SensitiveWordItem) {
  try {
    await ElMessageBox.confirm(`删除「${r.word}」？`, '删除', { type: 'warning' })
    await deleteSensitiveWord(r.id); ElMessage.success('已删除'); await load()
  } catch (e: any) { if (e !== 'cancel') ElMessage.error(e?.message || '删除失败') }
}

onMounted(load)
</script>

<template>
  <div class="sw">
    <div class="toolbar">
      <h2>🛡️ 敏感词库</h2>
      <div class="filters">
        <el-select v-model="category" style="width: 130px" @change="load">
          <el-option label="全部分类" value="all" />
          <el-option v-for="(v, k) in CAT" :key="k" :label="v" :value="k" />
        </el-select>
        <el-input v-model="q" placeholder="搜索词" style="width: 160px" clearable @keyup.enter="load" @clear="load" />
        <el-button type="primary" @click="openAdd">新增</el-button>
        <el-button @click="openBatch">批量导入</el-button>
        <el-button @click="load">刷新</el-button>
      </div>
    </div>
    <p class="hint">用于 AI 报告 / 作文批改 / 老师题目 / 学生上传内容过滤（§5.6）。阻断=命中即拒绝提交；打码=替换为 ***。词库变更约 30 秒内生效。</p>

    <el-table :data="rows" v-loading="loading" stripe>
      <el-table-column prop="word" label="敏感词" min-width="160" />
      <el-table-column label="分类" width="120"><template #default="{ row }"><el-tag size="small">{{ CAT[row.category] || row.category }}</el-tag></template></el-table-column>
      <el-table-column label="处理" width="120">
        <template #default="{ row }">
          <el-tag :type="row.action === 'block' ? 'danger' : 'warning'" size="small">{{ ACT[row.action] || row.action }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }"><el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '启用' : '停用' }}</el-tag></template>
      </el-table-column>
      <el-table-column label="操作" width="260" fixed="right">
        <template #default="{ row }">
          <el-button size="small" link @click="setAction(row, row.action === 'block' ? 'mask' : 'block')">转{{ row.action === 'block' ? '打码' : '阻断' }}</el-button>
          <el-button size="small" link @click="toggle(row)">{{ row.is_active ? '停用' : '启用' }}</el-button>
          <el-button size="small" link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div class="muted total">共 {{ total }} 条</div>

    <el-dialog v-model="dialog" title="新增敏感词" width="420px">
      <el-form label-width="72px">
        <el-form-item label="敏感词"><el-input v-model="form.word" maxlength="64" /></el-form-item>
        <el-form-item label="分类">
          <el-select v-model="form.category"><el-option v-for="(v, k) in CAT" :key="k" :label="v" :value="k" /></el-select>
        </el-form-item>
        <el-form-item label="处理">
          <el-radio-group v-model="form.action">
            <el-radio-button label="block">阻断</el-radio-button>
            <el-radio-button label="mask">打码</el-radio-button>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer><el-button @click="dialog = false">取消</el-button><el-button type="primary" @click="save">添加</el-button></template>
    </el-dialog>

    <el-dialog v-model="batchDialog" title="批量导入敏感词" width="480px">
      <el-form label-width="72px">
        <el-form-item label="词列表"><el-input v-model="batchForm.text" type="textarea" :rows="6" placeholder="每行一个，或用逗号分隔" /></el-form-item>
        <el-form-item label="分类">
          <el-select v-model="batchForm.category"><el-option v-for="(v, k) in CAT" :key="k" :label="v" :value="k" /></el-select>
        </el-form-item>
        <el-form-item label="处理">
          <el-radio-group v-model="batchForm.action">
            <el-radio-button label="block">阻断</el-radio-button>
            <el-radio-button label="mask">打码</el-radio-button>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer><el-button @click="batchDialog = false">取消</el-button><el-button type="primary" @click="saveBatch">导入</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.sw { padding: 16px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 12px; }
.filters { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.hint { color: #909399; font-size: 13px; margin: 0 0 16px; }
.muted { color: #909399; font-size: 12px; }
.total { margin-top: 12px; text-align: right; }
</style>
