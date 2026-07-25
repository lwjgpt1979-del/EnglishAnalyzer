<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, MagicStick, Loading } from '@element-plus/icons-vue'
import {
  getReadingQtypeStats, listReadingQtype, backfillReadingQtype,
  classifyReadingQtype, setReadingQtype,
  type ReadingQtypeStats, type ReadingQtypeItem,
} from '../api/admin'

const stats = ref<ReadingQtypeStats>({ total: 0, tagged: 0, untagged: 0, distribution: {} })
const skills = ref<string[]>([])
const rows = ref<ReadingQtypeItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const fSkill = ref<string>('')            // 题型筛选
const fUntagged = ref(false)              // 只看未标
const loading = ref(false)
const backfilling = ref(false)
const classifying = ref(false)
const classifyLimit = ref(100)

async function loadStats() {
  try { stats.value = await getReadingQtypeStats() } catch (e: any) { ElMessage.error(e?.message || '加载概况失败') }
}
async function load() {
  loading.value = true
  try {
    const r = await listReadingQtype({
      skill: fUntagged.value ? undefined : (fSkill.value || undefined),
      only_untagged: fUntagged.value || undefined,
      skip: (page.value - 1) * pageSize.value,
      limit: pageSize.value,
    })
    rows.value = r.items; total.value = r.total; if (r.skills?.length) skills.value = r.skills
  } catch (e: any) { ElMessage.error(e?.message || '加载列表失败') } finally { loading.value = false }
}
function reload() { page.value = 1; load() }

async function onBackfill() {
  backfilling.value = true
  try {
    const r = await backfillReadingQtype()
    ElMessage.success(`回填完成:命中 ${r.filled} 题,仍缺 ${r.still_missing} 题(需补跑)`)
    await loadStats(); await load()
  } catch (e: any) { ElMessage.error(e?.message || '回填失败') } finally { backfilling.value = false }
}
async function onClassify() {
  classifying.value = true
  try {
    const r = await classifyReadingQtype(classifyLimit.value)
    ElMessage.success(`补跑完成:归类 ${r.classified_contents} 种内容 / 标注 ${r.tagged_questions} 题,剩 ${r.remaining} 种`)
    await loadStats(); await load()
  } catch (e: any) { ElMessage.error(e?.message || '补跑失败') } finally { classifying.value = false }
}
async function onSetSkill(row: ReadingQtypeItem, skill: string) {
  try {
    await setReadingQtype(row.id, skill)
    row.skill = skill
    ElMessage.success('已更新题型')
    await loadStats()
  } catch (e: any) { ElMessage.error(e?.message || '更新失败'); await load() }
}

onMounted(async () => { await loadStats(); await load() })
</script>

<template>
  <div class="page">
    <h2>作业阅读题型归类</h2>
    <p class="hint">给作业里的阅读小题打上题型细标(细节/主旨/推理/词义/态度/指代/图表/其他),供「阅读理解学情统计」按题型算正确率。
      精讲时自动写入;下方「回填」从精讲缓存捡漏(不花钱),「补跑」对未覆盖的题调 LLM 归类。</p>

    <!-- 概况 -->
    <el-card shadow="never" class="mb">
      <div class="stat-row">
        <div class="stat"><div class="n">{{ stats.total }}</div><div class="l">阅读题总数</div></div>
        <div class="stat"><div class="n ok">{{ stats.tagged }}</div><div class="l">已标</div></div>
        <div class="stat"><div class="n warn">{{ stats.untagged }}</div><div class="l">未标</div></div>
        <div class="dist">
          <el-tag v-for="(c, k) in stats.distribution" :key="k" class="dtag"
                  :type="k === '未标' ? 'info' : ''" effect="plain">{{ k }} · {{ c }}</el-tag>
        </div>
      </div>
      <div class="actions">
        <el-button :icon="Refresh" :loading="backfilling" @click="onBackfill">回填(捡漏,不花钱)</el-button>
        <el-input-number v-model="classifyLimit" :min="1" :max="1000" :step="50" size="small" style="width:120px" />
        <el-button type="primary" :icon="MagicStick" :loading="classifying" @click="onClassify">补跑归类(调 LLM)</el-button>
      </div>
    </el-card>

    <!-- 筛选 -->
    <div class="filters">
      <el-select v-model="fSkill" placeholder="按题型筛" clearable style="width:160px"
                 :disabled="fUntagged" @change="reload">
        <el-option v-for="s in skills" :key="s" :label="s" :value="s" />
      </el-select>
      <el-checkbox v-model="fUntagged" @change="reload">只看未标</el-checkbox>
      <span class="grow" />
      <el-button :icon="Refresh" @click="reload">刷新</el-button>
    </div>

    <!-- 列表 -->
    <el-table :data="rows" v-loading="loading" border stripe size="small">
      <el-table-column label="题干" min-width="360">
        <template #default="{ row }"><span class="stem">{{ row.stem }}</span></template>
      </el-table-column>
      <el-table-column label="题型" width="150">
        <template #default="{ row }">
          <el-select :model-value="row.skill" placeholder="未标" size="small"
                     @update:model-value="(v: string) => onSetSkill(row, v)">
            <el-option v-for="s in skills" :key="s" :label="s" :value="s" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="作答" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.is_wrong ? 'danger' : 'success'" size="small" effect="plain">
            {{ row.is_wrong ? '错' : '对' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="短文" width="70" align="center">
        <template #default="{ row }">
          <el-icon v-if="row.has_passage" color="#3d8bf5"><Loading v-if="false" /></el-icon>
          <span :class="row.has_passage ? 'yes' : 'no'">{{ row.has_passage ? '有' : '—' }}</span>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination class="pager" layout="total, prev, pager, next, jumper"
                   :total="total" :current-page="page" :page-size="pageSize"
                   @current-change="(p: number) => { page = p; load() }" />
  </div>
</template>

<style scoped>
.page { padding: 4px 2px; }
h2 { margin: 0 0 6px; font-weight: 500; }
.hint { color: #6b7280; font-size: 13px; line-height: 1.6; margin: 0 0 12px; }
.mb { margin-bottom: 12px; }
.stat-row { display: flex; align-items: center; gap: 24px; flex-wrap: wrap; }
.stat { text-align: center; }
.stat .n { font-size: 24px; font-weight: 500; }
.stat .n.ok { color: #16a34a; }
.stat .n.warn { color: #d97706; }
.stat .l { font-size: 12px; color: #6b7280; }
.dist { display: flex; flex-wrap: wrap; gap: 6px; flex: 1; }
.dtag { margin: 0; }
.actions { display: flex; align-items: center; gap: 10px; margin-top: 14px; padding-top: 12px; border-top: 1px solid #f0f0f0; }
.filters { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
.filters .grow { flex: 1; }
.stem { font-size: 13px; color: #374151; }
.yes { color: #3d8bf5; } .no { color: #cbd5e1; }
.pager { margin-top: 12px; justify-content: flex-end; }
</style>
