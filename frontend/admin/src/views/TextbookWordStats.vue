<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getTextbookWordStats, type WordStatRow } from '../api/admin'

const f = reactive({ textbook: '', grade: '' })
const opts = ref<{ textbooks: string[]; grades: string[] }>({ textbooks: [], grades: [] })
const totals = ref({ words: 0, high_freq: 0, max_units: 0 })
const rows = ref<WordStatRow[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const d = await getTextbookWordStats(f.textbook || undefined, f.grade || undefined)
    rows.value = d.items
    totals.value = d.totals
    opts.value = d.options
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}
function resetF() { f.textbook = ''; f.grade = ''; load() }
onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3 style="margin:0">教材高频词统计</h3>
      <span class="hint">按 教材版本/年级 统计:一个词出现在多少个单元(出现单元数 = 教材内词频),越多越高频。</span>
    </div>
    <div class="filters">
      <el-select v-model="f.textbook" placeholder="教材版本" clearable style="width:160px" @change="load">
        <el-option v-for="t in opts.textbooks" :key="t" :label="t" :value="t" />
      </el-select>
      <el-select v-model="f.grade" placeholder="年级/学段" clearable style="width:140px" @change="load">
        <el-option v-for="g in opts.grades" :key="g" :label="g" :value="g" />
      </el-select>
      <el-button @click="resetF">重置</el-button>
    </div>

    <div class="summary">
      <el-tag size="large" effect="plain">总词数 <b>{{ totals.words }}</b></el-tag>
      <el-tag size="large" type="warning" effect="plain">高频词(≥2单元) <b>{{ totals.high_freq }}</b></el-tag>
      <el-tag size="large" type="info" effect="plain">最高出现 <b>{{ totals.max_units }}</b> 单元</el-tag>
      <span class="muted">选教材版/年级看该教材的高频词;不选=全部教材</span>
    </div>

    <el-table :data="rows" border stripe :default-sort="{ prop: 'unit_count', order: 'descending' }" style="width:100%">
      <el-table-column type="index" label="#" width="56" />
      <el-table-column prop="word" label="单词" min-width="160" sortable>
        <template #default="{ row }"><b>{{ row.word }}</b></template>
      </el-table-column>
      <el-table-column prop="gloss" label="释义" min-width="200" show-overflow-tooltip />
      <el-table-column prop="unit_count" label="出现单元数" width="140" align="center" sortable>
        <template #default="{ row }"><span :class="{ hot: row.unit_count >= 2 }">{{ row.unit_count }}</span></template>
      </el-table-column>
      <el-table-column prop="star" label="考频星级" width="120" align="center" sortable>
        <template #default="{ row }">{{ row.star ? '★'.repeat(row.star) : '—' }}</template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 6px; margin-bottom: 12px; flex-wrap: wrap; }
.hint { margin-left: 14px; color: #909399; font-size: 12px; }
.filters { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; flex-wrap: wrap; }
.summary { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }
.summary b { font-size: 15px; margin-left: 4px; }
.muted { color: #909399; font-size: 12px; }
.hot { color: #e6a23c; font-weight: 700; }
</style>
