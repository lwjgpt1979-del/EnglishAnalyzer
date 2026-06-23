<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Headset } from '@element-plus/icons-vue'
import {
  listTickets, getTicketThread, replyTicket, closeTicket,
  type SupportTicketItem, type SupportMessageItem,
} from '../api/admin'

const rows = ref<SupportTicketItem[]>([])
const total = ref(0)
const loading = ref(false)
const status = ref('pending')
const category = ref('all')

const CAT: Record<string, string> = { refund: '退款咨询', feature: '功能问题', complaint: '投诉', order: '订单问题', other: '其他' }
const ST: Record<string, string> = { open: '待回复', replied: '已回复', closed: '已结案' }
function fmt(s: string | null) { return s ? s.replace('T', ' ').slice(0, 16) : '-' }

async function load() {
  loading.value = true
  try {
    const r = await listTickets({ status: status.value, category: category.value, limit: 100 })
    rows.value = r.items; total.value = r.total
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}

// 工单详情抽屉
const drawer = ref(false)
const current = ref<SupportTicketItem | null>(null)
const messages = ref<SupportMessageItem[]>([])
const replyText = ref('')
const sending = ref(false)

async function openTicket(r: SupportTicketItem) {
  current.value = r; drawer.value = true; messages.value = []; replyText.value = ''
  try {
    const t = await getTicketThread(r.id)
    current.value = t.ticket; messages.value = t.messages
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
}
async function doReply() {
  if (!current.value || !replyText.value.trim()) return
  sending.value = true
  try {
    await replyTicket(current.value.id, replyText.value.trim())
    replyText.value = ''
    await openTicket(current.value)
    await load()
  } catch (e: any) { ElMessage.error(e?.message || '回复失败') }
  finally { sending.value = false }
}
async function doClose(r: SupportTicketItem) {
  try {
    await ElMessageBox.confirm('确认结案该工单？', '结案')
    await closeTicket(r.id)
    ElMessage.success('已结案'); drawer.value = false; await load()
  } catch (e: any) { if (e !== 'cancel') ElMessage.error(e?.message || '操作失败') }
}

onMounted(load)
</script>

<template>
  <div class="sup">
    <div class="toolbar">
      <h2><el-icon style="vertical-align:-2px;margin-right:4px"><Headset /></el-icon>客服工单</h2>
      <div class="filters">
        <el-radio-group v-model="status" @change="load">
          <el-radio-button label="pending">待处理</el-radio-button>
          <el-radio-button label="open">待回复</el-radio-button>
          <el-radio-button label="replied">已回复</el-radio-button>
          <el-radio-button label="closed">已结案</el-radio-button>
          <el-radio-button label="all">全部</el-radio-button>
        </el-radio-group>
        <el-select v-model="category" style="width: 130px" @change="load">
          <el-option label="全部类型" value="all" />
          <el-option v-for="(v, k) in CAT" :key="k" :label="v" :value="k" />
        </el-select>
        <el-button @click="load">刷新</el-button>
      </div>
    </div>
    <p class="hint">用户在线咨询工单（§13.1）。「待处理」= 未结案且用户最后发言。</p>

    <el-table :data="rows" v-loading="loading" stripe @row-click="openTicket">
      <el-table-column label="类型" width="100">
        <template #default="{ row }"><el-tag size="small">{{ CAT[row.category] || row.category }}</el-tag></template>
      </el-table-column>
      <el-table-column prop="subject" label="标题" min-width="220" show-overflow-tooltip />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === 'closed' ? 'info' : (row.status === 'replied' ? 'success' : 'warning')" size="small">{{ ST[row.status] || row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="最后" width="80">
        <template #default="{ row }">{{ row.last_reply_role === 'admin' ? '客服' : '用户' }}</template>
      </el-table-column>
      <el-table-column label="更新时间" width="150"><template #default="{ row }">{{ fmt(row.updated_at) }}</template></el-table-column>
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click.stop="openTicket(row)">查看/回复</el-button>
          <el-button v-if="row.status !== 'closed'" size="small" link @click.stop="doClose(row)">结案</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div class="muted total">共 {{ total }} 条</div>

    <el-drawer v-model="drawer" :title="current?.subject || '工单'" size="540px">
      <div v-if="current" class="thread">
        <div class="meta">
          <el-tag size="small">{{ CAT[current.category] || current.category }}</el-tag>
          <el-tag :type="current.status === 'closed' ? 'info' : 'warning'" size="small">{{ ST[current.status] }}</el-tag>
        </div>
        <div class="msgs">
          <div v-for="m in messages" :key="m.id" class="msg" :class="m.sender_role">
            <div class="who">{{ m.sender_role === 'admin' ? '客服' : '用户' }} · {{ fmt(m.created_at) }}</div>
            <div class="bubble">{{ m.content }}</div>
          </div>
        </div>
        <div v-if="current.status !== 'closed'" class="composer">
          <el-input v-model="replyText" type="textarea" :rows="3" placeholder="输入回复内容…" maxlength="1000" show-word-limit />
          <div class="actions">
            <el-button @click="doClose(current)">结案</el-button>
            <el-button type="primary" :loading="sending" :disabled="!replyText.trim()" @click="doReply">发送回复</el-button>
          </div>
        </div>
        <el-alert v-else title="该工单已结案" type="info" :closable="false" />
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.sup { padding: 16px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 12px; }
.filters { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.hint { color: #909399; font-size: 13px; margin: 0 0 16px; }
.muted { color: #909399; font-size: 12px; }
.total { margin-top: 12px; text-align: right; }
.thread { display: flex; flex-direction: column; gap: 12px; height: 100%; }
.meta { display: flex; gap: 8px; }
.msgs { flex: 1; overflow: auto; display: flex; flex-direction: column; gap: 10px; }
.msg .who { font-size: 12px; color: #909399; margin-bottom: 2px; }
.msg .bubble { background: #f4f4f5; padding: 8px 12px; border-radius: 8px; white-space: pre-wrap; display: inline-block; max-width: 90%; }
.msg.admin { text-align: right; }
.msg.admin .bubble { background: #ecf5ff; }
.composer { border-top: 1px solid #eee; padding-top: 12px; }
.composer .actions { margin-top: 8px; text-align: right; }
</style>
