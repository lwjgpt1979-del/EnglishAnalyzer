<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getKpPrompts, saveKpPrompts, getKpPromptScopes, deleteKpPromptScope,
  getNodeTree, suggestKpText, type KpPrompt, type QuestionKpRef } from '../api/admin'
import type { NodeTreeItem } from '../types'

// 复用编辑器:既做独立页(KpPrompts),也嵌在「课程内容生成」弹窗里按当前学期配置
const props = withDefaults(defineProps<{
  initScopeOn?: boolean      // 初始是否「按学期定制」(弹窗里传 true)
  initTextbook?: string
  initGrade?: string
  initSemester?: string
}>(), { initScopeOn: false, initTextbook: '译林版', initGrade: '七年级', initSemester: '上' })

// 学期 scope:给「教材版本+年级+学期」配独立提示词,无定制则继承全局默认
const VERSIONS = ['译林版', '人教版', '外研版', '北师大版']
const GRADES = ['小学5年级', '小学6年级', '七年级', '八年级', '九年级']
const SEMS = ['上', '下']
const scopeOn = ref(props.initScopeOn)
const sTextbook = ref(props.initTextbook)
const sGrade = ref(props.initGrade)
const sSemester = ref(props.initSemester)
const currentScope = computed(() => scopeOn.value ? `${sTextbook.value}|${sGrade.value}|${sSemester.value}` : '')
const customizedScopes = ref<string[]>([])
const isCustomized = computed(() => !!currentScope.value && customizedScopes.value.includes(currentScope.value))
// 短文是否也匹配「答题技能类」考点(推理判断/情景反应/词义猜测/信息计算/同义转换);默认关=收紧
const includeSkill = ref(false)

const TYPES = ['单选', '听力', '填空', '短文填空', '完型', '单词检测', '句子翻译', '阅读', '写作', '其他',
  '教材·听力', '教材·阅读', '教材·写作', '教材·其他']
const TYPE_HINT: Record<string, string> = {
  单选: '单项填空/语法选择 — 多挂语法/词汇考点',
  听力: '听力理解(section 含"听力") — 一般留空',
  填空: '单词拼写/选词/完成句子 — 词汇/语法考点',
  短文填空: 'section 含"短文填空" — 语境填词,词汇/语法考点',
  完型: '完形填空每空 — 语法/词汇/篇章考点',
  单词检测: 'section 含"单词/词汇检测" — 词义/拼写,1 个词汇考点',
  句子翻译: 'section 含"翻译" — 词汇+句法综合考点',
  阅读: '阅读理解/信息还原 — 篇章为主,无明确点可留空',
  写作: '书面表达 — 一般留空',
  其他: '兜底:未适配到上述题型的题都用这套',
  '教材·听力': '单元听力短文/对话脚本 → 听力考点(lt-*)',
  '教材·阅读': '单元阅读短文 → 阅读考点(rc-*)',
  '教材·写作': '单元写作材料/范文 → 写作考点(wr-*)',
  '教材·其他': '其他教材正文(语法讲解/词汇/课文)→ 覆盖到的考点',
}
const prompts = ref<KpPrompt[]>([])
const kpTree = ref<NodeTreeItem[]>([])     // 知识脑图分类树(供"关注分类"选择)
const treeProps = { label: 'name', children: 'children', value: 'id' }
const loading = ref(false)
const saving = ref(false)
// 扁平 {id,name} 列表:懒渲染(未展开节点不挂 DOM)时,让已选标签仍能显示名称
const kpCacheData = computed(() => {
  const out: { id: string; name: string }[] = []
  const walk = (ns: NodeTreeItem[]) => ns.forEach(n => { out.push({ id: n.id, name: n.name }); if (n.children) walk(n.children) })
  walk(kpTree.value)
  return out
})

function byType(t: string) { return prompts.value.filter(p => p.question_type === t) }
const totalByType = computed(() => Object.fromEntries(TYPES.map(t => [t, byType(t).length])))

