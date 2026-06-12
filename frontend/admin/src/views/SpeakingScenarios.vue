<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getSpeakingConfig, updateSpeakingConfig, getSpeakingSemesters,
  type SpeakingConfig, type SemScopeUnit,
} from '../api/admin'

const PRESET_TITLES: Record<string, string> = {
  self_intro: '🙋 自我介绍', restaurant: '🍔 餐厅点餐', directions: '🗺️ 问路指路',
  shopping: '🛍️ 购物砍价', hobbies: '🎨 聊聊爱好', school: '🏫 校园生活',
}

const cfg = ref<SpeakingConfig | null>(null)
const units = ref<SemScopeUnit[]>([])
const loading = ref(false)
const saving = ref(false)

async function load() {
  loading.value = true
  try {
    cfg.value = await getSpeakingConfig()
    units.value = await getSpeakingSemesters().catch(() => [])
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!cfg.value) return
  saving.value = true
  try {
    cfg.value = await updateSpeakingConfig(cfg.value)
    ElMessage.success('已保存，约 1 分钟内全端生效')
  } finally {
    saving.value = false
  }
}

const presetKeys = computed(() => Object.keys(cfg.value?.preset || {}))

// ── 学期分级规则编辑 ──
const ruleForm = reactive({ level: 'unit', tv: '', grade: '', sem: '', unitId: '', prompt: '' })
const textbooks = computed(() => [...new Set(units.value.map(u => u.textbook_version))])
const grades = computed(() => [...new Set(units.value.filter(u => u.textbook_version === ruleForm.tv).map(u => u.grade))])
const semesters = computed(() => [...new Set(units.value.filter(u => u.textbook_version === ruleForm.tv && u.grade === ruleForm.grade).map(u => u.semester))])
const unitOpts = computed(() => units.value.filter(u => u.textbook_version === ruleForm.tv && u.grade === ruleForm.grade && u.semester === ruleForm.sem))

function ruleKey(): string | null {
  const { level, tv, grade, sem, unitId } = ruleForm
  if (level === 'textbook') return tv ? `textbook:${tv}` : null
  if (level === 'grade') return tv && grade ? `grade:${tv}/${grade}` : null
  if (level === 'semester') return tv && grade && sem ? `semester:${tv}/${grade}/${sem}` : null
  if (level === 'unit') return unitId ? `unit:${unitId}` : null
  return null
}

function addRule() {
  if (!cfg.value) return
  const k = ruleKey()
  if (!k) { ElMessage.warning('请把该层级的选项选全'); return }
  if (!ruleForm.prompt.trim()) { ElMessage.warning('请填写提示词'); return }
  cfg.value.semester.rules[k] = ruleForm.prompt.trim()
  ruleForm.prompt = ''
  ElMessage.success('已添加规则，记得点底部「保存」')
}
function delRule(k: string) {
  if (cfg.value) delete cfg.value.semester.rules[k]
}
function ruleLabel(k: string): string {
  if (k.startsWith('unit:')) {
    const u = units.value.find(x => x.unit_id === k.slice(5))
    return u ? `单元 · ${u.textbook_version}/${u.grade}/${u.semester} · ${u.unit_title}` : `单元 · ${k.slice(5)}`
  }
  if (k.startsWith('semester:')) return `学期 · ${k.slice(9)}`
  if (k.startsWith('grade:')) return `年级 · ${k.slice(6)}`
  if (k.startsWith('textbook:')) return `教材 · ${k.slice(9)}`
  return k
}
const rulesList = computed(() => Object.entries(cfg.value?.semester.rules || {}))

onMounted(load)
</script>

