<script setup lang="ts">
import AppDialog from '../components/AppDialog.vue'
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listUsers, banUser, unbanUser, type AdminUserItem } from '../api/admin'

const rows = ref<AdminUserItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 50
const loading = ref(false)
const q = ref('')

const ROLE: Record<string, string> = { student: '学生', teacher: '教师', relative: '家长' }

async function load() {
  loading.value = true
  try {
    const r = await listUsers({ q: q.value || undefined, skip: (page.value - 1) * pageSize, limit: pageSize })
    rows.value = r.items
    total.value = r.total
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}
function reload() { page.value = 1; load() }

// 封禁弹窗（时长 7/30/永久 + 原因）
const banOpen = ref(false)
const banning = ref(false)
const banForm = reactive({ id: '', label: '', days: 7 as number | null, reason: '' })
function openBan(row: AdminUserItem) {
  banForm.id = row.id
  banForm.label = row.nickname || row.phone || row.id.slice(0, 8)
  banForm.days = 7
  banForm.reason = ''
  banOpen.value = true
}
async function submitBan() {
  if (!banForm.reason.trim()) { ElMessage.warning('封禁原因必填'); return }
  banning.value = true
  try {
    await banUser(banForm.id, banForm.reason.trim(), banForm.days)
    ElMessage.success('已封禁')
    banOpen.value = false
    await load()
  } catch (e: any) { ElMessage.error(e?.message || '操作失败') }
  finally { banning.value = false }
}

async function onUnban(row: AdminUserItem) {
  try {
    await ElMessageBox.confirm('确认解封该用户？', '解封')
    await unbanUser(row.id)
    ElMessage.success('已解封')
    await load()
  } catch (e: any) { if (e !== 'cancel') ElMessage.error(e?.message || '操作失败') }
}

function fmt(s: string | null) { return s ? s.replace('T', ' ').slice(0, 16) : '-' }

onMounted(load)
</script>

<template>
  <div class="users">
    <div class="toolbar">
      <h2>用户管理</h2>
      <div class="search">
        <el-input v-model="q" placeholder="昵称 / 手机号 / 用户ID" style="width:280px" clearable
          @keyup.enter="reload" @clear="reload" />
        <el-button type="primary" @click="reload">搜索</el-button>
      </div>
    </div>

    <el-table :data="rows" v-loading="loading" stripe>
      <el-table-column label="用户" min-width="160">
        <template #default="{ row }">
          <div>{{ row.nickname || '(未设昵称)' }}</div>
          <div class="muted">{{ row.phone || row.id.slice(0, 8) }}</div>
        </template>
      </el-table-column>
      <el-table-column label="角色" width="90">
        <template #default="{ row }">{{ ROLE[row.role] || row.role }}</template>
      </el-table-column>
      <el-table-column label="状态" width="160">
        <template #default="{ row }">
          <el-tag v-if="!row.banned" type="success" size="small">正常</el-tag>
          <template v-else>
            <el-tag type="danger" size="small">{{ row.ban_type === 'permanent' ? '永久封禁' : '临时封禁' }}</el-tag>
            <div v-if="row.banned_until" class="muted">至 {{ fmt(row.banned_until) }}</div>
          </template>
        </template>
      </el-table-column>
      <el-table-column label="封禁原因" min-width="160">
        <template #default="{ row }"><span class="muted">{{ row.ban_reason || '-' }}</span></template>
      </el-table-column>
      <el-table-column label="注册时间" width="150">
        <template #default="{ row }">{{ fmt(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!row.banned" size="small" type="danger" link @click="openBan(row)">封禁</el-button>
          <el-button v-else size="small" type="primary" link @click="onUnban(row)">解封</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div style="display:flex;justify-content:flex-end;margin-top:12px">
      <el-pagination layout="total, prev, pager, next, jumper" :total="total"
        :page-size="pageSize" v-model:current-page="page" @current-change="load" />
    </div>

    <AppDialog v-model="banOpen" :title="`封禁 ${banForm.label}`" width="460px">
      <el-form label-width="80px">
        <el-form-item label="封禁时长">
          <el-radio-group v-model="banForm.days">
            <el-radio-button :value="7">7 天</el-radio-button>
            <el-radio-button :value="30">30 天</el-radio-button>
            <el-radio-button :value="null">永久</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="封禁原因">
          <el-input v-model="banForm.reason" type="textarea" :rows="3"
            placeholder="必填，留存内部记录（如：伪造支付截图申请退款）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="banOpen = false">取消</el-button>
        <el-button type="danger" :loading="banning" @click="submitBan">确认封禁</el-button>
      </template>
    </AppDialog>
  </div>
</template>

<style scoped>
.users { padding: 16px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 12px; }
.search { display: flex; gap: 8px; }
.muted { color: #909399; font-size: 12px; }
.total { margin-top: 12px; text-align: right; }
</style>
