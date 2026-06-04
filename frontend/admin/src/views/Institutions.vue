<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createInstitution, listInstitutions, approveInstitution, rejectInstitution,
  type AdminInstitution,
} from '../api/admin'

const form = reactive({ name: '', contact_phone: '', province_code: '', city_code: '', address: '' })
const filter = ref('')
const rows = ref<AdminInstitution[]>([])

async function load() { rows.value = await listInstitutions(filter.value || undefined) }

async function submit() {
  if (!form.name) { ElMessage.warning('请填机构名称'); return }
  await createInstitution({ ...form })
  ElMessage.success('已录入（待审核）')
  Object.assign(form, { name: '', contact_phone: '', province_code: '', city_code: '', address: '' })
  await load()
}

async function approve(row: AdminInstitution) {
  const { value: uname } = await ElMessageBox.prompt('为该机构设置管理员登录用户名', '通过审核', {
    inputPattern: /.{3,}/, inputErrorMessage: '至少 3 个字符',
  })
  const r = await approveInstitution(row.id, uname)
  await ElMessageBox.alert(
    `用户名：${r.admin_username}\n初始密码：${r.password}\n请复制并线下转交机构，本密码仅此一次显示。`,
    '机构账号已开通', { confirmButtonText: '我已复制' })
  await load()
}

async function reject(row: AdminInstitution) {
  await ElMessageBox.confirm(`确认拒绝「${row.name}」？将置为 suspended。`, '提示', { type: 'warning' })
  await rejectInstitution(row.id)
  ElMessage.success('已拒绝')
  await load()
}

onMounted(load)
</script>

<template>
  <div>
    <h2 class="title">机构审核</h2>
    <el-card style="margin-bottom: 16px">
      <el-form inline>
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="电话"><el-input v-model="form.contact_phone" /></el-form-item>
        <el-form-item label="省编码"><el-input v-model="form.province_code" style="width: 100px" /></el-form-item>
        <el-form-item label="市编码"><el-input v-model="form.city_code" style="width: 100px" /></el-form-item>
        <el-form-item label="地址"><el-input v-model="form.address" /></el-form-item>
        <el-form-item><el-button type="primary" @click="submit">录入待审核机构</el-button></el-form-item>
      </el-form>
    </el-card>

    <el-select v-model="filter" placeholder="全部状态" clearable style="width: 160px; margin-bottom: 12px" @change="load">
      <el-option label="待审核" value="pending" />
      <el-option label="已通过" value="active" />
      <el-option label="已拒绝/冻结" value="suspended" />
    </el-select>

    <el-table :data="rows" border>
      <el-table-column prop="name" label="名称" />
      <el-table-column prop="contact_phone" label="电话" />
      <el-table-column prop="status" label="状态" />
      <el-table-column prop="created_at" label="申请时间">
        <template #default="{ row }">{{ row.created_at.slice(0, 10) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="180">
        <template #default="{ row }">
          <template v-if="row.status === 'pending'">
            <el-button text type="primary" @click="approve(row)">通过</el-button>
            <el-button text type="danger" @click="reject(row)">拒绝</el-button>
          </template>
          <span v-else>—</span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.title { margin: 0 0 16px; font-size: 18px; }
</style>