<template>
  <div v-loading="loading" style="display:flex;flex-direction:column;gap:16px;max-width:820px">
    <el-alert type="info" :closable="false" show-icon
      title="口语对话场景配置：开关控制是否在小程序展示；AI 提示词决定该场景里 AI 的角色与风格（系统会自动追加学生学情焦点和输出格式）。" />

    <template v-if="cfg">
      <!-- 特殊场景 -->
      <el-card>
        <template #header>特殊场景（按学生学情，逻辑固定）</template>
        <div v-for="(item, key) in { '错题薄弱点': cfg.special.wrong, '词力通在练词': cfg.special.vocab }" :key="key" class="row">
          <div class="row-head">
            <span class="row-name">{{ key === '错题薄弱点' ? '🎯 错题薄弱点' : '🔤 词力通在练词' }}</span>
            <el-switch v-model="item.enabled" active-text="启用" inactive-text="停用" />
          </div>
          <el-input v-model="item.prompt" type="textarea" :rows="2" placeholder="AI 提示词（角色/风格）" />
        </div>
      </el-card>

      <!-- 通用场景 -->
      <el-card>
        <template #header>通用场景（预设）</template>
        <div v-for="k in presetKeys" :key="k" class="row">
          <div class="row-head">
            <span class="row-name">{{ PRESET_TITLES[k] || k }}</span>
            <el-switch v-model="cfg.preset[k].enabled" active-text="启用" inactive-text="停用" />
          </div>
          <el-input v-model="cfg.preset[k].prompt" type="textarea" :rows="2" placeholder="AI 提示词（角色/风格）" />
        </div>
      </el-card>

      <!-- 学期场景 -->
      <el-card>
        <template #header>学期场景（每单元，分级提示词）</template>
        <div class="row">
          <div class="row-head">
            <span class="row-name">📖 学期场景总开关</span>
            <el-switch v-model="cfg.semester.enabled" active-text="启用" inactive-text="停用" />
          </div>
        </div>
        <el-form label-width="96px" style="margin-top:8px">
          <el-form-item label="默认提示词">
            <el-input v-model="cfg.semester.default_prompt" type="textarea" :rows="2" />
          </el-form-item>
        </el-form>

        <el-divider content-position="left">分级规则（就近生效：单元 › 学期 › 年级 › 教材 › 默认）</el-divider>
        <div class="rule-add">
          <el-radio-group v-model="ruleForm.level" size="small">
            <el-radio-button label="textbook">教材</el-radio-button>
            <el-radio-button label="grade">年级</el-radio-button>
            <el-radio-button label="semester">学期</el-radio-button>
            <el-radio-button label="unit">单元</el-radio-button>
          </el-radio-group>
          <div class="cascade">
            <el-select v-model="ruleForm.tv" placeholder="教材" size="small" style="width:130px" @change="ruleForm.grade=''; ruleForm.sem=''; ruleForm.unitId=''">
              <el-option v-for="t in textbooks" :key="t" :label="t" :value="t" />
            </el-select>
            <el-select v-if="ruleForm.level!=='textbook'" v-model="ruleForm.grade" placeholder="年级" size="small" style="width:120px" @change="ruleForm.sem=''; ruleForm.unitId=''">
              <el-option v-for="g in grades" :key="g" :label="g" :value="g" />
            </el-select>
            <el-select v-if="ruleForm.level==='semester'||ruleForm.level==='unit'" v-model="ruleForm.sem" placeholder="学期" size="small" style="width:90px" @change="ruleForm.unitId=''">
              <el-option v-for="s in semesters" :key="s" :label="s" :value="s" />
            </el-select>
            <el-select v-if="ruleForm.level==='unit'" v-model="ruleForm.unitId" placeholder="单元" size="small" style="width:200px">
              <el-option v-for="u in unitOpts" :key="u.unit_id" :label="`U${u.unit_no} ${u.unit_title}`" :value="u.unit_id" />
            </el-select>
          </div>
          <el-input v-model="ruleForm.prompt" type="textarea" :rows="2" placeholder="该层级的 AI 提示词" />
          <el-button type="primary" plain size="small" @click="addRule">+ 添加规则</el-button>
        </div>

        <div v-if="rulesList.length" class="rules">
          <div v-for="[k, p] in rulesList" :key="k" class="rule-item">
            <div class="rule-meta">
              <el-tag size="small" type="success">{{ ruleLabel(k) }}</el-tag>
              <el-button link type="danger" size="small" @click="delRule(k)">删除</el-button>
            </div>
            <div class="rule-prompt">{{ p }}</div>
          </div>
        </div>
        <el-empty v-else description="暂无分级规则，未配的单元用默认提示词" :image-size="60" />
      </el-card>

      <el-affix position="bottom" :offset="0">
        <div class="save-bar">
          <el-button type="primary" size="large" :loading="saving" @click="save">保存全部</el-button>
        </div>
      </el-affix>
    </template>
  </div>
</template>

<style scoped>
.row { padding: 10px 0; border-bottom: 1px solid var(--el-border-color-lighter); }
.row:last-child { border-bottom: none; }
.row-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.row-name { font-weight: 600; }
.rule-add { display: flex; flex-direction: column; gap: 10px; }
.cascade { display: flex; gap: 8px; flex-wrap: wrap; }
.rules { margin-top: 14px; display: flex; flex-direction: column; gap: 10px; }
.rule-item { background: var(--el-fill-color-light); border-radius: 8px; padding: 10px 12px; }
.rule-meta { display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px; }
.rule-prompt { font-size: 13px; color: var(--el-text-color-regular); white-space: pre-wrap; }
.save-bar { background: #fff; padding: 12px; box-shadow: 0 -4px 16px rgba(0,0,0,.06); text-align: center; }
</style>
