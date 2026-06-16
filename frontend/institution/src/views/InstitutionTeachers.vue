<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  generateTeacherInviteCode, listTeachers, removeTeacher, setTeacherQuota,
  type InstitutionTeacher,
} from '../api/institution'

const teachers = ref<InstitutionTeacher[]>([])
const inviteCode = ref('')
const inviteExpire = ref('')

async function load() {
  teachers.value = await listTeachers()
}

async function genCode() {
  const r = await generateTeacherInviteCode()
  inviteCode.value = r.code
  inviteExpire.value = r.expires_at.slice(0, 16).replace('T', ' ')
}

async function remove(t: InstitutionTeacher) {
  await ElMessageBox.confirm(`确认把「${t.nickname || t.id}」移出机构？`, '提示', { type: 'warning' })
  await removeTeacher(t.id)
  ElMessage.success('已移出')
  await load()
}

function _parseQuota(v: string | null): number | null | undefined {
  if (v === '' || v == null) return null   // 留空=随机构池共享
  const n = Number(v)
  if (Number.isNaN(n) || n < 0) return undefined   // 非法
  return n
}

async function setQuota(t: InstitutionTeacher) {
  // 池内子上限：出卷 + 批改，留空=随机构池共享（先到先得）
  const r1 = await ElMessageBox.prompt(
    '每月出卷子上限（留空=随机构池共享）', '设置子额度（1/2）',
    { inputValue: t.monthly_paper_quota?.toString() ?? '' }).catch(() => null)
  if (!r1) return
  const paper = _parseQuota(r1.value)
  if (paper === undefined) { ElMessage.error('请输入非负整数'); return }
  const r2 = await ElMessageBox.prompt(
    '每月批改/点评子上限（留空=随机构池共享）', '设置子额度（2/2）',
    { inputValue: t.monthly_grading_quota?.toString() ?? '' }).catch(() => null)
  if (!r2) return
  const grading = _parseQuota(r2.value)
  if (grading === undefined) { ElMessage.error('请输入非负整数'); return }
  await setTeacherQuota(t.id, paper, grading)
  ElMessage.success('已设置')
  await load()
}

onMounted(load)
</script>

<template>
  <div>
    <h2 class="title">老师管理</h2>
    <el-card style="margin-bottom: 16px">
      <el-button type="primary" @click="genCode">生成机构邀请码</el-button>
      <span v-if="inviteCode" class="code-tip">
        邀请码：<b>{{ inviteCode }}</b>（有效期至 {{ inviteExpire }}）— 让老师在小程序「加入机构」输入
      </span>
    </el-card>
    <el-table :data="teachers" border>
      <el-table-column prop="nickname" label="昵称" />
      <el-table-column prop="phone" label="电话" />
      <el-table-column prop="subject" label="科目" />
      <el-table-column prop="cert_status" label="认证状态" />
      <el-table-column label="出卷子上限">
        <template #default="{ row }">{{ row.monthly_paper_quota ?? '随池' }}</template>
      </el-table-column>
      <el-table-column label="批改子上限">
        <template #default="{ row }">{{ row.monthly_grading_quota ?? '随池' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="180">
        <template #default="{ row }">
          <el-button type="primary" text @click="setQuota(row)">设子额度</el-button>
          <el-button type="danger" text @click="remove(row)">移出机构</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.title { margin: 0 0 16px; font-size: 18px; }
.code-tip { margin-left: 16px; color: #555; }
</style>
