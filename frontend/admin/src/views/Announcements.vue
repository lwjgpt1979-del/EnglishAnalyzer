<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listAnnouncements, createAnnouncement, updateAnnouncement, deleteAnnouncement,
  type AnnouncementItem,
} from '../api/admin'

const rows = ref<AnnouncementItem[]>([])
const total = ref(0)
const loading = ref(false)

const AUD: Record<string, string> = { all: '全平台', institution: '指定机构', grade: '指定年级' }
function fmt(s: string | null) { return s ? s.replace('T', ' ').slice(0, 16) : '不限' }

async function load() {
  loading.value = true
  try { const r = await listAnnouncements({ limit: 100 }); rows.value = r.items; total.value = r.total }
  catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}

const dialog = ref(false)
const form = reactive({
  title: '', content: '', audience: 'all', targets: '', pinned: false, range: [] as string[],
})
function openCreate() {
  Object.assign(form, { title: '', content: '', audience: 'all', targets: '', pinned: false, range: [] })
  dialog.value = true
}
async function save() {
  if (!form.title.trim() || !form.content.trim()) { ElMessage.warning('标题和内容必填'); return }
  const target_values = form.targets.split(/[\s,，\n]+/).map(s => s.trim()).filter(Boolean)
  if (form.audience !== 'all' && !target_values.length) {
    ElMessage.warning('定向公告需填写目标（机构ID或年级名）'); return
  }
  const body: Record<string, unknown> = {
    title: form.title, content: form.content, audience: form.audience,
    target_values, pinned: form.pinned,
  }
  if (form.range && form.range.length === 2) { body.starts_at = form.range[0]; body.ends_at = form.range[1] }
  try { await createAnnouncement(body); ElMessage.success('已发布'); dialog.value = false; await load() }
  catch (e: any) { ElMessage.error(e?.message || '发布失败') }
}
async function togglePin(r: AnnouncementItem) {
  try { await updateAnnouncement(r.id, { pinned: !r.pinned }); await load() }
  catch (e: any) { ElMessage.error(e?.message || '操作失败') }
}
async function toggleActive(r: AnnouncementItem) {
  try { await updateAnnouncement(r.id, { is_active: !r.is_active }); await load() }
  catch (e: any) { ElMessage.error(e?.message || '操作失败') }
}
async function remove(r: AnnouncementItem) {
  try {
    await ElMessageBox.confirm(`删除公告「${r.title}」？`, '删除', { type: 'warning' })
    await deleteAnnouncement(r.id); ElMessage.success('已删除'); await load()
  } catch (e: any) { if (e !== 'cancel') ElMessage.error(e?.message || '删除失败') }
}

onMounted(load)
</script>

<template>
  <div class="ann">
    <div class="toolbar">
      <h2>📢 公告管理</h2>
      <div class="filters">
        <el-button type="primary" @click="openCreate">发布公告</el-button>
        <el-button @click="load">刷新</el-button>
      </div>
    </div>
    <p class="hint">全平台或定向（指定机构/年级）公告，用户在小程序「消息中心 → 公告」查看（§5.6）。</p>

    <el-table :data="rows" v-loading="loading" stripe>
      <el-table-column label="标题" min-width="200">
        <template #default="{ row }">
          <el-tag v-if="row.pinned" type="danger" size="small" effect="dark" style="margin-right:4px">置顶</el-tag>{{ row.title }}
        </template>
      </el-table-column>
      <el-table-column label="受众" width="160">
        <template #default="{ row }">
          {{ AUD[row.audience] || row.audience }}
          <span v-if="row.audience !== 'all'" class="muted">（{{ (row.target_values || []).length }}个）</span>
        </template>
      </el-table-column>
      <el-table-column label="生效时间" width="280">
        <template #default="{ row }">{{ fmt(row.starts_at) }} ~ {{ fmt(row.ends_at) }}</template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }"><el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '展示中' : '已停用' }}</el-tag></template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button size="small" link @click="togglePin(row)">{{ row.pinned ? '取消置顶' : '置顶' }}</el-button>
          <el-button size="small" link @click="toggleActive(row)">{{ row.is_active ? '停用' : '启用' }}</el-button>
          <el-button size="small" link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div class="muted total">共 {{ total }} 条</div>

    <el-dialog v-model="dialog" title="发布公告" width="560px">
      <el-form label-width="90px">
        <el-form-item label="标题"><el-input v-model="form.title" maxlength="120" placeholder="公告标题" /></el-form-item>
        <el-form-item label="内容"><el-input v-model="form.content" type="textarea" :rows="5" placeholder="公告正文" /></el-form-item>
        <el-form-item label="受众">
          <el-radio-group v-model="form.audience">
            <el-radio-button label="all">全平台</el-radio-button>
            <el-radio-button label="institution">指定机构</el-radio-button>
            <el-radio-button label="grade">指定年级</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="form.audience !== 'all'" :label="form.audience === 'grade' ? '年级' : '机构ID'">
          <el-input v-model="form.targets" type="textarea" :rows="2"
            :placeholder="form.audience === 'grade' ? '如：小学5年级（多个换行/逗号分隔）' : '机构 UUID（多个换行/逗号分隔）'" />
        </el-form-item>
        <el-form-item label="生效时间">
          <el-date-picker v-model="form.range" type="datetimerange" value-format="YYYY-MM-DDTHH:mm:ss"
            start-placeholder="开始(可空)" end-placeholder="结束(可空)" />
        </el-form-item>
        <el-form-item label="置顶"><el-switch v-model="form.pinned" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialog = false">取消</el-button><el-button type="primary" @click="save">发布</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.ann { padding: 16px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 12px; }
.filters { display: flex; gap: 12px; align-items: center; }
.hint { color: #909399; font-size: 13px; margin: 0 0 16px; }
.muted { color: #909399; font-size: 12px; }
.total { margin-top: 12px; text-align: right; }
</style>
