<script setup lang="ts">
import AppDialog from '../components/AppDialog.vue'
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { reactive } from 'vue'
import { listTeachersForAdmin, reviewTeacherCert, claimTeacherCert, getCertQuality, setTeacherLimitOverride, type CertQuality } from '../api/admin'
import type { AdminTeacherItem } from '../types'
import { Refresh, Pointer, CircleCheck, CircleClose } from '@element-plus/icons-vue'

// 个体额度覆盖（§5.6）
const limitDialog = ref(false)
const limitTarget = ref<AdminTeacherItem | null>(null)
const limitForm = reactive<{ max_students: number | null; monthly_paper_quota: number | null; monthly_grading_quota: number | null }>(
  { max_students: null, monthly_paper_quota: null, monthly_grading_quota: null })
function openLimit(row: AdminTeacherItem) {
  limitTarget.value = row
  limitForm.max_students = row.max_students ?? null
  limitForm.monthly_paper_quota = null
  limitForm.monthly_grading_quota = null
  limitDialog.value = true
}
async function saveLimit() {
  if (!limitTarget.value) return
  try {
    await setTeacherLimitOverride(limitTarget.value.teacher_id, { ...limitForm })
    ElMessage.success('已保存额度覆盖'); limitDialog.value = false; load()
  } catch (e: any) { ElMessage.error(e?.message || '保存失败') }
}

const quality = ref<CertQuality | null>(null)
async function loadQuality() {
  try { quality.value = await getCertQuality(30) } catch { /* ignore */ }
}
async function onClaim(row: AdminTeacherItem) {
  try {
    await claimTeacherCert(row.teacher_id)
    ElMessage.success('已认领，可开始审核')
  } catch (e: any) { ElMessage.error(e?.message || '认领失败') }
}

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
    loadQuality()
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
  if (!reason.trim()) { ElMessage.warning('驳回必须填写原因'); return }
  try {
    const result = await reviewTeacherCert(row.teacher_id, false, reason)
    ElMessage.warning('已拒绝认证')
    patchRow(result)
    loadQuality()
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

onMounted(() => { load(); loadQuality() })
</script>

<template>
  <div>
    <!-- 审核质量监控（§5.8）-->
    <el-row v-if="quality" :gutter="12" style="margin-bottom: 16px">
      <el-col :span="4"><el-card shadow="hover" body-style="padding:12px"><el-statistic title="近30天申请" :value="quality.applied" /></el-card></el-col>
      <el-col :span="4"><el-card shadow="hover" body-style="padding:12px"><el-statistic title="已审核" :value="quality.reviewed" /></el-card></el-col>
      <el-col :span="4"><el-card shadow="hover" body-style="padding:12px"><el-statistic title="通过率(%)" :value="quality.pass_rate_pct" /></el-card></el-col>
      <el-col :span="4"><el-card shadow="hover" body-style="padding:12px" :class="quality.pending > 0 ? 'pend' : ''"><el-statistic title="待审核" :value="quality.pending" /></el-card></el-col>
      <el-col :span="8"><el-card shadow="hover" body-style="padding:12px">
        <div class="rj-title">驳回原因 Top5</div>
        <div v-for="r in quality.reject_reasons_top" :key="r.reason" class="rj-row">
          <span class="rj-reason">{{ r.reason }}</span><span class="rj-cnt">{{ r.count }}</span>
        </div>
        <div v-if="!quality.reject_reasons_top.length" class="muted">暂无驳回</div>
      </el-card></el-col>
    </el-row>

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
      <el-button @click="load" :loading="loading"><el-icon style="vertical-align:-2px;margin-right:4px"><Refresh /></el-icon>刷新</el-button>
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
      <el-table-column label="操作" width="230" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="row.cert_status === 'pending'"
            size="small"
            plain
            @click="onClaim(row)"
          ><el-icon style="vertical-align:-2px;margin-right:4px"><Pointer /></el-icon>认领</el-button>
          <el-button
            size="small"
            type="success"
            :disabled="row.cert_status === 'certified'"
            @click="onApprove(row)"
          ><el-icon style="vertical-align:-2px;margin-right:4px"><CircleCheck /></el-icon>通过</el-button>
          <el-button
            size="small"
            type="danger"
            plain
            :disabled="row.cert_status === 'rejected'"
            @click="onReject(row)"
          ><el-icon style="vertical-align:-2px;margin-right:4px"><CircleClose /></el-icon>拒绝</el-button>
          <el-button size="small" link @click="openLimit(row)">额度</el-button>
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

    <AppDialog v-model="limitDialog" title="老师额度覆盖（留空=随全局默认）" width="440px">
      <el-form label-width="150px">
        <el-form-item label="绑定学生上限"><el-input-number v-model="limitForm.max_students" :min="0" /></el-form-item>
        <el-form-item label="月度出卷上限"><el-input-number v-model="limitForm.monthly_paper_quota" :min="0" /></el-form-item>
        <el-form-item label="月度批改上限"><el-input-number v-model="limitForm.monthly_grading_quota" :min="0" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="limitDialog = false">取消</el-button><el-button type="primary" @click="saveLimit">保存</el-button></template>
    </AppDialog>
  </div>
</template>

<style scoped>
.pend { background: #fdf6ec; }
.rj-title { font-size: 13px; color: #909399; margin-bottom: 6px; }
.rj-row { display: flex; justify-content: space-between; font-size: 13px; padding: 2px 0; }
.rj-reason { color: #606266; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 80%; }
.rj-cnt { color: #f56c6c; font-weight: 600; }
.muted { color: #c0c4cc; font-size: 12px; }
</style>

