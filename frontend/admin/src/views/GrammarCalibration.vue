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
function pct(v: number | null | undefined) { return v == null ? '—' : (v * 100).toFixed(1) + '%' }
onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3 style="margin:0">语法掌握判定校准(R10 验证闭环)</h3>
      <span class="hint">用真实作答反查 R10「已掌握」判得准不准:对题真值(刷题)给正确率分母,纸质错题作补充。</span>
    </div>

    <div class="filters">
      <el-input v-model="studentId" placeholder="按学生 ID 过滤(留空=全部学生)" clearable style="width:340px" @keyup.enter="load" />
      <el-button type="primary" @click="load">查询</el-button>
      <el-button @click="reset">全部学生</el-button>
    </div>

    <el-alert v-if="data" :closable="false" type="info" show-icon style="margin-bottom:14px">
      <template #title>
        <b>post_mastery</b> = R10 判会(达成四维)后的真实作答正确率(分母=对题);<b>1 − 正确率 = 虚高率(false_mastery_rate)</b>,越高说明判得越虚。
        纸质错题只有错、无分母,单列为「判会后又错」实锤。
      </template>
    </el-alert>

    <div v-if="data" class="summary">
      <el-tag size="large" effect="plain">判会点 <b>{{ data.mastered_points }}</b></el-tag>
      <el-tag size="large" type="success" effect="plain">已坐实(复测) <b>{{ data.confirmed_points }}</b></el-tag>
      <el-tag size="large" effect="plain">判会后作答 <b>{{ data.post_mastery.answers }}</b></el-tag>
      <el-tag size="large" :type="(data.post_mastery.accuracy ?? 1) < 0.85 ? 'danger' : 'success'" effect="plain">
        判会后正确率 <b>{{ pct(data.post_mastery.accuracy) }}</b>
      </el-tag>
      <el-tag size="large" :type="(data.post_mastery.false_mastery_rate ?? 0) > 0 ? 'danger' : 'success'" effect="dark">
        虚高率 <b>{{ pct(data.post_mastery.false_mastery_rate) }}</b>
      </el-tag>
      <el-tag size="large" :type="data.paper_wrong_after_mastery.hits ? 'warning' : 'info'" effect="plain">
        纸质判会后又错 <b>{{ data.paper_wrong_after_mastery.hits }}</b>
      </el-tag>
    </div>

    <h4 style="margin:6px 0 10px">虚高榜(判会点里事后表现最差的:对题正确率低 / 纸质又错)</h4>
    <el-table :data="data?.worst_nodes || []" border stripe style="width:100%">
      <el-table-column type="index" label="#" width="56" />
      <el-table-column prop="name" label="语法点" min-width="240" show-overflow-tooltip />
      <el-table-column prop="answers" label="判会后作答" width="110" align="center" sortable />
      <el-table-column prop="accuracy" label="正确率" width="110" align="center" sortable>
        <template #default="{ row }"><span :class="{ hot: (row.accuracy ?? 1) < 0.85 }">{{ pct(row.accuracy) }}</span></template>
      </el-table-column>
      <el-table-column prop="false_mastery_rate" label="虚高率" width="110" align="center" sortable>
        <template #default="{ row }"><span :class="{ hot: (row.false_mastery_rate ?? 0) > 0 }">{{ pct(row.false_mastery_rate) }}</span></template>
      </el-table-column>
      <el-table-column prop="paper_hits" label="纸质又错" width="100" align="center" sortable />
      <el-table-column prop="confirmed" label="是否已坐实" width="130" align="center">
        <template #default="{ row }">
          <el-tag :type="row.confirmed ? 'danger' : 'warning'" effect="plain" size="small">
            {{ row.confirmed ? '已坐实却翻车' : '仅四维达成' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="days_since_mastered" label="判会距今(天)" width="140" align="center" sortable />
      <el-table-column prop="node_id" label="节点 ID" width="150" show-overflow-tooltip />
      <template #empty>暂无可校准数据(判会点尚无事后真实作答/错题,或该范围内无数据)</template>
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
