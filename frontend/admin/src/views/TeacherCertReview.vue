<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listTeachersForAdmin, reviewTeacherCert } from '../api/admin'
import type { AdminTeacherItem } from '../types'

const rows = ref<AdminTeacherItem[]>([])
const total = ref(0)
const loading = ref(false)
const filterStatus = ref('pending')
const skip = ref(0)
const PAGE_SIZE = 50

async function load() {
  loading.value = true
  try {
    const result = await listTeachersForAdmin({
      cert_status: filterStatus.value || undefined,
      skip: skip.value,
      limit: PAGE_SIZE,
    })
    rows.value = result.items
    total.value = result.total
  } catch (e: any) {
    ElMessage.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function onApprove(row: AdminTeacherItem) {
  await ElMessageBox.confirm(
    `确认通过「${row.nickname || row.teacher_id}」的教师认证？`,
    '认证通过',
    { type: 'success', confirmButtonText: '通过', cancelButtonText: '取消' },
  )
  try {
    const result = await reviewTeacherCert(row.teacher_id, true)
    ElMessage.success('已通过认证')
    patchRow(result)
  } catch (e: any) {
    ElMessage.error(e?.message || '操作失败')
  }
}

async function onReject(row: AdminTeacherItem) {
  let reason = ''
  await ElMessageBox.prompt('请输入拒绝理由（选填）', '拒绝认证', {
    confirmButtonText: '拒绝',
    cancelButtonText: '取消',
    inputPlaceholder: '如：材料不清晰、信息不完整…',
    beforeClose: (action, _ctx, done) => {
      if (action === 'confirm') {
        // @ts-ignore
        reason = _ctx.inputValue || ''
      }
      done()
    },
  }).catch(() => { throw new Error('cancelled') })
  try {
    const result = await reviewTeacherCert(row.teacher_id, false, reason || undefined)
    ElMessage.warning('已拒绝认证')
    patchRow(result)
  } catch (e: any) {
    if ((e as Error).message !== 'cancelled') ElMessage.error(e?.message || '操作失败')
  }
}

function patchRow(updated: AdminTeacherItem) {
  const idx = rows.value.findIndex(r => r.teacher_id === updated.teacher_id)
  if (idx !== -1) {
    rows.value[idx] = updated
    // 若当前在筛选 pending，审核后该行不再是 pending，移出列表
    if (filterStatus.value === 'pending' && updated.cert_status !== 'pending') {
      rows.value.splice(idx, 1)
      total.value = Math.max(0, total.value - 1)
    }
  }
}

function statusTag(s: string): 'warning' | 'success' | 'danger' | 'info' {
  return { pending: 'warning', certified: 'success', rejected: 'danger', uncertified: 'info' }[s] as any || 'info'
}
function statusLabel(s: string): string {
  return { pending: '待审核', certified: '已认证', rejected: '已拒绝', uncertified: '未提交' }[s] || s
}

onMounted(load)
</script>

<template>
  <div>
    <!-- 筛选工具栏 -->
    <div style="margin-bottom: 16px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap;">
      <el-select
        v-model="filterStatus"
        placeholder="认证状态"
        style="width: 130px"
        @change="() => { skip = 0; load() }"
      >
        <el-option label="全部" value="" />
        <el-option label="待审核" value="pending" />
        <el-option label="已认证" value="certified" />
        <el-option label="已拒绝" value="rejected" />
        <el-option label="未提交" value="uncertified" />
      </el-select>
      <el-button @click="load" :loading="loading">🔄 刷新</el-button>
      <span style="color: #909399; font-size: 13px;">
        共 {{ total }} 名老师
      </span>
    </div>

    <!-- 教师列表 -->
    <el-table v-loading="loading" :data="rows" border style="width: 100%">
      <el-table-column label="昵称/ID" min-width="140">
        <template #default="{ row }">
          <span>{{ row.nickname || '—' }}</span>
          <div style="font-size: 11px; color: #c0c4cc;">{{ row.teacher_id.slice(0, 8) }}…</div>
        </template>
      </el-table-column>
      <el-table-column prop="phone" label="手机号" width="130" />
      <el-table-column prop="subject" label="科目" width="80" />
      <el-table-column label="认证状态" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="statusTag(row.cert_status)" size="small">{{ statusLabel(row.cert_status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="认证材料" width="110" align="center">
        <template #default="{ row }">
          <a v-if="row.cert_doc_url" :href="row.cert_doc_url" target="_blank" style="color: #409eff; font-size: 13px;">
            查看材料
          </a>
          <span v-else style="color: #c0c4cc; font-size: 13px;">未上传</span>
        </template>
      </el-table-column>
      <el-table-column prop="max_students" label="最大学生" width="90" align="center" />
      <el-table-column label="提交时间" width="160">
        <template #default="{ row }">
          {{ row.created_at ? row.created_at.slice(0, 16).replace('T', ' ') : '—' }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button
            size="small"
            type="success"
            :disabled="row.cert_status === 'certified'"
            @click="onApprove(row)"
          >✅ 通过</el-button>
          <el-button
            size="small"
            type="danger"
            plain
            :disabled="row.cert_status === 'rejected'"
            @click="onReject(row)"
          >❌ 拒绝</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div style="margin-top: 16px; display: flex; justify-content: flex-end;">
      <el-pagination
        :current-page="Math.floor(skip / PAGE_SIZE) + 1"
        :page-size="PAGE_SIZE"
        :total="total"
        layout="prev, pager, next, total"
        @current-change="(p: number) => { skip = (p - 1) * PAGE_SIZE; load() }"
      />
    </div>
  </div>
</template>

