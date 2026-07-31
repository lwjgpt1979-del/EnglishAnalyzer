<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import AppDialog from '../components/AppDialog.vue'
import OptionVocabChipRow from '../components/OptionVocabChipRow.vue'
import LogicDisplayBlock from '../components/LogicDisplayBlock.vue'
import {
  getVocabOptionRoleStats,
  listRegions,
  listWordPlatformQuestions,
  type RegionNode,
  type VocabOptionRoleRegionRow,
  type VocabOptionRoleWordRow,
  type WordPlatformQuestionRow,
} from '../api/admin'

type ViewTab = 'region-prov' | 'region-city' | 'word-region'

const EXAM_TYPE = '中考'
const POOL_OPTIONS = [
  { value: 'option_vocab_slot', label: '全部空位题(单选+完形+填空)' },
  { value: 'option_mcq', label: '四选一(语法单选+完形)' },
  { value: 'option_fill', label: '填空(词形+开放)' },
  { value: 'standalone_word_mcq', label: '仅语法单选' },
] as const
const tab = ref<ViewTab>('word-region')
const f = reactive({ province: '', city: '', q: '', pool: 'option_vocab_slot' as string })
const provinces = ref<RegionNode[]>([])
const cities = ref<RegionNode[]>([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(50)
const total = ref(0)
const unknownCount = ref(0)
const wordRows = ref<VocabOptionRoleWordRow[]>([])
const regionRows = ref<VocabOptionRoleRegionRow[]>([])

const dlg = ref(false)
const dlgLoading = ref(false)
const dlgTitle = ref('')
const dlgItems = ref<WordPlatformQuestionRow[]>([])
const dlgTotal = ref(0)
const dlgPage = ref(1)
const dlgWordId = ref('')
const dlgRole = ref<'correct' | 'distractor' | 'any'>('any')

/** 传给后端的 region_code:市优先,否则省前缀 */
const regionCode = computed(() => f.city || f.province || undefined)

const crumb = computed(() => {
  const p = provinces.value.find((x) => x.code === f.province)
  const c = cities.value.find((x) => x.code === f.city)
  const parts = ['全国']
  if (p) parts.push(p.name)
  if (c) parts.push(c.name)
  return parts
})

async function loadProvinces() {
  provinces.value = await listRegions()
}

async function loadCities(code: string) {
  cities.value = code ? await listRegions(code) : []
}

watch(() => f.province, async (code) => {
  f.city = ''
  await loadCities(code)
  if (tab.value !== 'region-prov') { page.value = 1; reload() }
})

watch(() => f.city, () => {
  if (tab.value === 'word-region') { page.value = 1; reload() }
})

watch(() => f.pool, () => { page.value = 1; reload() })

watch(tab, () => { page.value = 1; reload() })


function buildParams() {
  const skip = (page.value - 1) * pageSize.value
  if (tab.value === 'region-prov') {
    return {
      exam_type: EXAM_TYPE, pool: f.pool, group_by: 'region' as const,
      region_level: 'province' as const, sort: 'question_count_desc',
      skip, limit: pageSize.value,
    }
  }
  if (tab.value === 'region-city') {
    return {
      exam_type: EXAM_TYPE, pool: f.pool, group_by: 'region' as const,
      region_level: 'city' as const,
      region_code: f.province || undefined,
      sort: 'question_count_desc', skip, limit: pageSize.value,
    }
  }
  return {
    exam_type: EXAM_TYPE, pool: f.pool, group_by: 'word' as const,
    region_code: regionCode.value,
    q: f.q.trim() || undefined,
    sort: 'correct_count_desc', skip, limit: pageSize.value,
  }
}

async function reload() {
  loading.value = true
  try {
    const d = await getVocabOptionRoleStats(buildParams())
    total.value = d.total
    unknownCount.value = d.unknown_question_count ?? 0
    if (tab.value === 'word-region') {
      wordRows.value = d.items as VocabOptionRoleWordRow[]
      regionRows.value = []
    } else {
      regionRows.value = d.items as VocabOptionRoleRegionRow[]
      wordRows.value = []
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function onSearch() { page.value = 1; reload() }
function resetF() {
  f.province = ''
  f.city = ''
  f.q = ''
  f.pool = 'option_vocab_slot'
  page.value = 1
  tab.value = 'word-region'
  reload()
}

function drillToCity(row: VocabOptionRoleRegionRow) {
  f.province = row.region_code
  tab.value = 'region-city'
  page.value = 1
  reload()
}

function openWordList(row: VocabOptionRoleRegionRow) {
  if (tab.value === 'region-city') {
    f.city = row.region_code
  } else {
    f.province = row.region_code
  }
  tab.value = 'word-region'
  page.value = 1
  reload()
}

async function openQuestions(
  row: VocabOptionRoleWordRow,
  role: 'correct' | 'distractor' | 'any',
) {
  const roleLabel = role === 'correct' ? '主·考' : role === 'distractor' ? '次·干扰' : '全部'
  const region = row.region_name || cities.value.find((c) => c.code === f.city)?.name
    || provinces.value.find((p) => p.code === f.province)?.name || '全国'
  dlgTitle.value = `${row.word} · ${roleLabel} · ${region} · ${EXAM_TYPE}`
  dlg.value = true
  dlgPage.value = 1
  dlgWordId.value = row.word_id
  dlgRole.value = role
  await fetchQuestions()
}

async function fetchQuestions() {
  if (!dlgWordId.value) return
  dlgLoading.value = true
  try {
    const d = await listWordPlatformQuestions(dlgWordId.value, {
      role: dlgRole.value,
      pool: f.pool,
      exam_type: EXAM_TYPE,
      region_code: regionCode.value,
      skip: (dlgPage.value - 1) * 20,
      limit: 20,
    })
    dlgItems.value = d.items
    dlgTotal.value = d.total
  } catch (e: any) {
    ElMessage.error(e?.message || '加载原题失败')
  } finally {
    dlgLoading.value = false
  }
}

onMounted(async () => {
  await loadProvinces()
  await reload()
})
</script>

<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3 style="margin:0">中考 · 选项词角色统计</h3>
      <span class="hint">空位逻辑题 · 主·考 / 次·干扰 · 仅校验通过且挂边成功</span>
    </div>

    <div class="filters">
      <el-tag type="warning" effect="plain">{{ EXAM_TYPE }}</el-tag>
      <el-select v-model="f.pool" style="width:220px">
        <el-option v-for="o in POOL_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
      </el-select>
      <el-select v-model="f.province" placeholder="省(全国)" clearable filterable style="width:140px">
        <el-option v-for="p in provinces" :key="p.code" :label="p.name" :value="p.code" />
      </el-select>
      <el-select v-model="f.city" placeholder="市" clearable filterable style="width:140px" :disabled="!f.province">
        <el-option v-for="c in cities" :key="c.code" :label="c.name" :value="c.code" />
      </el-select>
      <el-input v-if="tab === 'word-region'" v-model="f.q" placeholder="搜词" clearable style="width:140px" @keyup.enter="onSearch" />
      <el-button type="primary" @click="onSearch">查询</el-button>
      <el-button @click="resetF">重置</el-button>
    </div>

    <div class="crumb">
      <span v-for="(p, i) in crumb" :key="i">
        <span v-if="i"> / </span><b v-if="i === crumb.length - 1">{{ p }}</b><span v-else>{{ p }}</span>
      </span>
    </div>

    <el-tabs v-model="tab" @tab-change="() => { page = 1 }">
      <el-tab-pane label="按省汇总" name="region-prov" />
      <el-tab-pane label="按市汇总" name="region-city" />
      <el-tab-pane label="词 × 地区" name="word-region" />
    </el-tabs>

    <!-- 按省 -->
    <el-table v-if="tab === 'region-prov'" :data="regionRows" border stripe style="width:100%">
      <el-table-column type="index" label="#" width="50" />
      <el-table-column prop="region_name" label="省" min-width="120">
        <template #default="{ row }"><b>{{ row.region_name || row.region_code }}</b></template>
      </el-table-column>
      <el-table-column prop="question_count" label="原题数" width="100" align="center" sortable />
      <el-table-column prop="word_count" label="挂边词数" width="100" align="center" sortable />
      <el-table-column prop="correct_link_count" label="主·考链" width="100" align="center">
        <template #default="{ row }"><span class="ok">{{ row.correct_link_count }}</span></template>
      </el-table-column>
      <el-table-column prop="distractor_link_count" label="次·干扰链" width="110" align="center">
        <template #default="{ row }"><span class="bad">{{ row.distractor_link_count }}</span></template>
      </el-table-column>
      <el-table-column label="" width="120">
        <template #default="{ row }">
          <el-button link type="primary" @click="drillToCity(row)">下钻各市</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 按市 -->
    <el-table v-else-if="tab === 'region-city'" :data="regionRows" border stripe style="width:100%">
      <el-table-column type="index" label="#" width="50" />
      <el-table-column prop="region_name" label="市" min-width="120">
        <template #default="{ row }"><b>{{ row.region_name || row.region_code }}</b></template>
      </el-table-column>
      <el-table-column prop="question_count" label="原题数" width="100" align="center" sortable />
      <el-table-column prop="word_count" label="挂边词数" width="100" align="center" sortable />
      <el-table-column prop="correct_link_count" label="主·考链" width="100" align="center">
        <template #default="{ row }"><span class="ok">{{ row.correct_link_count }}</span></template>
      </el-table-column>
      <el-table-column prop="distractor_link_count" label="次·干扰链" width="110" align="center">
        <template #default="{ row }"><span class="bad">{{ row.distractor_link_count }}</span></template>
      </el-table-column>
      <el-table-column label="" width="100">
        <template #default="{ row }">
          <el-button link type="primary" @click="openWordList(row)">看词表</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 词表 -->
    <el-table v-else :data="wordRows" border stripe :default-sort="{ prop: 'correct_count', order: 'descending' }" style="width:100%">
      <el-table-column type="index" label="#" width="50" />
      <el-table-column prop="word" label="词" min-width="120" sortable>
        <template #default="{ row }"><b>{{ row.word }}</b></template>
      </el-table-column>
      <el-table-column v-if="f.city" prop="region_name" label="地区" width="100" />
      <el-table-column prop="correct_count" label="主·考(题数)" width="120" align="center" sortable>
        <template #default="{ row }">
          <el-button link type="success" :disabled="!row.correct_count" @click="openQuestions(row, 'correct')">
            {{ row.correct_count }}
          </el-button>
        </template>
      </el-table-column>
      <el-table-column prop="distractor_count" label="次·干扰(题数)" width="130" align="center" sortable>
        <template #default="{ row }">
          <el-button link type="danger" :disabled="!row.distractor_count" @click="openQuestions(row, 'distractor')">
            {{ row.distractor_count }}
          </el-button>
        </template>
      </el-table-column>
      <el-table-column prop="question_count" label="合计题" width="90" align="center" sortable />
      <el-table-column label="" width="100">
        <template #default="{ row }">
          <el-button link type="primary" @click="openQuestions(row, 'any')">全部原题</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="foot">
      <span v-if="unknownCount && tab !== 'word-region'" class="muted">缺地区 {{ unknownCount }} 题</span>
      <el-pagination
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next, jumper"
        @current-change="reload"
      />
    </div>

    <AppDialog v-model="dlg" :title="dlgTitle" width="680px">
      <div v-loading="dlgLoading">
        <div v-for="it in dlgItems" :key="it.question_id + (it.link_kind || '')" class="q-row">
          <div class="q-meta">
            {{ it.exam_type || EXAM_TYPE }}
            <span v-if="it.region_name"> · {{ it.region_name }}</span>
            <span v-if="it.section"> · {{ it.section }}</span>
            <span v-if="it.question_no"> · 第 {{ it.question_no }} 题</span>
            <el-tag v-if="it.analysis_kind" size="small" effect="plain">{{ it.analysis_kind }}</el-tag>
            <el-tag v-if="it.link_kind === 'correct'" size="small" type="success" effect="plain">主·考</el-tag>
            <el-tag v-else-if="it.link_kind === 'distractor'" size="small" type="danger" effect="plain">次·干扰</el-tag>
          </div>
          <div v-if="it.stem" class="q-stem">{{ it.stem }}</div>
          <LogicDisplayBlock
            v-if="it.analysis_kind && !['grammar_mc', 'reading', 'writing', 'sentence'].includes(it.analysis_kind)"
            :logic="it.logic_display"
            compact
          />
          <OptionVocabChipRow :vocab="it.option_vocab" />
        </div>
        <el-empty v-if="!dlgLoading && !dlgItems.length" description="暂无原题" />
        <el-pagination
          v-if="dlgTotal > 20"
          v-model:current-page="dlgPage"
          :page-size="20"
          :total="dlgTotal"
          layout="total, prev, pager, next"
          small
          style="margin-top:12px;justify-content:flex-end"
          @current-change="fetchQuestions"
        />
      </div>
    </AppDialog>
  </div>
</template>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.hint { color: #909399; font-size: 12px; }
.filters { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
.crumb { font-size: 12px; color: #909399; margin-bottom: 10px; }
.crumb b { color: #303133; }
.foot { display: flex; align-items: center; justify-content: space-between; margin-top: 14px; flex-wrap: wrap; gap: 8px; }
.muted { color: #909399; font-size: 12px; }
.ok { color: #2fa98a; font-weight: 600; }
.bad { color: #e85d5d; font-weight: 600; }
.q-row { padding: 10px 0; border-bottom: 1px dashed #ebeef5; }
.q-row:last-child { border-bottom: 0; }
.q-meta { font-size: 11px; color: #909399; margin-bottom: 4px; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.q-stem { font-size: 13px; margin-bottom: 6px; line-height: 1.45; }
</style>
