<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getKpPrompts, saveKpPrompts, getNodeTree, suggestKpText, type KpPrompt, type QuestionKpRef } from '../api/admin'
import type { NodeTreeItem } from '../types'

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
          <span class="focus-label">每{{ t.startsWith('教材') ? '段' : '题' }}考点数</span>
          <span class="muted">至少</span>
          <el-input-number v-model="p.min_kp" :min="0" :max="10" size="small" controls-position="right" style="width:96px" />
          <span class="muted">至多</span>
          <el-input-number v-model="p.max_kp" :min="1" :max="10" size="small" controls-position="right" style="width:96px" />
          <span class="muted">(至少给 AI 提示;至多解析时封顶)</span>
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
.tips-box { margin-bottom: 14px; border: 1px solid #e4e7ed; border-radius: 6px; padding: 0 12px; background: #fafcff; }
.tips-title { font-weight: 600; font-size: 14px; color: #409eff; }
.tips-body { font-size: 13px; color: #5a5e66; line-height: 1.7; }
.tips-body ul { margin: 4px 0 10px; padding-left: 20px; }
.tips-body code { background: #eef1f6; padding: 1px 5px; border-radius: 3px; font-size: 12px; }
.tips-body p { margin: 6px 0; }
</style>
