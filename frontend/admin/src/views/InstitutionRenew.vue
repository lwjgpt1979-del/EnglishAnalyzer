<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listRenewableStudents, batchRenew, type RenewableStudent } from '../api/institution'

const rows = ref<RenewableStudent[]>([])
const selected = ref<RenewableStudent[]>([])
const onlyExpiring = ref(true)
const months = ref(6)

async function load() {
  rows.value = await listRenewableStudents(onlyExpiring.value ? 30 : undefined)
}

async function renew() {
  if (!selected.value.length) return
  const ids = selected.value.map((r) => r.student_id)
  const res = await batchRenew(ids, months.value)
  ElMessage.success(`续费 ${res.renewed_count} 人，跳过 ${res.skipped.length} 人，合计 ¥${(res.total_amount_fen / 100).toFixed(2)}`)
  await load()
}

onMounted(load)
</script>

<template>
  <div>
    <h2 class="title">批量续费</h2>
    <el-card style="margin-bottom: 16px">
      <el-checkbox v-model="onlyExpiring" @change="load">仅看近 30 天到期</el-checkbox>
      <span style="margin-left: 24px">续费月数：</span>
      <el-input-number v-model="months" :min="1" />
      <el-button type="primary" style="margin-left: 16px" :disabled="!selected.length" @click="renew">
        批量续费（dev-mock 即付）
      </el-button>
    </el-card>
    <el-table :data="rows" border @selection-change="(v: RenewableStudent[]) => (selected = v)">
      <el-table-column type="selection" width="50" />
      <el-table-column prop="nickname" label="昵称" />
      <el-table-column prop="tier" label="档位" />
      <el-table-column label="到期日">
        <template #default="{ row }">{{ row.expires_at.slice(0, 10) }}</template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.title { margin: 0 0 16px; font-size: 18px; }
</style>
