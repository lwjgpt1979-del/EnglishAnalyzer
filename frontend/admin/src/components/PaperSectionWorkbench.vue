<script setup lang="ts">
/**
 * 方案 A · 分题型工作台 — 单个大题(section)内的 KP / 解析操作区
 * 父组件 PlatformQuestions 持有状态与 API;本组件只负责展示与事件上抛
 */
import { computed, ref, watch } from 'vue'
import { Document } from '@element-plus/icons-vue'
import type { PaperQuestion, QuestionKpRef, KpProposal } from '../api/admin'

export type WorkbenchKind = 'grammar' | 'cloze' | 'reading' | 'writing' | 'vocab' | 'passage_fill' | 'generic'

const props = defineProps<{
  sec: { name: string; groups: { key: string | null; passage?: string | null; rows: PaperQuestion[] }[] }
  kind: WorkbenchKind
  checkedIds: string[]
  kpSuggest: Record<string, QuestionKpRef[]>
  kpProposals: Record<string, KpProposal[]>
  genBusy: string | null
  anaBatchBusy: boolean
  simDeriveCount: number
  analyzable: boolean
}>()

const emit = defineEmits<{
  'update:checkedIds': [ids: string[]]
  'ana-batch': []
  'toggle-sec': [checked: boolean]
  'accept-suggest': [q: PaperQuestion, s: QuestionKpRef]
  'dismiss-suggest': [q: PaperQuestion, s: QuestionKpRef]
  'accept-proposal': [q: PaperQuestion, p: KpProposal]
  'dismiss-proposal': [q: PaperQuestion, p: KpProposal]
  'open-kp': [q: PaperQuestion]
  'remove-kp': [q: PaperQuestion, nodeId: string]
  'derive-sim': [q: PaperQuestion]
  'open-analysis': [q: PaperQuestion]
}>()

/** 本 section 全部题 id */
function sectionQuestionIds(): string[] {
  return props.sec.groups.flatMap(g => g.rows.map(r => r.id))
}

const secIds = computed(() => sectionQuestionIds())
const secTotal = computed(() => secIds.value.length)
const secPending = computed(() => props.sec.groups.flatMap(g => g.rows)
  .filter(q => !(q.kps?.length) && !(props.kpSuggest[q.id]?.length) && !(props.kpProposals[q.id]?.length)).length)
const secConfirmed = computed(() => props.sec.groups.flatMap(g => g.rows).filter(q => q.kps?.length).length)
const secAllChecked = computed(() => secIds.value.length > 0 && secIds.value.every(id => props.checkedIds.includes(id)))
const secSomeChecked = computed(() => !secAllChecked.value && secIds.value.some(id => props.checkedIds.includes(id)))

const kindTitle = computed(() => {
  const m: Record<WorkbenchKind, string> = {
    grammar: '语法单选 · 词法/句法考点',
    cloze: '完形填空 · 载体槽 + 线索轴',
    reading: '阅读理解 · rc 技能 + 定位句',
    writing: '书面表达 · 体裁 + 要点清单',
    vocab: '词汇运用 · 词形/搭配考点',
    passage_fill: '短文/缺词填空 · 语篇 + 逐空',
    generic: '题目列表',
  }
  return m[props.kind] || props.sec.name
})

/** 题干摘要(表格列) */
function stemBrief(stem?: string | null, max = 96): string {
  const s = (stem || '').replace(/\s+/g, ' ').trim()
  return s.length <= max ? s : s.slice(0, max) + '…'
}

function toggleCheck(qid: string, on: boolean) {
  const set = new Set(props.checkedIds)
  if (on) set.add(qid); else set.delete(qid)
  emit('update:checkedIds', [...set])
}

function onToggleSec(checked: boolean) {
  emit('toggle-sec', checked)
}

/** 本题是否有 AI 待采纳建议 */
function hasPendingSuggest(q: PaperQuestion): boolean {
  return !!(props.kpSuggest[q.id]?.length || props.kpProposals[q.id]?.length)
}

