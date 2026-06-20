<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getKpPrompts, saveKpPrompts, type KpPrompt } from '../api/admin'

const TYPES = ['单选', '填空', '完型', '阅读', '写作']
const TYPE_HINT: Record<string, string> = {
  单选: '单项填空/语法选择 — 多挂语法/词汇考点',
  填空: '单词拼写/选词/完成句子 — 词汇/语法考点',
  完型: '完形填空每空 — 语法/词汇/篇章考点',
  阅读: '阅读理解/信息还原 — 篇章为主,无明确点可留空',
  写作: '书面表达 — 一般留空',
}
const prompts = ref<KpPrompt[]>([])
const loading = ref(false)
const saving = ref(false)

function byType(t: string) { return prompts.value.filter(p => p.question_type === t) }
const totalByType = computed(() => Object.fromEntries(TYPES.map(t => [t, byType(t).length])))

async function load() {
  loading.value = true
  try { prompts.value = (await getKpPrompts()).prompts }
  catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}
function addPrompt(t: string) {
  prompts.value.push({ id: null, name: '新提示词', text: '', question_type: t, is_default: !byType(t).length })
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
      <h3 style="margin:0">知识点 AI 提示词(按题型)</h3>
      <span class="hint">「AI 建议知识点 / 一键挂」按题型用对应提示词;每题型可多套、选一个默认。</span>
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
          placeholder="给 AI 的指令(system 提示):如何为该题型的题挑受控考点" />
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
</style>
