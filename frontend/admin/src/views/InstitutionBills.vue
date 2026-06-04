<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { listBills, type BillItem } from '../api/institution'

const rows = ref<BillItem[]>([])
const total = computed(() => rows.value.reduce((s, b) => s + b.amount_fen, 0))

async function load() { rows.value = await listBills() }

function exportCsv() {
  const header = '日期,类型,明细,金额(元)'
  const lines = rows.value.map((b) =>
    `${b.date.slice(0, 10)},${b.type},"${b.summary}",${(b.amount_fen / 100).toFixed(2)}`)
  const csv = '﻿' + [header, ...lines].join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `机构账单_${new Date().toISOString().slice(0, 10).replace(/-/g, '')}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(load)
</script>

<template>
  <div>
    <h2 class="title">账单</h2>
    <div class="bar">
      <span>合计：¥ {{ (total / 100).toFixed(2) }}</span>
      <el-button type="primary" :disabled="!rows.length" @click="exportCsv">导出 CSV</el-button>
    </div>
    <el-table :data="rows" border>
      <el-table-column label="日期">
        <template #default="{ row }">{{ row.date.slice(0, 10) }}</template>
      </el-table-column>
      <el-table-column prop="type" label="类型" width="100" />
      <el-table-column prop="summary" label="明细" />
      <el-table-column label="金额(元)" width="140">
        <template #default="{ row }">{{ (row.amount_fen / 100).toFixed(2) }}</template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.title { margin: 0 0 16px; font-size: 18px; }
.bar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
</style>