/** 状态标签 */
function qStatus(q: PaperQuestion): { label: string; type: 'success' | 'warning' | 'info' } {
  if (q.kps?.length) return { label: '已挂 KP', type: 'success' }
  if (hasPendingSuggest(q)) return { label: '待采纳', type: 'warning' }
  return { label: '未挂', type: 'info' }
}

/** 题组待处理数 */
function groupPending(g: { rows: PaperQuestion[] }): number {
  return g.rows.filter(q => !(q.kps?.length) && !(props.kpSuggest[q.id]?.length) && !(props.kpProposals[q.id]?.length)).length
}
function groupConfirmed(g: { rows: PaperQuestion[] }): number {
  return g.rows.filter(q => q.kps?.length).length
}

/** 有 block 的篇章数 */
const passageGroupCount = computed(() =>
  props.sec.groups.filter(g => g.key).length || props.sec.groups.length)

/** 阅读:篇章 Tab 当前索引 */
const activePassageIdx = ref(0)
watch(() => props.sec.name, () => { activePassageIdx.value = 0 })
const activeGroup = computed(() => props.sec.groups[activePassageIdx.value] ?? null)

/** Tab 标签文案 */
function passageTabLabel(gi: number): string {
  const g = props.sec.groups[gi]
  if (!g) return ''
  return g.key ? `Passage ${passageLetter(gi)}` : '独立题'
}

/** 篇章序号 → A/B/C…(仅 block 题组) */
function passageLetter(gi: number): string {
  let n = 0
  for (let i = 0; i <= gi; i++) {
    if (props.sec.groups[i]?.key) n++
  }
  return n > 0 ? String.fromCharCode(64 + n) : '—'
}

/** 卡片标题:取短文首行 */
function passageTitle(g: { key?: string | null; passage?: string | null }, gi: number): string {
  if (!g.passage?.trim()) return g.key ? `Passage ${passageLetter(gi)}` : '独立阅读题'
  const first = g.passage.trim().split('\n')[0].replace(/\s+/g, ' ').trim()
  return first.length > 52 ? first.slice(0, 52) + '…' : first
}

/** 全选 / 取消本篇章 */
function toggleGroupCheck(g: { rows: PaperQuestion[] }, checked: boolean) {
  const set = new Set(props.checkedIds)
  for (const q of g.rows) {
    if (checked) set.add(q.id); else set.delete(q.id)
  }
  emit('update:checkedIds', [...set])
}
function groupAllChecked(g: { rows: PaperQuestion[] }): boolean {
  return g.rows.length > 0 && g.rows.every(q => props.checkedIds.includes(q.id))
}

/** 完形:取第一个有短文的题组(单篇左文右题) */
const primaryPassage = computed(() => {
  for (const g of props.sec.groups) {
    if (g.key && g.passage) return g.passage
  }
  return null
})
</script>

