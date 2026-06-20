<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getKpPrompts, saveKpPrompts, getNodeTree, suggestKpText, type KpPrompt, type QuestionKpRef } from '../api/admin'
import type { NodeTreeItem } from '../types'

const TYPES = ['单选', '听力', '填空', '完型', '阅读', '写作', '教材']
const TYPE_HINT: Record<string, string> = {
  单选: '单项填空/语法选择 — 多挂语法/词汇考点',
  听力: '听力理解(section 含"听力") — 一般留空',
  填空: '单词拼写/选词/完成句子 — 词汇/语法考点',
  完型: '完形填空每空 — 语法/词汇/篇章考点',
  阅读: '阅读理解/信息还原 — 篇章为主,无明确点可留空',
  写作: '书面表达 — 一般留空',
  教材: '教材正文(语法讲解/词汇/课文)→ 抽出覆盖到的考点',
}
const prompts = ref<KpPrompt[]>([])
const kpTree = ref<NodeTreeItem[]>([])     // 知识脑图分类树(供"关注分类"选择)
const treeProps = { label: 'name', children: 'children', value: 'id' }
const loading = ref(false)
const saving = ref(false)

function byType(t: string) { return prompts.value.filter(p => p.question_type === t) }
const totalByType = computed(() => Object.fromEntries(TYPES.map(t => [t, byType(t).length])))

async function load() {
  loading.value = true
  try {
    const [pr, tree] = await Promise.all([getKpPrompts(), getNodeTree('knowledge')])
    prompts.value = pr.prompts.map(p => ({ ...p, focus_node_ids: p.focus_node_ids || [] }))
    kpTree.value = tree.items
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}
function addPrompt(t: string) {
  prompts.value.push({ id: null, name: '新提示词', text: '', question_type: t, is_default: !byType(t).length, focus_node_ids: [], min_kp: 0, max_kp: 2 })
}
function removePrompt(p: KpPrompt) {
  const i = prompts.value.indexOf(p)
  if (i >= 0) prompts.value.splice(i, 1)
  // 删的是默认 → 把该型第一个设默认
  const g = byType(p.question_type)
  if (g.length && !g.some(x => x.is_default)) g[0].is_default = true
}
function setDefault(p: KpPrompt) {
  prompts.value.forEach(x => { if (x.question_type === p.question_type) x.is_default = (x === p) })
}
// 教材正文试匹配
const tryText = ref('')
const trying = ref(false)
const tryResult = ref<QuestionKpRef[] | null>(null)
async function tryMatch() {
  if (!tryText.value.trim()) { ElMessage.warning('请粘贴一段教材正文'); return }
  trying.value = true; tryResult.value = null
  try { tryResult.value = await suggestKpText(tryText.value, '教材') }
  catch (e: any) { ElMessage.error(e?.message || '试匹配失败') }
  finally { trying.value = false }
}

async function save() {
  for (const p of prompts.value) {
    if (!p.text.trim()) { ElMessage.warning(`「${p.name}」提示词内容不能为空`); return }
  }
  saving.value = true
  try {
    prompts.value = (await saveKpPrompts(prompts.value)).prompts
    ElMessage.success('已保存')
  } catch (e: any) { ElMessage.error(e?.message || '保存失败') }
  finally { saving.value = false }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3 style="margin:0">习题匹配知识脑图提示词(按题型)</h3>
      <span class="hint">「AI 建议知识点 / 一键挂」按题型用对应提示词;每题型可多套、选一个默认;可配「关注分类」限定 AI 只在所选知识脑图分类的考点里匹配(空=全部)。</span>
      <el-button type="primary" :loading="saving" style="margin-left:auto" @click="save">保存</el-button>
    </div>

    <el-card v-for="t in TYPES" :key="t" shadow="never" class="type-card">
      <div class="type-head">
        <span class="type-name">{{ t }}</span>
        <span class="type-hint">{{ TYPE_HINT[t] }}</span>
        <span class="muted">{{ totalByType[t] }} 套</span>
        <el-button size="small" link type="primary" style="margin-left:auto" @click="addPrompt(t)">+ 新增提示词</el-button>
      </div>
      <el-empty v-if="!byType(t).length" description="暂无提示词,点右上「+ 新增」" :image-size="44" />
      <div v-for="p in byType(t)" :key="p.id || p.name + Math.random()" class="prompt-row">
        <div class="prompt-head">
          <el-radio :model-value="p.is_default" :value="true" @change="setDefault(p)">默认</el-radio>
          <el-input v-model="p.name" size="small" placeholder="提示词名称" style="width:200px" />
          <el-button size="small" type="danger" link style="margin-left:auto" @click="removePrompt(p)">删除</el-button>
        </div>
        <el-input v-model="p.text" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
          placeholder="给 AI 的指令:如何为该题型的题挑受控考点" />
        <div class="focus-row">
          <span class="focus-label">关注分类</span>
          <el-tree-select v-model="p.focus_node_ids" :data="kpTree" :props="treeProps" node-key="id"
            multiple :render-after-expand="false" check-strictly collapse-tags collapse-tags-tooltip
            placeholder="空 = 全部考点;选几个分类则 AI 只在其下考点里匹配" style="flex:1" />
        </div>
        <div class="focus-row">
          <span class="focus-label">每{{ t === '教材' ? '段' : '题' }}考点数</span>
          <span class="muted">至少</span>
          <el-input-number v-model="p.min_kp" :min="0" :max="10" size="small" controls-position="right" style="width:96px" />
          <span class="muted">至多</span>
          <el-input-number v-model="p.max_kp" :min="1" :max="10" size="small" controls-position="right" style="width:96px" />
          <span class="muted">(至少给 AI 提示;至多解析时封顶)</span>
        </div>
      </div>

      <!-- 教材:粘贴正文试匹配 -->
      <div v-if="t === '教材'" class="try-box">
        <div class="focus-label" style="margin-bottom:6px">试匹配:粘贴一段教材正文,用上面默认提示词看 AI 抽出哪些考点</div>
        <el-input v-model="tryText" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
          placeholder="粘贴教材正文(语法讲解/词汇/课文)…" />
        <div style="margin-top:8px;display:flex;align-items:center;gap:10px;flex-wrap:wrap">
          <el-button size="small" type="primary" :loading="trying" @click="tryMatch">试匹配</el-button>
          <template v-if="tryResult">
            <el-tag v-for="r in tryResult" :key="r.node_id" size="small">{{ r.name }}</el-tag>
            <span v-if="!tryResult.length" class="muted">未匹配到考点</span>
          </template>
        </div>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 14px; margin-bottom: 16px; }
.hint { color: #909399; font-size: 12px; }
.muted { color: #c0c4cc; font-size: 12px; }
.type-card { margin-bottom: 14px; }
.type-head { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
.type-name { font-weight: 600; font-size: 15px; }
.type-hint { color: #909399; font-size: 12px; }
.prompt-row { border-top: 1px dashed #ebeef5; padding: 10px 0; }
.prompt-head { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.focus-row { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
.focus-label { font-size: 12px; color: #909399; flex-shrink: 0; }
.try-box { border-top: 1px dashed #ebeef5; padding-top: 12px; margin-top: 6px; }
</style>
