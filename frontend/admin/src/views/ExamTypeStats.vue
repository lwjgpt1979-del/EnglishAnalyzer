<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getKpExamStats, type ExamStatRow } from '../api/admin'

const GRPS = [{ label: '全部', value: '' }, { label: '词法', value: '词法' }, { label: '句法', value: '句法' },
  { label: '阅读', value: '阅读' }, { label: '听力', value: '听力' }, { label: '作文', value: '作文' }]
const grp = ref('')
const rows = ref<ExamStatRow[]>([])
const totals = ref({ 普通: 0, 中考: 0, 高考: 0, 合计: 0 })
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const d = await getKpExamStats(grp.value || undefined)
    rows.value = d.items
    totals.value = d.totals
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}
onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3 style="margin:0">考试类型统计</h3>
      <span style="margin-left:8px">分类</span>
      <el-select v-model="grp" style="width:110px;margin-left:6px" @change="load">
        <el-option v-for="g in GRPS" :key="g.value" :label="g.label" :value="g.value" />
      </el-select>
      <span class="hint">按考点统计已挂「真题」的考试类型分布;点列头可排序。</span>
    </div>

    <div class="summary">
      <el-tag size="large" effect="plain">普通 <b>{{ totals.普通 }}</b></el-tag>
      <el-tag size="large" type="warning" effect="plain">中考 <b>{{ totals.中考 }}</b></el-tag>
      <el-tag size="large" type="danger" effect="plain">高考 <b>{{ totals.高考 }}</b></el-tag>
      <el-tag size="large" type="info" effect="plain">合计 <b>{{ totals.合计 }}</b></el-tag>
      <span class="muted">共 {{ rows.length }} 个考点挂有真题</span>
    </div>

    <el-table :data="rows" border stripe :default-sort="{ prop: '合计', order: 'descending' }" style="width:100%">
      <el-table-column type="index" label="#" width="56" />
      <el-table-column prop="name" label="考点" min-width="240" show-overflow-tooltip sortable />
      <el-table-column prop="code" label="编码" width="130" show-overflow-tooltip />
      <el-table-column prop="普通" label="普通" width="110" align="center" sortable />
      <el-table-column prop="中考" label="中考" width="110" align="center" sortable>
        <template #default="{ row }"><span :class="{ hot: row.中考 }">{{ row.中考 }}</span></template>
      </el-table-column>
      <el-table-column prop="高考" label="高考" width="110" align="center" sortable>
        <template #default="{ row }"><span :class="{ hot: row.高考 }">{{ row.高考 }}</span></template>
      </el-table-column>
      <el-table-column prop="合计" label="合计" width="110" align="center" sortable />
    </el-table>
  </div>
</template>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 6px; margin-bottom: 14px; flex-wrap: wrap; }
.hint { margin-left: 14px; color: #909399; font-size: 12px; }
.summary { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
.summary b { font-size: 15px; margin-left: 4px; }
.muted { color: #909399; font-size: 12px; }
.hot { color: #e6a23c; font-weight: 700; }
</style>
