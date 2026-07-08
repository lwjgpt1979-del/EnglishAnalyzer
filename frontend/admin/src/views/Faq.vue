<script setup lang="ts">
import AppDialog from '../components/AppDialog.vue'
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listFaq, createFaq, updateFaq, deleteFaq, type FaqItem } from '../api/admin'
import { QuestionFilled } from '@element-plus/icons-vue'

const rows = ref<FaqItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 50
const loading = ref(false)
const audience = ref('all')

const AUD: Record<string, string> = { c: 'C端(学生/亲人)', b: 'B端(机构)', all: '全部' }

async function load() {
  loading.value = true
  try {
    const r = await listFaq({ audience: audience.value, skip: (page.value - 1) * pageSize, limit: pageSize })
    rows.value = r.items; total.value = r.total
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}
// 受众筛选变更:回到第一页
function reload() { page.value = 1; load() }

const dialog = ref(false)
const editing = ref<FaqItem | null>(null)
const form = reactive({ audience: 'c', category: '通用', question: '', answer: '', sort_order: 0 })

function openCreate() {
  editing.value = null
  Object.assign(form, { audience: 'c', category: '通用', question: '', answer: '', sort_order: 0 })
  dialog.value = true
}
function openEdit(r: FaqItem) {
  editing.value = r
  Object.assign(form, { audience: r.audience, category: r.category, question: r.question, answer: r.answer, sort_order: r.sort_order })
  dialog.value = true
}
async function save() {
  if (!form.question.trim() || !form.answer.trim()) { ElMessage.warning('问题和答案必填'); return }
  try {
    if (editing.value) await updateFaq(editing.value.id, { ...form })
    else await createFaq({ ...form })
    ElMessage.success('已保存'); dialog.value = false; await load()
  } catch (e: any) { ElMessage.error(e?.message || '保存失败') }
}
async function toggle(r: FaqItem) {
  try { await updateFaq(r.id, { is_active: !r.is_active }); await load() }
  catch (e: any) { ElMessage.error(e?.message || '操作失败') }
}
async function remove(r: FaqItem) {
  try {
    await ElMessageBox.confirm(`删除「${r.question}」？`, '删除', { type: 'warning' })
    await deleteFaq(r.id); ElMessage.success('已删除'); await load()
  } catch (e: any) { if (e !== 'cancel') ElMessage.error(e?.message || '删除失败') }
}

onMounted(load)
</script>

<template>
  <div class="faq">
    <div class="toolbar">
      <h2><el-icon style="vertical-align:-2px;margin-right:4px"><QuestionFilled /></el-icon>FAQ 自助管理</h2>
      <div class="filters">
        <el-radio-group v-model="audience" @change="reload">
          <el-radio-button label="all">全部</el-radio-button>
          <el-radio-button label="c">C端</el-radio-button>
          <el-radio-button label="b">B端</el-radio-button>
        </el-radio-group>
        <el-button type="primary" @click="openCreate">新增 FAQ</el-button>
        <el-button @click="load">刷新</el-button>
      </div>
    </div>
    <p class="hint">小程序「帮助与反馈」自助查询（§13.2）。按 受众→分类→排序 展示。</p>

    <el-table :data="rows" v-loading="loading" stripe>
      <el-table-column label="受众" width="90">
        <template #default="{ row }"><el-tag size="small">{{ AUD[row.audience] || row.audience }}</el-tag></template>
      </el-table-column>
      <el-table-column prop="category" label="分类" width="120" />
      <el-table-column prop="question" label="问题" min-width="220" show-overflow-tooltip />
      <el-table-column prop="answer" label="答案" min-width="240" show-overflow-tooltip />
      <el-table-column prop="sort_order" label="排序" width="70" />
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '启用' : '停用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button size="small" link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" link @click="toggle(row)">{{ row.is_active ? '停用' : '启用' }}</el-button>
          <el-button size="small" link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div style="display:flex;justify-content:flex-end;margin-top:12px">
      <el-pagination layout="total, prev, pager, next, jumper" :total="total"
        :page-size="pageSize" v-model:current-page="page" @current-change="load" />
    </div>

    <AppDialog v-model="dialog" :title="editing ? '编辑 FAQ' : '新增 FAQ'" width="560px">
      <el-form label-width="72px">
        <el-form-item label="受众">
          <el-radio-group v-model="form.audience">
            <el-radio-button label="c">C端</el-radio-button>
            <el-radio-button label="b">B端</el-radio-button>
            <el-radio-button label="all">全部</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="分类"><el-input v-model="form.category" maxlength="40" placeholder="如：会员/退款/上传" /></el-form-item>
        <el-form-item label="问题"><el-input v-model="form.question" maxlength="200" placeholder="用户视角的问题" /></el-form-item>
        <el-form-item label="答案"><el-input v-model="form.answer" type="textarea" :rows="4" placeholder="解答内容" /></el-form-item>
        <el-form-item label="排序"><el-input-number v-model="form.sort_order" :min="0" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </AppDialog>
  </div>
</template>

<style scoped>
.faq { padding: 16px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 12px; }
.filters { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.hint { color: #909399; font-size: 13px; margin: 0 0 16px; }
.muted { color: #909399; font-size: 12px; }
.total { margin-top: 12px; text-align: right; }
</style>
