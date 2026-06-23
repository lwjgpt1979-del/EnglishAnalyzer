<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listLectureNodes, splitLecture, createKnowledgeNode, type LectureNode } from '../api/admin'
import { Check, Close } from '@element-plus/icons-vue'

const GRPS = [{ label: '全部', value: '' }, { label: '词法', value: '词法' }, { label: '句法', value: '句法' }]
const grp = ref('')
const rows = ref<LectureNode[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 10
const loading = ref(false)

// 每个考点的拆分状态:subs=AI建议子考点;accepted=已挂入的名;busy=拆分中
const split = reactive<Record<string, { subs: string[]; accepted: string[]; busy: boolean; open: boolean }>>({})
const showFull = reactive<Record<string, boolean>>({})

async function load() {
  loading.value = true
  try {
    const d = await listLectureNodes({ grp: grp.value || undefined, skip: (page.value - 1) * pageSize, limit: pageSize })
    rows.value = d.items
    total.value = d.total
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}
function reload() { page.value = 1; load() }

async function doSplit(n: LectureNode) {
  if (!split[n.id]) split[n.id] = { subs: [], accepted: [], busy: false, open: true }
  const st = split[n.id]    // 读回响应式代理(不能用 ||= 的返回值,那是原始对象,改之不触发渲染)
  st.busy = true; st.open = true
  try {
    const r = await splitLecture(n.id)
    st.subs = r.subs
    if (!r.subs.length) ElMessage.info(`「${n.name}」AI 未拆出子考点(详解可能是纯表格/过短)`)
  } catch (e: any) { ElMessage.error(e?.message || '拆分失败') }
  finally { st.busy = false }
}
async function accept(n: LectureNode, name: string) {
  const st = split[n.id]
  try {
    await createKnowledgeNode({ name, parent_id: n.id })
    st.accepted.push(name)
    st.subs = st.subs.filter(s => s !== name)
    n.child_count += 1
    ElMessage.success(`已在「${n.name}」下新建子考点「${name}」`)
  } catch (e: any) { ElMessage.error(e?.message || '挂入失败') }
}
function dismiss(n: LectureNode, name: string) {
  const st = split[n.id]
  st.subs = st.subs.filter(s => s !== name)
}
async function acceptAll(n: LectureNode) {
  const st = split[n.id]
  for (const name of [...st.subs]) await accept(n, name)
}

onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3 style="margin:0">详解拆分审核</h3>
      <span style="margin-left:8px">分类</span>
      <el-select v-model="grp" style="width:110px;margin-left:6px" @change="reload">
        <el-option v-for="g in GRPS" :key="g.value" :label="g.label" :value="g.value" />
      </el-select>
      <span class="hint">AI 读每条详解 → 拆成更细的子考点;逐条 ✓ 确认即在该考点下新建子考点(标 ✍人工)。共 {{ total }} 条有详解的考点。</span>
    </div>

    <el-card v-for="n in rows" :key="n.id" shadow="never" class="node-card">
      <div class="node-head">
        <span class="node-name">{{ n.name }}</span>
        <span class="node-code">{{ n.code }}</span>
        <el-tag v-if="n.child_count" size="small" type="info">已有子考点 {{ n.child_count }}</el-tag>
        <el-button size="small" type="primary" :loading="split[n.id]?.busy" style="margin-left:auto" @click="doSplit(n)">
          {{ split[n.id]?.subs?.length || split[n.id]?.accepted?.length ? '重新 AI 拆分' : 'AI 拆分' }}
        </el-button>
      </div>

      <div class="lecture">
        <pre class="md">{{ showFull[n.id] ? n.content : n.content.slice(0, 160) }}{{ !showFull[n.id] && n.content.length > 160 ? '…' : '' }}</pre>
        <el-link v-if="n.content.length > 160" type="primary" :underline="false" @click="showFull[n.id] = !showFull[n.id]">
          {{ showFull[n.id] ? '收起' : '展开详解' }}
        </el-link>
      </div>

      <div v-if="split[n.id]?.open" class="subs">
        <template v-if="split[n.id].subs.length">
          <span class="subs-label">AI 建议子考点:</span>
          <el-tag v-for="s in split[n.id].subs" :key="s" size="small" type="primary" effect="plain" style="border-style:dashed;margin:2px">
            {{ s }}
            <el-icon style="cursor:pointer;color:#67c23a;margin-left:4px;vertical-align:-2px" @click="accept(n, s)"><Check /></el-icon>
            <el-icon style="cursor:pointer;color:#c0c4cc;margin-left:2px;vertical-align:-2px" @click="dismiss(n, s)"><Close /></el-icon>
          </el-tag>
          <el-button size="small" type="success" plain style="margin-left:6px" @click="acceptAll(n)">全部采纳</el-button>
        </template>
        <span v-for="a in (split[n.id].accepted || [])" :key="'a' + a" class="accepted"><el-icon style="vertical-align:-2px;margin-right:2px"><Check /></el-icon>{{ a }} 已挂</span>
        <span v-if="!split[n.id].busy && !split[n.id].subs.length && !split[n.id].accepted.length" class="muted">无可拆子考点</span>
      </div>
    </el-card>

    <div class="pager">
      <el-pagination layout="total, prev, pager, next" :total="total" :page-size="pageSize"
        v-model:current-page="page" @current-change="load" />
    </div>
  </div>
</template>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 6px; margin-bottom: 16px; flex-wrap: wrap; }
.hint { margin-left: 14px; color: #909399; font-size: 12px; }
.node-card { margin-bottom: 12px; }
.node-head { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.node-name { font-weight: 600; font-size: 15px; }
.node-code { font-family: monospace; font-size: 12px; color: #909399; }
.lecture { margin-bottom: 8px; }
.md { white-space: pre-wrap; word-break: break-word; font-size: 12px; line-height: 1.6; color: #606266;
  background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; padding: 8px 10px; margin: 0 0 4px; max-height: 260px; overflow: auto; }
.subs { border-top: 1px dashed #ebeef5; padding-top: 8px; display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
.subs-label { font-size: 12px; color: #909399; }
.accepted { font-size: 12px; color: #67c23a; background: #f0f9eb; padding: 0 8px; border-radius: 8px; margin: 2px; }
.muted { color: #c0c4cc; font-size: 12px; }
.pager { margin-top: 14px; display: flex; justify-content: flex-end; }
</style>
