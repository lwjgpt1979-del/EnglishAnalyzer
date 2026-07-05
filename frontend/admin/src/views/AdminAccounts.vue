<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listAdminAccounts, createAdminAccount, updateAdminAccount, resetAdminPassword,
  adminMe, type AdminAccountRow,
} from '../api/admin'

// 模块清单(与后端 app/core/module_map.MODULES + 菜单分组对应)
const MODULES: { key: string; label: string }[] = [
  { key: 'content', label: '内容生产' },
  { key: 'vocab', label: '词汇/词力通' },
  { key: 'speak', label: '口语/听力/主题' },
  { key: 'teacher_inst', label: '教师/机构' },
  { key: 'ops', label: '用户/运营' },
  { key: 'sales', label: '销售/电销CRM' },
  { key: 'finance', label: '营收/财务' },
  { key: 'support', label: '支持/反馈' },
  { key: 'system', label: '系统配置' },
]
const modLabel = (k: string) => MODULES.find(m => m.key === k)?.label || k

const rows = ref<AdminAccountRow[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const myId = ref('')

async function load() {
  loading.value = true
  try {
    const r = await listAdminAccounts({ skip: (page.value - 1) * pageSize.value, limit: pageSize.value })
    rows.value = r.items; total.value = r.total
  } catch (e: any) { ElMessage.error(e?.message || '加载失败(仅超级管理员可访问)') }
  finally { loading.value = false }
}

// ── 新建 ──
const dlgNew = ref(false)
const fNew = ref({ username: '', password: '', nickname: '', allMods: false, modules: [] as string[] })
function openNew() {
  fNew.value = { username: '', password: '', nickname: '', allMods: false, modules: [] }
  dlgNew.value = true
}
async function saveNew() {
  if (!fNew.value.username.trim()) { ElMessage.warning('请填用户名'); return }
  if (fNew.value.password.length < 8) { ElMessage.warning('密码至少 8 位'); return }
  if (!fNew.value.allMods && !fNew.value.modules.length) { ElMessage.warning('请勾选模块,或选「全权」'); return }
  try {
    await createAdminAccount({
      username: fNew.value.username.trim(), password: fNew.value.password,
      nickname: fNew.value.nickname.trim() || undefined,
      modules: fNew.value.allMods ? null : fNew.value.modules,
    })
    ElMessage.success('已创建'); dlgNew.value = false; load()
  } catch (e: any) { ElMessage.error(e?.message || '创建失败') }
}

// ── 改权限 ──
const dlgEdit = ref(false)
const editRow = ref<AdminAccountRow | null>(null)
const fEdit = ref({ nickname: '', allMods: false, modules: [] as string[] })
function openEdit(row: AdminAccountRow) {
  editRow.value = row
  fEdit.value = { nickname: row.nickname || '', allMods: row.modules === null, modules: [...(row.modules || [])] }
  dlgEdit.value = true
}
async function saveEdit() {
  if (!editRow.value) return
  if (!fEdit.value.allMods && !fEdit.value.modules.length) { ElMessage.warning('请勾选模块,或选「全权」'); return }
  try {
    await updateAdminAccount(editRow.value.id, {
      nickname: fEdit.value.nickname.trim() || undefined,
      all_modules: fEdit.value.allMods,
      modules: fEdit.value.allMods ? undefined : fEdit.value.modules,
    })
    ElMessage.success('已保存'); dlgEdit.value = false; load()
  } catch (e: any) { ElMessage.error(e?.message || '保存失败') }
}

async function toggleActive(row: AdminAccountRow) {
  const verb = row.is_active ? '停用' : '启用'
  try { await ElMessageBox.confirm(`${verb}账号「${row.username}」?停用后立即无法登录/调用接口。`, verb, { type: 'warning' }) } catch { return }
  try { await updateAdminAccount(row.id, { is_active: !row.is_active }); ElMessage.success(`已${verb}`); load() }
  catch (e: any) { ElMessage.error(e?.message || `${verb}失败`) }
}

async function resetPwd(row: AdminAccountRow) {
  let pwd = ''
  try {
    const r = await ElMessageBox.prompt(`给「${row.username}」设置新密码(至少 8 位):`, '重置密码',
      { inputType: 'password', inputPattern: /^.{8,}$/, inputErrorMessage: '至少 8 位' })
    pwd = r.value
  } catch { return }
  try { await resetAdminPassword(row.id, pwd); ElMessage.success('已重置') }
  catch (e: any) { ElMessage.error(e?.message || '重置失败') }
}

onMounted(async () => {
  try { myId.value = (await adminMe()).id } catch { /* ignore */ }
  await load()
})
</script>

<template>
  <div>
    <div class="toolbar">
      <h3 style="margin:0">账号与权限</h3>
      <span class="hint">子管理员按模块授权(如只给电销),越权访问接口直接 403;「全权」=超级管理员。停用立即生效。仅超管可进本页。</span>
      <el-button type="primary" @click="openNew">新建管理员</el-button>
    </div>

    <el-table :data="rows" border stripe style="width:100%" v-loading="loading">
      <el-table-column prop="username" label="用户名" width="160">
        <template #default="{ row }">
          {{ row.username }}
          <el-tag v-if="row.id === myId" size="small" effect="plain" style="margin-left:4px">我</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="nickname" label="昵称" width="130">
        <template #default="{ row }"><span :class="{ muted: !row.nickname }">{{ row.nickname || '—' }}</span></template>
      </el-table-column>
      <el-table-column label="权限" min-width="320">
        <template #default="{ row }">
          <el-tag v-if="row.modules === null" type="danger" effect="dark" size="small">全权(超管)</el-tag>
          <template v-else>
            <el-tag v-for="m in row.modules" :key="m" size="small" effect="plain" style="margin-right:6px">{{ modLabel(m) }}</el-tag>
          </template>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '正常' : '已停用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="170">
        <template #default="{ row }">{{ row.created_at ? row.created_at.replace('T', ' ').slice(0, 19) : '—' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="240" align="center">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">改权限</el-button>
          <el-button size="small" @click="resetPwd(row)">重置密码</el-button>
          <el-button size="small" :type="row.is_active ? 'danger' : 'success'" plain
            :disabled="row.id === myId" @click="toggleActive(row)">{{ row.is_active ? '停用' : '启用' }}</el-button>
        </template>
      </el-table-column>
      <template #empty>暂无管理员账号</template>
    </el-table>

    <el-pagination
      style="margin-top:14px; justify-content:flex-end"
      layout="total, prev, pager, next, jumper"
      :total="total" :current-page="page" :page-size="pageSize"
      @current-change="(p: number) => { page = p; load() }" />

    <!-- 新建 -->
    <el-dialog v-model="dlgNew" title="新建管理员" width="520px">
      <el-form label-width="90px">
        <el-form-item label="用户名"><el-input v-model="fNew.username" placeholder="登录账号,如 sales_wang" /></el-form-item>
        <el-form-item label="密码"><el-input v-model="fNew.password" type="password" show-password placeholder="至少 8 位" /></el-form-item>
        <el-form-item label="昵称"><el-input v-model="fNew.nickname" placeholder="显示名,如 电销小王(可选)" /></el-form-item>
        <el-form-item label="权限">
          <el-switch v-model="fNew.allMods" active-text="全权(超管)" style="margin-bottom:6px" />
          <el-checkbox-group v-if="!fNew.allMods" v-model="fNew.modules">
            <el-checkbox v-for="m in MODULES" :key="m.key" :value="m.key">{{ m.label }}</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dlgNew = false">取消</el-button>
        <el-button type="primary" @click="saveNew">创建</el-button>
      </template>
    </el-dialog>

    <!-- 改权限 -->
    <el-dialog v-model="dlgEdit" :title="`改权限:${editRow?.username || ''}`" width="520px">
      <el-form label-width="90px">
        <el-form-item label="昵称"><el-input v-model="fEdit.nickname" /></el-form-item>
        <el-form-item label="权限">
          <el-switch v-model="fEdit.allMods" active-text="全权(超管)" style="margin-bottom:6px" />
          <el-checkbox-group v-if="!fEdit.allMods" v-model="fEdit.modules">
            <el-checkbox v-for="m in MODULES" :key="m.key" :value="m.key">{{ m.label }}</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dlgEdit = false">取消</el-button>
        <el-button type="primary" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; flex-wrap: wrap; }
.hint { color: #909399; font-size: 12px; flex: 1; }
.muted { color: #a0a4ab; }
</style>
