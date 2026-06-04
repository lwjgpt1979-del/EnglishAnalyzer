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

async function setQuota(t: InstitutionTeacher) {
  const { value } = await ElMessageBox.prompt(
    '每月出卷上限（留空=不限）', '设置额度',
    { inputValue: t.monthly_paper_quota?.toString() ?? '' })
  const q = value === '' || value == null ? null : Number(value)
  if (q !== null && (Number.isNaN(q) || q < 0)) { ElMessage.error('请输入非负整数'); return }
  await setTeacherQuota(t.id, q)
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
      <el-table-column label="月出卷额度">
        <template #default="{ row }">{{ row.monthly_paper_quota ?? '不限' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="180">
        <template #default="{ row }">
          <el-button type="primary" text @click="setQuota(row)">设额度</el-button>
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
