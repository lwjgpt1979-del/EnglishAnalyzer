<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import AppDialog from '../components/AppDialog.vue'
import {
  getUnmatchedGrammarUsage, getKgGrammarUsage, getGrammarParentOptions, promoteGrammar,
  type UnmatchedGrammarRow, type KgGrammarRow, type GrammarParentOption,
} from '../api/admin'

const tab = ref<'unmatched' | 'nodes'>('unmatched')

// —— 未匹配语法(独立题等)——
const um = reactive({ q: '', page: 1, size: 20, total: 0, loading: false })
const umRows = ref<UnmatchedGrammarRow[]>([])
async function loadUm() {
  um.loading = true
  try {
    const d = await getUnmatchedGrammarUsage({ q: um.q.trim() || undefined, skip: (um.page - 1) * um.size, limit: um.size })
    umRows.value = d.items; um.total = d.total
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { um.loading = false }
}
function reloadUm() { um.page = 1; loadUm() }

// —— 图谱语法节点 ——
const kg = reactive({ q: '', page: 1, size: 20, total: 0, loading: false })
const kgRows = ref<KgGrammarRow[]>([])
async function loadKg() {
  kg.loading = true
  try {
    const d = await getKgGrammarUsage({ q: kg.q.trim() || undefined, skip: (kg.page - 1) * kg.size, limit: kg.size })
    kgRows.value = d.items; kg.total = d.total
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { kg.loading = false }
}
function reloadKg() { kg.page = 1; loadKg() }

function onTab() { (tab.value === 'unmatched' ? (umRows.value.length || loadUm()) : (kgRows.value.length || loadKg())) }

// —— 人工加入知识图谱 ——
const promote = reactive({ open: false, name: '', name_norm: '', parentId: '', parentLoading: false, submitting: false })
const parentOpts = ref<GrammarParentOption[]>([])
function openPromote(row: UnmatchedGrammarRow) {
  promote.name = row.name; promote.name_norm = row.name_norm; promote.parentId = ''
  parentOpts.value = []
  promote.open = true
  searchParents('')
}
async function searchParents(q: string) {
  promote.parentLoading = true
  try { parentOpts.value = await getGrammarParentOptions(q.trim() || undefined) }
  catch (e: any) { ElMessage.error(e?.message || '加载父节点失败') }
  finally { promote.parentLoading = false }
}
async function doPromote() {
  if (!promote.parentId) { ElMessage.warning('请选择挂载的父节点(词法/句法子树)'); return }
  promote.submitting = true
  try {
    const r = await promoteGrammar({ name: promote.name, name_norm: promote.name_norm, parent_id: promote.parentId })
    ElMessage.success(`已加入图谱:${r.name}(${r.code}),回填 ${r.backfilled} 个学生的个人语法`)
    promote.open = false
    loadUm()                    // 该语法已收编,从未匹配列表消失
    kgRows.value = []           // 图谱侧数据变了,下次切换重取
  } catch (e: any) { ElMessage.error(e?.message || '加入失败') }
  finally { promote.submitting = false }
}

function fmtDate(s: string | null) { return s ? s.slice(0, 10) : '—' }
function anchorLabel(c: string | null) { return c === 'jf' ? '句法' : c === 'cf' ? '词法' : (c || '—') }

onMounted(loadUm)
</script>

<template>
  <div>
    <div class="toolbar">
      <h3 style="margin:0">语法使用统计</h3>
      <span class="hint">对比「独立题等未匹配上图谱的语法」与「图谱里已有的语法」的使用度;高频未匹配语法可一键人工收编进知识图谱。</span>
    </div>

    <el-tabs v-model="tab" @tab-change="onTab">
      <!-- 未匹配语法 -->
      <el-tab-pane label="未匹配语法(独立题等)" name="unmatched">
        <div v-loading="um.loading">
          <div class="filters">
            <el-input v-model="um.q" placeholder="按语法名搜索" clearable style="width:260px" @keyup.enter="reloadUm" @clear="reloadUm" />
            <el-button type="primary" @click="reloadUm">查询</el-button>
            <span class="muted">口径:命中该语法名的学生数(每学生每名计一次)。ref_node_id 为空 = 未匹配图谱。</span>
          </div>
          <el-table :data="umRows" border stripe style="width:100%">
            <el-table-column type="index" label="#" width="56" :index="(i: number) => (um.page - 1) * um.size + i + 1" />
            <el-table-column prop="name" label="语法名" min-width="240" show-overflow-tooltip />
            <el-table-column label="挂靠" width="90" align="center">
              <template #default="{ row }">{{ anchorLabel(row.anchor_code) }}</template>
            </el-table-column>
            <el-table-column prop="student_count" label="命中学生数" width="120" align="center" />
            <el-table-column prop="paper_count" label="涉及卷数" width="110" align="center" />
            <el-table-column label="最近出现" width="120" align="center">
              <template #default="{ row }">{{ fmtDate(row.last_seen) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="150" align="center" fixed="right">
              <template #default="{ row }">
                <el-button size="small" type="primary" @click="openPromote(row)">加入知识图谱</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-pagination class="pager" layout="total, prev, pager, next, jumper" :total="um.total"
            v-model:current-page="um.page" :page-size="um.size" @current-change="loadUm" />
        </div>
      </el-tab-pane>

      <!-- 图谱语法 -->
      <el-tab-pane label="图谱语法(词法/句法)" name="nodes">
        <div v-loading="kg.loading">
          <div class="filters">
            <el-input v-model="kg.q" placeholder="按语法名搜索" clearable style="width:260px" @keyup.enter="reloadKg" @clear="reloadKg" />
            <el-button type="primary" @click="reloadKg">查询</el-button>
            <span class="muted">引用学生数 = 上传作业里匹配上它的学生;学习人数 = 有掌握台账(实际学过/练过)的学生。</span>
          </div>
          <el-table :data="kgRows" border stripe style="width:100%">
            <el-table-column type="index" label="#" width="56" :index="(i: number) => (kg.page - 1) * kg.size + i + 1" />
            <el-table-column prop="name" label="语法节点" min-width="240" show-overflow-tooltip />
            <el-table-column prop="code" label="编码" width="150" show-overflow-tooltip />
            <el-table-column prop="ref_student_count" label="引用学生数" width="120" align="center" />
            <el-table-column prop="learner_count" label="学习人数" width="120" align="center" />
          </el-table>
          <el-pagination class="pager" layout="total, prev, pager, next, jumper" :total="kg.total"
            v-model:current-page="kg.page" :page-size="kg.size" @current-change="loadKg" />
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 加入知识图谱 -->
    <AppDialog v-model="promote.open" title="加入知识图谱" width="520px">
      <el-form label-width="96px">
        <el-form-item label="语法名">
          <el-input :model-value="promote.name" disabled />
        </el-form-item>
        <el-form-item label="挂载父节点">
          <el-select v-model="promote.parentId" filterable remote :remote-method="searchParents"
            :loading="promote.parentLoading" placeholder="搜索并选择父节点(词法/句法子树)" style="width:100%">
            <el-option v-for="o in parentOpts" :key="o.id" :label="`${o.name}（${o.code}）`" :value="o.id" />
          </el-select>
        </el-form-item>
        <el-alert :closable="false" type="info" show-icon
          title="新节点将建/复用于所选父节点下(继承其轴),并把所有同名未匹配的个人语法回填 ref_node_id —— 学生个人语法即变「已入图谱」,后续上传自动命中。" />
      </el-form>
      <template #footer>
        <el-button @click="promote.open = false">取消</el-button>
        <el-button type="primary" :loading="promote.submitting" @click="doPromote">确认加入</el-button>
      </template>
    </AppDialog>
  </div>
</template>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 6px; margin-bottom: 12px; flex-wrap: wrap; }
.filters { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; flex-wrap: wrap; }
.hint { margin-left: 14px; color: #909399; font-size: 12px; }
.muted { color: #909399; font-size: 12px; }
.pager { margin-top: 14px; justify-content: flex-end; }
</style>
