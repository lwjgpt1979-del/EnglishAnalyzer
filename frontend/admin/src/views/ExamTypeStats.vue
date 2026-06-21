<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getKpExamStats, type ExamStatRow, type ExamStatOptions } from '../api/admin'

const GRPS = ['', '词法', '句法', '阅读', '听力', '作文']
const STAGE_LABEL: Record<string, string> = { 小: '小学', 初: '初中', 高: '高中' }
const EXAM_TYPES = ['', '普通', '中考', '高考']
const f = reactive({ grp: '', textbook: '', stage: '', grade: '', region_code: '', exam_type: '' })
const opts = ref<ExamStatOptions>({ textbooks: [], stages: [], grades: [], regions: [] })
const rows = ref<ExamStatRow[]>([])
const totals = ref({ 普通: 0, 中考: 0, 高考: 0, 合计: 0 })
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const d = await getKpExamStats({ ...f })
    rows.value = d.items
    totals.value = d.totals
    opts.value = d.options
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}
function resetF() { f.grp = ''; f.textbook = ''; f.stage = ''; f.grade = ''; f.region_code = ''; f.exam_type = ''; load() }
onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3 style="margin:0">考试类型统计</h3>
      <span class="hint">按考点统计已挂「真题」的考试类型分布;可按 教材/学段/年级/地区/考试类型 筛,点列头排序。</span>
    </div>
    <div class="filters">
      <el-select v-model="f.grp" placeholder="知识分类" clearable style="width:120px" @change="load">
        <el-option v-for="g in GRPS" :key="g" :label="g || '全部分类'" :value="g" />
      </el-select>
      <el-select v-model="f.textbook" placeholder="教材版" clearable style="width:120px" @change="load">
        <el-option v-for="t in opts.textbooks" :key="t" :label="t" :value="t" />
      </el-select>
      <el-select v-model="f.stage" placeholder="学段" clearable style="width:100px" @change="load">
        <el-option v-for="s in opts.stages" :key="s" :label="STAGE_LABEL[s] || s" :value="s" />
      </el-select>
      <el-select v-model="f.grade" placeholder="年级" clearable style="width:110px" @change="load">
        <el-option v-for="g in opts.grades" :key="g" :label="g" :value="g" />
      </el-select>
      <el-select v-model="f.region_code" placeholder="地区" clearable filterable style="width:160px" @change="load">
        <el-option v-for="r in opts.regions" :key="r.code" :label="r.name" :value="r.code" />
      </el-select>
      <el-select v-model="f.exam_type" placeholder="考试类型" clearable style="width:110px" @change="load">
        <el-option v-for="e in EXAM_TYPES.filter(x => x)" :key="e" :label="e" :value="e" />
      </el-select>
      <el-button @click="resetF">重置</el-button>
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
.toolbar { display: flex; align-items: center; gap: 6px; margin-bottom: 12px; flex-wrap: wrap; }
.filters { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; flex-wrap: wrap; }
.hint { margin-left: 14px; color: #909399; font-size: 12px; }
.summary { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
.summary b { font-size: 15px; margin-left: 4px; }
.muted { color: #909399; font-size: 12px; }
.hot { color: #e6a23c; font-weight: 700; }
</style>