<template>
  <div class="workbench">
    <div class="wb-hd">
      <span class="wb-title">{{ sec.name }} · {{ kindTitle }}</span>
      <span class="wb-sum">
        共 {{ secTotal }} 题
        <template v-if="kind === 'reading'"> · {{ passageGroupCount }} 篇</template>
        · 已挂 {{ secConfirmed }} · 待处理 {{ secPending }}
      </span>
      <div class="wb-actions">
        <el-button v-if="analyzable" size="small" type="warning" plain :loading="anaBatchBusy"
          @click="emit('ana-batch')">{{ anaBatchBusy ? '解析中…' : '批量解析全段' }}</el-button>
        <el-button size="small" :type="secAllChecked ? 'primary' : 'default'" plain
          @click="onToggleSec(!secAllChecked)">
          {{ secAllChecked ? '☑' : (secSomeChecked ? '◪' : '☐') }} 全选本题型
        </el-button>
      </div>
    </div>

    <!-- 语法单选:表格工作台 -->
    <template v-if="kind === 'grammar'">
      <el-table :data="sec.groups.flatMap(g => g.rows)" size="small" stripe class="wb-table"
        :row-key="(r: PaperQuestion) => r.id">
        <el-table-column width="44" align="center">
          <template #default="{ row }">
            <el-checkbox :model-value="checkedIds.includes(row.id)"
              @change="(v: boolean) => toggleCheck(row.id, v)" />
          </template>
        </el-table-column>
        <el-table-column prop="question_no" label="题" width="48" />
        <el-table-column label="题干摘要" min-width="200">
          <template #default="{ row }">
            <div class="stem-cell">{{ stemBrief(row.stem) }}</div>
          </template>
        </el-table-column>
        <el-table-column label="考点" min-width="160">
          <template #default="{ row }">
            <div class="kp-line">
              <el-tag v-for="k in row.kps" :key="k.node_id" size="small" closable
                @close="emit('remove-kp', row, k.node_id)">{{ k.name }}</el-tag>
              <el-tag v-for="s in (kpSuggest[row.id] || [])" :key="'s' + s.node_id" size="small" type="primary"
                effect="plain" style="border-style:dashed">
                AI:{{ s.name }}
                <span class="act-ok" @click="emit('accept-suggest', row, s)">✓</span>
                <span class="act-x" @click="emit('dismiss-suggest', row, s)">✕</span>
              </el-tag>
              <el-tag v-for="(p, pi) in (kpProposals[row.id] || [])" :key="'p' + pi" size="small" type="danger"
                effect="plain" style="border-style:dashed">
                新建:{{ p.name }}
                <span class="act-ok" @click="emit('accept-proposal', row, p)">✓</span>
                <span class="act-x" @click="emit('dismiss-proposal', row, p)">✕</span>
              </el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="88" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="qStatus(row).type">{{ qStatus(row).label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" align="center">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="emit('open-kp', row)">+KP</el-button>
            <el-button v-if="analyzable" size="small" text type="warning" @click="emit('open-analysis', row)">解析</el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- 阅读理解 · 篇章 Tab + 左文右题(一次只显一篇) -->
    <template v-else-if="kind === 'reading'">
      <div class="passage-tabs">
        <button v-for="(g, gi) in sec.groups" :key="g.key || `solo-${gi}`" type="button"
          :class="['passage-tab', { on: activePassageIdx === gi }]"
          @click="activePassageIdx = gi">
          {{ passageTabLabel(gi) }}
          <span class="cnt">{{ g.rows.length }}题</span>
          <span v-if="groupPending(g)" class="bad">·{{ groupPending(g) }}</span>
        </button>
      </div>
      <template v-if="activeGroup">
        <div class="passage-panel-hd">
          <div v-if="activeGroup.key" class="passage-letter">{{ passageLetter(activePassageIdx) }}</div>
          <div class="passage-card-info">
            <b>{{ activeGroup.key ? `Passage ${passageLetter(activePassageIdx)}` : '独立阅读题' }}</b>
            <span>{{ activeGroup.rows.length }} 题 · 已挂 {{ groupConfirmed(activeGroup) }} · 待 {{ groupPending(activeGroup) }}</span>
            <span v-if="activeGroup.passage" class="passage-sub">{{ passageTitle(activeGroup, activePassageIdx) }}</span>
          </div>
          <el-button size="small" :type="groupAllChecked(activeGroup) ? 'primary' : 'default'" plain
            @click="toggleGroupCheck(activeGroup, !groupAllChecked(activeGroup))">
            {{ groupAllChecked(activeGroup) ? '☑' : '☐' }} 全选本篇
          </el-button>
        </div>
        <div class="passage-panel-body">
          <div v-if="activeGroup.passage" class="passage-card-text">
            <div class="passage-card-text-hd">
              <el-icon style="vertical-align:-2px;margin-right:4px"><Document /></el-icon>短文
            </div>
            {{ activeGroup.passage }}
          </div>
          <div v-else class="passage-card-text passage-card-text--empty">
            <span class="hint">本题组无共用短文</span>
          </div>
          <div class="passage-card-qs">
            <el-table :data="activeGroup.rows" size="small" stripe class="rc-table"
              :row-key="(r: PaperQuestion) => r.id">
              <el-table-column width="40" align="center">
                <template #default="{ row }">
                  <el-checkbox :model-value="checkedIds.includes(row.id)"
                    @change="(v: boolean) => toggleCheck(row.id, v)" />
                </template>
              </el-table-column>
              <el-table-column prop="question_no" label="题" width="44" />
              <el-table-column label="题干" min-width="160">
                <template #default="{ row }">
                  <div class="stem-cell">{{ stemBrief(row.stem, 120) }}</div>
                </template>
              </el-table-column>
              <el-table-column label="rc / 考点" min-width="140">
                <template #default="{ row }">
                  <div class="kp-line">
                    <el-tag v-for="k in row.kps" :key="k.node_id" size="small" closable
                      @close="emit('remove-kp', row, k.node_id)">{{ k.name }}</el-tag>
                    <el-tag v-for="s in (kpSuggest[row.id] || [])" :key="'s' + s.node_id" size="small" type="primary"
                      effect="plain" style="border-style:dashed">
                      AI:{{ s.name }}
                      <span class="act-ok" @click="emit('accept-suggest', row, s)">✓</span>
                      <span class="act-x" @click="emit('dismiss-suggest', row, s)">✕</span>
                    </el-tag>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="80" align="center">
                <template #default="{ row }">
                  <el-tag size="small" :type="qStatus(row).type">{{ qStatus(row).label }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="100" align="center">
                <template #default="{ row }">
                  <el-button size="small" text type="primary" @click="emit('open-kp', row)">+KP</el-button>
                  <el-button size="small" text type="warning" @click="emit('open-analysis', row)">解析</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>
      </template>
    </template>

    <!-- 短文/缺词填空:语篇高度随正文,下方逐空列表 -->
    <template v-else-if="kind === 'passage_fill'">
      <div v-for="(g, gi) in sec.groups" :key="g.key || `fill-${gi}`" class="fill-group">
        <div v-if="g.passage" class="passage-block">
          <div class="passage-block-hd">
            <el-icon style="vertical-align:-2px;margin-right:4px"><Document /></el-icon>短文
            <span v-if="g.rows.length" class="passage-block-meta">{{ g.rows.length }} 空</span>
          </div>
          <div class="passage-block-text">{{ g.passage }}</div>
        </div>
        <div v-for="q in g.rows" :key="q.id" class="q-row">
          <el-checkbox :model-value="checkedIds.includes(q.id)"
            @change="(v: boolean) => toggleCheck(q.id, v)" />
          <span class="q-no">{{ q.question_no }}</span>
          <div class="q-body">
            <div class="q-stem">{{ q.stem }}</div>
            <div class="kp-line">
              <el-tag v-for="k in q.kps" :key="k.node_id" size="small" closable
                @close="emit('remove-kp', q, k.node_id)">{{ k.name }}</el-tag>
              <el-tag v-if="!(q.kps?.length) && !hasPendingSuggest(q)" size="small" type="warning" effect="plain">未挂知识点</el-tag>
              <el-tag v-for="s in (kpSuggest[q.id] || [])" :key="'s' + s.node_id" size="small" type="primary"
                effect="plain" style="border-style:dashed">
                AI:{{ s.name }}
                <span class="act-ok" @click="emit('accept-suggest', q, s)">✓</span>
                <span class="act-x" @click="emit('dismiss-suggest', q, s)">✕</span>
              </el-tag>
              <el-tag v-for="(p, pi) in (kpProposals[q.id] || [])" :key="'p' + pi" size="small" type="danger"
                effect="plain" style="border-style:dashed">
                新建:{{ p.name }}
                <span class="act-ok" @click="emit('accept-proposal', q, p)">✓</span>
              </el-tag>
              <el-button size="small" text type="primary" @click="emit('open-kp', q)">+ 知识点</el-button>
              <el-button v-if="analyzable" size="small" text type="warning" @click="emit('open-analysis', q)">解析</el-button>
            </div>
          </div>
          <el-tag size="small" :type="q.status === 'published' ? 'success' : 'info'">
            {{ q.status === 'published' ? '已发布' : '草稿' }}
          </el-tag>
        </div>
      </div>
    </template>

    <!-- 完形:单篇左文右题双栏 -->
    <template v-else-if="kind === 'cloze'">
      <div class="block-layout">
        <div v-if="primaryPassage" class="passage-box">
          <div class="passage-meta"><el-icon style="vertical-align:-2px;margin-right:4px"><Document /></el-icon>短文</div>
          <div class="passage-text">{{ primaryPassage }}</div>
        </div>
        <div class="slot-panel">
          <div v-for="(g, gi) in sec.groups" :key="gi">
            <div v-if="g.key && g.passage && g.passage !== primaryPassage" class="passage-inline">{{ g.passage }}</div>
            <div v-for="q in g.rows" :key="q.id" class="slot-row">
              <el-checkbox :model-value="checkedIds.includes(q.id)"
                @change="(v: boolean) => toggleCheck(q.id, v)" />
              <span class="q-no">{{ q.question_no }}</span>
              <div class="q-body">
                <div class="q-stem">{{ stemBrief(q.stem, 120) }}</div>
                <div class="kp-line">
                  <el-tag v-for="k in q.kps" :key="k.node_id" size="small" closable
                    @close="emit('remove-kp', q, k.node_id)">{{ k.name }}</el-tag>
                  <el-tag v-for="s in (kpSuggest[q.id] || [])" :key="'s' + s.node_id" size="small" type="primary"
                    effect="plain" style="border-style:dashed">
                    AI:{{ s.name }}
                    <span class="act-ok" @click="emit('accept-suggest', q, s)">✓</span>
                  </el-tag>
                  <el-button size="small" text type="primary" @click="emit('open-kp', q)">+KP</el-button>
                  <el-button size="small" text type="warning" @click="emit('open-analysis', q)">解析</el-button>
                </div>
              </div>
              <el-tag size="small" :type="qStatus(q).type">{{ qStatus(q).label }}</el-tag>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- 写作:单题卡片 -->
    <template v-else-if="kind === 'writing'">
      <div v-for="q in sec.groups.flatMap(g => g.rows)" :key="q.id" class="writing-card">
        <div class="writing-hd">
          <el-checkbox :model-value="checkedIds.includes(q.id)"
            @change="(v: boolean) => toggleCheck(q.id, v)" />
          <span class="q-no">{{ q.question_no }}</span>
          <el-tag size="small" :type="qStatus(q).type">{{ qStatus(q).label }}</el-tag>
          <div style="flex:1"></div>
          <el-button size="small" type="warning" @click="emit('open-analysis', q)">解析 / 要点</el-button>
        </div>
        <div class="writing-stem">{{ q.stem }}</div>
        <div class="kp-line">
          <el-tag v-for="k in q.kps" :key="k.node_id" size="small" closable
            @close="emit('remove-kp', q, k.node_id)">{{ k.name }}</el-tag>
          <el-button size="small" text type="primary" @click="emit('open-kp', q)">+KP</el-button>
        </div>
      </div>
    </template>

    <!-- 通用 / 词汇等:紧凑列表(沿用原交互) -->
    <template v-else>
      <div v-for="(g, gi) in sec.groups" :key="gi"
        :class="g.key ? 'group-box' : ''">
        <div v-if="g.key" class="passage-inline">
          <el-icon style="vertical-align:-2px;margin-right:4px"><Document /></el-icon>{{ g.passage }}
        </div>
        <div v-for="q in g.rows" :key="q.id" class="q-row">
          <el-checkbox :model-value="checkedIds.includes(q.id)"
            @change="(v: boolean) => toggleCheck(q.id, v)" />
          <span class="q-no">{{ q.question_no }}</span>
          <div class="q-body">
            <div class="q-stem">{{ q.stem }}</div>
            <div class="kp-line">
              <el-tag v-for="k in q.kps" :key="k.node_id" size="small" closable
                @close="emit('remove-kp', q, k.node_id)">{{ k.name }}</el-tag>
              <el-tag v-if="!(q.kps?.length) && !hasPendingSuggest(q)" size="small" type="warning" effect="plain">未挂知识点</el-tag>
              <el-tag v-for="s in (kpSuggest[q.id] || [])" :key="'s' + s.node_id" size="small" type="primary"
                effect="plain" style="border-style:dashed">
                AI:{{ s.name }}
                <span class="act-ok" @click="emit('accept-suggest', q, s)">✓</span>
                <span class="act-x" @click="emit('dismiss-suggest', q, s)">✕</span>
              </el-tag>
              <el-tag v-for="(p, pi) in (kpProposals[q.id] || [])" :key="'p' + pi" size="small" type="danger"
                effect="plain" style="border-style:dashed">
                新建:{{ p.name }}
                <span class="act-ok" @click="emit('accept-proposal', q, p)">✓</span>
              </el-tag>
              <el-button size="small" text type="primary" @click="emit('open-kp', q)">+ 知识点</el-button>
              <el-button v-if="q.kps?.length" size="small" text type="success" :loading="genBusy === q.id"
                @click="emit('derive-sim', q)">↻ 派生仿真</el-button>
              <el-button v-if="analyzable" size="small" text type="warning" @click="emit('open-analysis', q)">解析</el-button>
            </div>
          </div>
          <el-tag size="small" :type="q.status === 'published' ? 'success' : 'info'">
            {{ q.status === 'published' ? '已发布' : '草稿' }}
          </el-tag>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.workbench {
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  overflow: hidden;
}
.wb-hd {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  padding: 12px 14px;
  border-bottom: 1px solid #ebeef5;
  background: #fafcfe;
}
.wb-title { font-size: 14px; font-weight: 700; color: #303133; }
.wb-sum { font-size: 12px; color: #909399; }
.wb-actions { margin-left: auto; display: flex; flex-wrap: wrap; gap: 6px; }
.wb-table { width: 100%; }
.stem-cell { font-size: 13px; line-height: 1.5; white-space: pre-wrap; }
.kp-line { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; margin-top: 4px; }
.act-ok { cursor: pointer; color: #67c23a; font-weight: 700; margin-left: 3px; }
.act-x { cursor: pointer; color: #c0c4cc; margin-left: 2px; }
.block-layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  padding: 14px;
}
@media (max-width: 900px) { .block-layout { grid-template-columns: 1fr; } }
.passage-box {
  background: #fdf8ee;
  border: 1px solid #ebe6dc;
  border-radius: 8px;
  padding: 14px;
  overflow: visible;
}
.passage-meta { font-size: 11px; color: #909399; margin-bottom: 8px; }
.passage-text {
  font-size: 12px;
  line-height: 1.75;
  color: #444;
  white-space: pre-wrap;
  font-family: Georgia, "Times New Roman", serif;
}
.slot-panel { display: flex; flex-direction: column; gap: 8px; max-height: 420px; overflow: auto; }
.slot-row {
  display: grid;
  grid-template-columns: 28px 36px 1fr auto;
  gap: 8px;
  align-items: start;
  padding: 8px 10px;
  background: #f9fafb;
  border-radius: 6px;
  font-size: 12px;
}
.passage-inline {
  font-size: 12px;
  color: #606266;
  margin-bottom: 8px;
  white-space: pre-wrap;
  padding: 8px;
  background: #f0f9ff;
  border-radius: 6px;
  border-left: 3px solid #0ea5e9;
}
.q-no { color: #909399; font-weight: 700; flex-shrink: 0; width: 30px; }
.q-stem { font-size: 13px; line-height: 1.5; white-space: pre-wrap; }
.q-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 14px;
  border-bottom: 1px dashed #f0f0f0;
  font-size: 13px;
}
.group-box { border: 1px solid #ebeef5; border-radius: 6px; margin: 8px 14px; padding: 8px; background: #fafcff; }
.writing-card {
  margin: 12px 14px;
  padding: 12px;
  border: 1px solid #fed7aa;
  border-radius: 8px;
  background: #fff7ed;
}
.writing-hd { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.writing-stem { font-size: 13px; line-height: 1.6; white-space: pre-wrap; margin-bottom: 8px; }

/* 阅读 · 篇章 Tab + 左文右题 */
.passage-tabs {
  display: flex; gap: 4px; flex-wrap: wrap; padding: 8px 12px 0;
  border-bottom: 1px solid #ebeef5; background: #f8fafc;
}
.passage-tab {
  padding: 8px 14px; border: none; border-radius: 8px 8px 0 0;
  font-size: 12px; font-weight: 700; cursor: pointer; color: #606266;
  background: transparent; border-bottom: 3px solid transparent; margin-bottom: -1px;
}
.passage-tab.on {
  background: #fff; color: #0ea5e9; border-bottom-color: #0ea5e9;
}
.passage-tab .cnt { font-weight: 600; opacity: .75; margin-left: 4px; }
.passage-tab .bad { color: #f56c6c; margin-left: 2px; font-size: 11px; }
.passage-tab.on .bad { color: #f87171; }
.passage-panel-hd {
  display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
  padding: 10px 14px; background: linear-gradient(90deg, #e0f2fe, #f0f9ff);
  border-bottom: 1px solid #bae6fd;
}
.passage-panel-body {
  display: grid; grid-template-columns: 44% 1fr; min-height: 360px;
}
@media (max-width: 900px) { .passage-panel-body { grid-template-columns: 1fr; } }
.passage-letter {
  width: 28px; height: 28px; border-radius: 50%; background: #0ea5e9; color: #fff;
  display: flex; align-items: center; justify-content: center; font-weight: 900; font-size: 13px; flex-shrink: 0;
}
.passage-card-info { flex: 1; min-width: 120px; }
.passage-card-info b { font-size: 13px; display: block; }
.passage-card-info span { font-size: 11px; color: #909399; display: block; margin-top: 2px; }
.passage-sub { color: #606266 !important; font-style: italic; }
.passage-card-text {
  padding: 14px;
  font-size: 12px;
  line-height: 1.75;
  color: #444;
  white-space: pre-wrap;
  border-right: 1px solid #ebeef5;
  max-height: 420px;
  overflow: auto;
  font-family: Georgia, "Times New Roman", serif;
  background: #fdf8ee;
}
.passage-card-text--empty {
  display: flex; align-items: center; justify-content: center;
  background: #fafafa; color: #909399; font-family: inherit;
}
.passage-card-text-hd { font-size: 11px; color: #909399; margin-bottom: 8px; font-family: inherit; }
.passage-card-qs { padding: 8px; overflow: auto; max-height: 420px; }
.rc-table { width: 100%; }
.hint { font-size: 12px; color: #909399; }

/* 短文/缺词填空:语篇区高度随正文 */
.fill-group { margin-bottom: 8px; }
.passage-block {
  margin: 12px 14px 10px;
  background: #f0f9ff;
  border-left: 3px solid #0ea5e9;
  border-radius: 6px;
  padding: 12px 14px;
}
.passage-block-hd {
  font-size: 12px;
  font-weight: 600;
  color: #409eff;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.passage-block-meta { font-size: 11px; color: #909399; font-weight: 400; }
.passage-block-text {
  font-size: 13px;
  line-height: 1.75;
  color: #444;
  white-space: pre-wrap;
}
</style>
