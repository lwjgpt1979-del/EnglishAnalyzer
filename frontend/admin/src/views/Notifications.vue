<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listNotifications, markRead, type AdminNotification } from '../api/notifications'

const rows = ref<AdminNotification[]>([])
const unread = ref(0)
const total = ref(0)
const page = ref(1)
const pageSize = 50

async function load() {
  const r = await listNotifications({ skip: (page.value - 1) * pageSize, limit: pageSize })
  rows.value = r.items
  unread.value = r.unread_count
  total.value = r.total
}

async function read(n: AdminNotification) {
  if (n.is_read) return
  await markRead(n.id)
  ElMessage.success('已读')
  await load()
}

onMounted(load)
</script>

<template>
  <div>
    <h2 class="title">通知 <span v-if="unread" class="badge">{{ unread }}</span></h2>
    <el-table :data="rows" border>
      <el-table-column prop="title" label="标题" width="180" />
      <el-table-column prop="content" label="内容" />
      <el-table-column label="时间" width="120">
        <template #default="{ row }">{{ row.created_at.slice(0, 10) }}</template>
      </el-table-column>
      <el-table-column label="状态" width="120">
        <template #default="{ row }">
          <el-tag v-if="row.is_read" type="info">已读</el-tag>
          <el-button v-else text type="primary" @click="read(row)">标为已读</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div style="display:flex;justify-content:flex-end;margin-top:12px">
      <el-pagination layout="total, prev, pager, next, jumper" :total="total"
        :page-size="pageSize" v-model:current-page="page" @current-change="load" />
    </div>
  </div>
</template>

<style scoped>
.title { margin: 0 0 16px; font-size: 18px; }
.badge { background: #f56c6c; color: #fff; border-radius: 10px; padding: 0 8px; font-size: 12px; }
</style>
