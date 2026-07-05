<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listAuditLogs, getAuditAdmins, type AuditLogRow } from '../api/admin'

const MODULE_LABEL: Record<string, string> = {
  sales: '电销CRM', finance: '财务', ops: '运营', teacher_inst: '教师/机构',
  system: '系统', support: '支持', vocab: '词汇', speak: '口语听力', content: '内容',
}
const METHOD_TYPE: Record<string, string> = { POST: 'primary', PUT: 'warning', PATCH: 'warning', DELETE: 'danger' }

const rows = ref<AuditLogRow[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const admins = ref<{ admin_id: string; name: string }[]>([])

// 筛选
const fModule = ref('')
const fMethod = ref('')
const fAdmin = ref('')
const fQ = ref('')
const fFailOnly = ref(false)
const fRange = ref<[Date, Date] | null>(null)

async function load() {
  loading.value = true
  try {
    const r = await listAuditLogs({
      module: fModule.value || undefined,
      method: fMethod.value || undefined,
      admin_id: fAdmin.value || undefined,
      q: fQ.value.trim() || undefined,
      status_min: fFailOnly.value ? 400 : undefined,
      date_from: fRange.value ? fRange.value[0].toISOString() : undefined,
      date_to: fRange.value ? fRange.value[1].toISOString() : undefined,
      skip: (page.value - 1) * pageSize.value, limit: pageSize.value,
    })
    rows.value = r.items; total.value = r.total
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}
function reload() { page.value = 1; load() }

function fmtTime(iso: string) { return iso.replace('T', ' ').slice(0, 19) }
function shortPath(p: string) { return p.replace('/api/v1/admin', '') }

onMounted(async () => {
  try { admins.value = await getAuditAdmins() } catch { /* ignore */ }
  await load()
})
</script>

<template>
  <div>
    <div class="toolbar">
      <h3 style="margin:0">操作审计</h3>
      <span class="hint">后台所有写操作(增/改/删)自动留痕:谁、何时、对哪个接口、提交了什么(敏感字段已脱敏)。含未授权尝试(操作人为空)。</span>
    </div>

    <div class="bar">
      <el-select v-model="fModule" placeholder="模块" clearable style="width:130px" @change="reload">
        <el-option v-for="(l, k) in MODULE_LABEL" :key="k" :label="l" :value="k" />
      </el-select>
      <el-select v-model="fMethod" placeholder="动作" clearable style="width:110px" @change="reload">
        <el-option label="POST(增)" value="POST" />
        <el-option label="PUT(改)" value="PUT" />
        <el-option label="PATCH(改)" value="PATCH" />
        <el-option label="DELETE(删)" value="DELETE" />
      </el-select>
      <el-select v-model="fAdmin" placeholder="操作人" clearable filterable style="width:150px" @change="reload">
        <el-option v-for="a in admins" :key="a.admin_id" :label="a.name" :value="a.admin_id" />
      </el-select>
      <el-input v-model="fQ" placeholder="路径关键词,如 pricing" clearable style="width:200px" @keyup.enter="reload" @clear="reload" />
      <el-date-picker v-model="fRange" type="datetimerange" range-separator="至"
        start-placeholder="开始" end-placeholder="结束" style="width:340px" @change="reload" />
      <el-checkbox v-model="fFailOnly" @change="reload">只看失败/越权(≥400)</el-checkbox>
      <el-button type="primary" @click="reload">查询</el-button>
    </div>

    <el-table :data="rows" border stripe style="width:100%" v-loading="loading">
      <el-table-column label="时间" width="165">
        <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作人" width="120">
        <template #default="{ row }">
          <span v-if="row.admin_name">{{ row.admin_name }}</span>
          <el-tag v-else type="danger" size="small" effect="dark" title="无有效登录态的写尝试">未授权</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="动作" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="(METHOD_TYPE[row.method] as any) || 'info'" size="small">{{ row.method }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="模块" width="100" align="center">
        <template #default="{ row }"><el-tag size="small" effect="plain">{{ MODULE_LABEL[row.module] || row.module }}</el-tag></template>
      </el-table-column>
      <el-table-column label="接口路径" min-width="240" show-overflow-tooltip>
        <template #default="{ row }">
          <code class="pathc">{{ shortPath(row.path) }}</code>
          <span v-if="row.query" class="muted">?{{ row.query }}</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="80" align="center">
        <template #default="{ row }">
          <span :style="{ color: row.status >= 400 ? '#f56c6c' : '#67c23a', fontWeight: 600 }">{{ row.status }}</span>
        </template>
      </el-table-column>
      <el-table-column label="提交内容(已脱敏)" min-width="260">
        <template #default="{ row }">
          <el-popover v-if="row.detail" trigger="click" width="480" placement="left">
            <template #reference>
              <code class="detailc">{{ JSON.stringify(row.detail).slice(0, 80) }}{{ JSON.stringify(row.detail).length > 80 ? '…' : '' }}</code>
            </template>
            <pre class="detailfull">{{ JSON.stringify(row.detail, null, 2) }}</pre>
          </el-popover>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column prop="ip" label="IP" width="130" show-overflow-tooltip />
      <el-table-column label="耗时" width="80" align="right">
        <template #default="{ row }"><span class="muted">{{ row.duration_ms != null ? row.duration_ms + 'ms' : '—' }}</span></template>
      </el-table-column>
      <template #empty>暂无审计记录</template>
    </el-table>

    <el-pagination
      style="margin-top:14px; justify-content:flex-end"
      layout="total, prev, pager, next, jumper"
      :total="total" :current-page="page" :page-size="pageSize"
      @current-change="(p: number) => { page = p; load() }" />
  </div>
</template>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; flex-wrap: wrap; }
.bar { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; flex-wrap: wrap; }
.hint { color: #909399; font-size: 12px; }
.muted { color: #a0a4ab; font-size: 12px; }
.pathc { background: #f4f4f5; padding: 1px 6px; border-radius: 4px; font-size: 12px; }
.detailc { font-size: 12px; color: #606266; cursor: pointer; }
.detailfull { max-height: 400px; overflow: auto; font-size: 12px; margin: 0; }
</style>
