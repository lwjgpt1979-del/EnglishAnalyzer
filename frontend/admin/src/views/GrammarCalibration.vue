<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getGrammarCalibration, type GrammarCalibration } from '../api/admin'

const studentId = ref('')
const data = ref<GrammarCalibration | null>(null)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    data.value = await getGrammarCalibration(studentId.value.trim() || undefined)
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}
function reset() { studentId.value = ''; load() }
function pct(v: number | null) { return v == null ? '—' : (v * 100).toFixed(1) + '%' }
function fmt(ts: string | null) { return ts ? new Date(ts).toLocaleString() : '—' }
onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3 style="margin:0">语法掌握判定校准(R10 验证闭环)</h3>
      <span class="hint">用真实错题(R3 错题闭环)反查 R10「已掌握」判得准不准。</span>
    </div>

    <div class="filters">
      <el-input v-model="studentId" placeholder="按学生 ID 过滤(留空=全部学生)" clearable style="width:340px" @keyup.enter="load" />
      <el-button type="primary" @click="load">查询</el-button>
      <el-button @click="reset">全部学生</el-button>
    </div>

    <el-alert v-if="data" :closable="false" type="info" show-icon style="margin-bottom:14px">
      <template #title>
        只有错题真值,所以这里是「翻车计数」而非正确率:<b>hits = R10 判会(达成四维)后,该点又在真题里错了的次数</b> = 实锤虚高。对题正确率分母待后续刷题真值流补全。
      </template>
    </el-alert>

    <div v-if="data" class="summary">
      <el-tag size="large" effect="plain">判会点 <b>{{ data.mastered_points }}</b></el-tag>
      <el-tag size="large" type="success" effect="plain">已坐实(复测) <b>{{ data.confirmed_points }}</b></el-tag>
      <el-tag size="large" :type="data.false_mastery_hits ? 'danger' : 'info'" effect="plain">判会后又错 <b>{{ data.false_mastery_hits }}</b></el-tag>
      <el-tag size="large" :type="data.affected_points ? 'warning' : 'info'" effect="plain">翻车点 <b>{{ data.affected_points }}</b></el-tag>
      <el-tag size="large" :type="(data.false_mastery_point_rate || 0) > 0 ? 'danger' : 'success'" effect="dark">
        点翻车率 <b>{{ pct(data.false_mastery_point_rate) }}</b>
      </el-tag>
    </div>

    <h4 style="margin:6px 0 10px">虚高实锤榜(判会却又错的语法点,按翻车次数降序)</h4>
    <el-table :data="data?.worst_nodes || []" border stripe style="width:100%">
      <el-table-column type="index" label="#" width="56" />
      <el-table-column prop="name" label="语法点" min-width="240" show-overflow-tooltip />
      <el-table-column prop="hits" label="判会后又错" width="130" align="center" sortable>
        <template #default="{ row }"><span class="hot">{{ row.hits }}</span></template>
      </el-table-column>
      <el-table-column prop="confirmed" label="是否已坐实" width="130" align="center">
        <template #default="{ row }">
          <el-tag :type="row.confirmed ? 'danger' : 'warning'" effect="plain" size="small">
            {{ row.confirmed ? '已坐实却翻车' : '仅四维达成' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="days_since_mastered" label="判会距今(天)" width="140" align="center" sortable />
      <el-table-column label="最近翻车时间" min-width="180">
        <template #default="{ row }">{{ fmt(row.last_wrong_at) }}</template>
      </el-table-column>
      <el-table-column prop="node_id" label="节点 ID" width="150" show-overflow-tooltip />
      <template #empty>暂无「判会后又错」记录(无虚高,或该范围内尚无真实错题数据)</template>
    </el-table>
  </div>
</template>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 6px; margin-bottom: 12px; flex-wrap: wrap; }
.filters { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; flex-wrap: wrap; }
.hint { margin-left: 14px; color: #909399; font-size: 12px; }
.summary { display: flex; align-items: center; gap: 12px; margin-bottom: 18px; flex-wrap: wrap; }
.summary b { font-size: 15px; margin-left: 4px; }
.hot { color: #f56c6c; font-weight: 700; }
</style>
