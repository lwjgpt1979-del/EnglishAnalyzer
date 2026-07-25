<template>
  <div class="page">
    <h2>作文模板 / 范文配置</h2>
    <p class="hint">
      按题型配置：<b>骨架</b>（自由写抽屉用）+ <b>范文/高分句</b>（每行一条）+ <b>搭作文模版</b>（多模版×分段×候选句，JSON）。键 _default 为兜底。
    </p>
    <el-card v-for="(item, key) in form" :key="key" class="tpl-card">
      <template #header>
        <div class="card-head">
          <span>{{ key }}</span>
          <el-button size="small" type="danger" link @click="removeKey(key)">删除</el-button>
        </div>
      </template>
      <div class="lbl">骨架（一句话结构）</div>
      <el-input v-model="item.template" type="textarea" :rows="2" placeholder="称呼→开头→主体→结尾…" />
      <div class="lbl">范文 / 高分句（每行一条）</div>
      <el-input v-model="item.samplesText" type="textarea" :rows="3" placeholder="每行一条" />
      <div class="lbl">
        搭作文模版（JSON 数组：多模版 × 分段 slots × 候选 sentences）
        <el-button size="small" link type="primary" @click="fillExample(key)">填入示例</el-button>
      </div>
      <el-input v-model="item.templatesText" type="textarea" :rows="8" class="mono"
        placeholder='[{"id":"formal","name":"正式版","tag":"稳","slots":[{"key":"greeting","label":"称呼","sentences":["Dear ..."]}]}]' />
      <div v-if="item.err" class="err">JSON 格式错误：{{ item.err }}</div>
    </el-card>

    <div class="add-row">
      <el-input v-model="newKey" placeholder="新增题型（如 邀请信 / 议论文 / _default）" style="width: 240px" />
      <el-button @click="addKey">添加题型</el-button>
    </div>

    <el-button type="primary" :loading="saving" @click="save">保存</el-button>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getEssayTemplates, updateEssayTemplates } from '../api/admin'

type Item = { template: string; samplesText: string; templatesText: string; err?: string }
const form = reactive<Record<string, Item>>({})
const newKey = ref('')
const saving = ref(false)

const EXAMPLE = [{
  id: 'formal', name: '正式版', tag: '稳·得分保险',
  slots: [
    { key: 'greeting', label: '称呼', sentences: ['Dear Mr. Smith,'] },
    { key: 'open', label: '开头·目的', sentences: ["I'm writing to invite you to …"] },
    { key: 'body', label: '主体·时间地点+活动', sentences: ['The activity will be held at … on …, including …'] },
    { key: 'close', label: '结尾·期待+落款', sentences: ['We would be honored if you could join us. Yours, Li Hua'] },
  ],
}]

onMounted(async () => {
  const data = await getEssayTemplates()
  for (const [k, v] of Object.entries(data)) {
    form[k] = {
      template: (v as any).template || '',
      samplesText: ((v as any).samples || []).join('\n'),
      templatesText: (v as any).templates ? JSON.stringify((v as any).templates, null, 2) : '',
    }
  }
})

function addKey() {
  const k = newKey.value.trim()
  if (!k || form[k]) return
  form[k] = { template: '', samplesText: '', templatesText: '' }
  newKey.value = ''
}
function removeKey(k: string) { delete form[k] }
function fillExample(k: string) { form[k].templatesText = JSON.stringify(EXAMPLE, null, 2) }

async function save() {
  // 先校验所有 templatesText JSON
  for (const [k, v] of Object.entries(form)) {
    v.err = ''
    if (v.templatesText.trim()) {
      try {
        const t = JSON.parse(v.templatesText)
        if (!Array.isArray(t)) throw new Error('必须是数组 [ ... ]')
      } catch (e) { v.err = (e as Error).message; ElMessage.error(`「${k}」搭作文模版 JSON 有误`); return }
    }
  }
  saving.value = true
  try {
    const payload: Record<string, any> = {}
    for (const [k, v] of Object.entries(form)) {
      const item: any = {
        template: v.template,
        samples: v.samplesText.split('\n').map((s) => s.trim()).filter(Boolean),
      }
      if (v.templatesText.trim()) item.templates = JSON.parse(v.templatesText)
      payload[k] = item
    }
    await updateEssayTemplates(payload)
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error((e as Error).message || '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.page { padding: 16px; }
.hint { color: #888; font-size: 13px; margin-bottom: 12px; line-height: 1.7; }
.tpl-card { margin-bottom: 16px; }
.card-head { display: flex; justify-content: space-between; align-items: center; }
.lbl { font-size: 12px; color: #888; margin: 12px 0 4px; display: flex; align-items: center; gap: 8px; }
.mono :deep(textarea) { font-family: 'SFMono-Regular', Menlo, Consolas, monospace; font-size: 12px; }
.err { color: #e35b5b; font-size: 12px; margin-top: 4px; }
.add-row { display: flex; gap: 8px; margin: 16px 0; }
</style>