async function reloadPrompts() {
  const pr = await getKpPrompts(currentScope.value || undefined)
  prompts.value = pr.prompts.map(p => ({ ...p, focus_node_ids: p.focus_node_ids || [], focus_ranges: p.focus_ranges || {} }))
  includeSkill.value = !!pr.passage_include_skill
}
async function load() {
  loading.value = true
  try {
    const [tree, scopes] = await Promise.all([getNodeTree('knowledge'), getKpPromptScopes()])
    kpTree.value = tree.items
    customizedScopes.value = scopes
    await reloadPrompts()
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}
// 切换 scope(开关/教材/年级/学期)→ 重载该 scope 的提示词
watch(currentScope, async () => {
  loading.value = true
  try { await reloadPrompts() }
  catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
})

async function restoreGlobal() {
  if (!currentScope.value) return
  try {
    await ElMessageBox.confirm(
      `将删除「${currentScope.value}」的定制提示词,恢复为继承全局默认。`, '恢复继承全局',
      { type: 'warning', confirmButtonText: '恢复继承', cancelButtonText: '取消' })
  } catch { return }
  try {
    await deleteKpPromptScope(currentScope.value)
    customizedScopes.value = await getKpPromptScopes()
    await reloadPrompts()
    ElMessage.success('已恢复继承全局默认')
  } catch (e: any) { ElMessage.error(e?.message || '操作失败') }
}
function addPrompt(t: string) {
  prompts.value.push({ id: null, name: '新提示词', text: '', question_type: t, is_default: !byType(t).length, focus_node_ids: [], min_kp: 0, max_kp: 2, focus_ranges: {} })
}

// id → 分类名(供「按分类设范围」显示)
const kpNameById = computed(() => {
  const m: Record<string, string> = {}
  kpCacheData.value.forEach(n => { m[n.id] = n.name })
  return m
})
// 某分类的 [至少,至多]:未单独配则用提示词级范围兜底(显示用)
function catRange(p: KpPrompt, id: string): [number, number] {
  const r = p.focus_ranges?.[id]
  return (Array.isArray(r) && r.length === 2) ? r : [p.min_kp ?? 0, p.max_kp ?? 2]
}
function setCatRange(p: KpPrompt, id: string, idx: 0 | 1, val: number) {
  if (!p.focus_ranges) p.focus_ranges = {}
  const cur = catRange(p, id)
  const v = Math.max(0, Math.round(Number(val) || 0))   // 防 null/小数 → 整数,避免后端 422
  const next: [number, number] = idx === 0 ? [v, cur[1]] : [cur[0], v]
  if (next[0] > next[1]) { if (idx === 0) next[1] = next[0]; else next[0] = next[1] }
  p.focus_ranges[id] = next
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
  try { tryResult.value = await suggestKpText(tryText.value, '教材·其他') }
  catch (e: any) { ElMessage.error(e?.message || '试匹配失败') }
  finally { trying.value = false }
}

async function save() {
  for (const p of prompts.value) {
    if (!p.text.trim()) { ElMessage.warning(`「${p.name}」提示词内容不能为空`); return }
  }
  saving.value = true
  try {
    prompts.value = (await saveKpPrompts(prompts.value, currentScope.value || undefined, includeSkill.value)).prompts
    if (currentScope.value && !customizedScopes.value.includes(currentScope.value)) {
      customizedScopes.value = await getKpPromptScopes()
    }
    ElMessage.success(currentScope.value ? `已保存为「${currentScope.value}」学期定制` : '已保存(全局默认)')
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

    <!-- 学期范围:全局默认 / 按学期定制 -->
    <div class="scope-bar">
      <span class="focus-label">配置范围</span>
      <el-switch v-model="scopeOn" active-text="按学期定制" inactive-text="全局默认" inline-prompt style="--el-switch-on-color:#409eff" />
      <template v-if="scopeOn">
        <el-select v-model="sTextbook" size="small" style="width:120px">
          <el-option v-for="v in VERSIONS" :key="v" :label="v" :value="v" />
        </el-select>
        <el-select v-model="sGrade" size="small" style="width:120px">
          <el-option v-for="g in GRADES" :key="g" :label="g" :value="g" />
        </el-select>
        <el-select v-model="sSemester" size="small" style="width:100px">
          <el-option v-for="s in SEMS" :key="s" :label="s + '学期'" :value="s" />
        </el-select>
        <el-tag :type="isCustomized ? 'success' : 'info'" size="small" effect="plain">
          {{ isCustomized ? '此学期已定制' : '继承全局默认(保存后即生成本学期定制)' }}
        </el-tag>
        <el-button v-if="isCustomized" size="small" link type="warning" @click="restoreGlobal">恢复继承全局</el-button>
      </template>
      <span v-else class="hint">所有学期默认用这套;某学期需要不同提示词时,打开右侧开关单独配。</span>
      <span v-if="customizedScopes.length" class="hint" style="margin-left:auto">已定制学期:{{ customizedScopes.join('、') }}</span>
    </div>

    <!-- 短文匹配口径:是否也挂答题技能类考点(本 scope 级,保存后生效) -->
    <div class="scope-bar" style="background:#fffdf5;border-color:#f5e6c8">
      <span class="focus-label">短文匹配口径</span>
      <el-switch v-model="includeSkill" active-text="也挂答题技能类考点" inactive-text="只挂内容类(收紧)" inline-prompt />
      <span class="hint">开=短文也可挂 推理判断/情景反应/词义猜测/信息计算/同义转换 等技能类考点;关(默认)=只挂主题/主旨/关键信息等内容类。{{ currentScope ? '(应用到本学期)' : '(应用到全局默认)' }}</span>
    </div>

    <!-- 提示词组装说明:固定部分 + 可改部分 + 匹配逻辑,方便日后回看 -->
    <el-collapse class="tips-box">
      <el-collapse-item name="how">
        <template #title>
          <span class="tips-title">提示词怎么组装 / 匹配逻辑(固定 + 可改,点开查看)</span>
        </template>
        <div class="tips-body">
          <p><b>发给 AI 的内容 = 系统消息 + 用户消息</b>,其中只有标【可改】的在本页配置,其余是代码里固定的脚手架:</p>
          <ul>
            <li><b>系统消息（固定·自动生成)</b>:AI 角色 + <u>受控考点目录</u>(按题型/板块自动筛选,并按试卷学段过滤;同一前缀命中缓存)。</li>
            <li><b>用户消息</b> = 【可改:本页「提示词正文」】 + 数量规则(按【可改:每题至少/至多】,且<b>不硬凑</b>) + 题目/短文材料 + 缺口建议规则(固定) + JSON 输出格式(固定)。</li>
          </ul>
          <p><b>① 两段式触发(按「至多」考点数)</b></p>
          <ul>
            <li><b>至多 = 1</b> → <b>一段式</b>:关注分类取并集,一次挑最贴切的 1 个。</li>
            <li><b>至多 &gt; 1 且关注分类 ≥ 2</b> → <b>两段式</b>:按关注分类<b>配置顺序(主→次)</b>各聚焦匹配一段,合并去重后按「至多」截断。<br/><span class="muted">(多分类混在一个大目录里单次问,AI 易漏/飘;拆成各自干净目录分别问更稳)</span></li>
          </ul>
          <p><b>② 不硬凑 + 缺口建议</b>:无贴切考点就给空,<b>不硬凑</b>;真题里某题确有考点但目录没有时,AI 用 <code>propose</code> 建议新建考点 → 页面「🆕 缺口建议」供人工确认添加。</p>
          <p><b>③ 短文额外收紧(仅短文,不影响真题题目)</b>:短文只挂<b>内容类</b>考点(主题/主旨/关键信息/场景人物/篇章结构);排除<b>答题技能类</b>(同义转换、推理判断、信息筛选与计算、词义猜测、情景反应)——这些需配题目才能考查,真题题目里照常保留。</p>
          <p class="muted">本页可改:每个题型/板块的「提示词正文、关注分类、每题至少/至多、多套选默认」。其余(目录注入、JSON 格式、两段式/不硬凑/缺口建议/短文收紧)在代码 <code>kp_suggest_service.py</code> 固定。</p>
        </div>
      </el-collapse-item>
    </el-collapse>

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
            multiple check-strictly collapse-tags collapse-tags-tooltip :cache-data="kpCacheData"
            placeholder="空 = 全部考点;选几个分类则 AI 只在其下考点里匹配" style="flex:1" />
        </div>
        <div class="focus-row">
          <span class="focus-label">默认考点数</span>
          <span class="muted">至少</span>
          <el-input-number v-model="p.min_kp" :min="0" :max="99" size="small" controls-position="right" style="width:96px" />
          <span class="muted">至多</span>
          <el-input-number v-model="p.max_kp" :min="1" :max="99" size="small" controls-position="right" style="width:96px" />
          <span class="muted">(分类未单独设范围时用它;至少给 AI 提示、至多解析时封顶)</span>
        </div>
        <!-- 每个关注分类各设范围;两段式(至多>1 且关注分类≥2)时各分类按各自范围聚焦匹配 -->
        <div v-if="(p.focus_node_ids || []).length" class="cat-ranges">
          <div class="focus-label" style="margin-bottom:4px">按分类设考点数（留空=用上面默认）</div>
          <div v-for="id in p.focus_node_ids" :key="id" class="cat-range-row">
            <span class="cat-name">{{ kpNameById[id] || id }}</span>
            <span class="muted">至少</span>
            <el-input-number :model-value="catRange(p, id)[0]" @update:model-value="(v: number) => setCatRange(p, id, 0, v)"
              :min="0" :max="99" size="small" controls-position="right" style="width:90px" />
            <span class="muted">至多</span>
            <el-input-number :model-value="catRange(p, id)[1]" @update:model-value="(v: number) => setCatRange(p, id, 1, v)"
              :min="1" :max="99" size="small" controls-position="right" style="width:90px" />
            <el-button v-if="p.focus_ranges?.[id]" size="small" link type="info"
              @click="delete p.focus_ranges![id]">恢复默认</el-button>
          </div>
        </div>
      </div>

      <!-- 教材·其他:粘贴正文试匹配 -->
      <div v-if="t === '教材·其他'" class="try-box">
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
.scope-bar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  margin-bottom: 14px; padding: 10px 12px; background: #f4f8ff;
  border: 1px solid #e1ebff; border-radius: 6px; }
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
.cat-ranges { margin-top: 8px; padding: 8px 10px; background: #fafcff; border: 1px dashed #e4e7ed; border-radius: 6px; }
.cat-range-row { display: flex; align-items: center; gap: 8px; margin-top: 6px; }
.cat-name { font-size: 13px; color: #303133; min-width: 120px; }
.try-box { border-top: 1px dashed #ebeef5; padding-top: 12px; margin-top: 6px; }
.tips-box { margin-bottom: 14px; border: 1px solid #e4e7ed; border-radius: 6px; padding: 0 12px; background: #fafcff; }
.tips-title { font-weight: 600; font-size: 14px; color: #409eff; }
.tips-body { font-size: 13px; color: #5a5e66; line-height: 1.7; }
.tips-body ul { margin: 4px 0 10px; padding-left: 20px; }
.tips-body code { background: #eef1f6; padding: 1px 5px; border-radius: 3px; font-size: 12px; }
.tips-body p { margin: 6px 0; }
</style>
