<template>
  <view class="page">
    <view v-if="loading" class="tip">加载中…</view>
    <view v-else-if="!quest" class="tip">暂无细目闯关数据</view>

    <!-- 细目地图 -->
    <template v-else-if="phase === 'map'">
      <view class="hero">
        <text class="hero-t">{{ quest.point_name }}</text>
        <text class="hero-s">细目闯关 · 一句三练</text>
        <view class="prog"><view class="fill" :style="{ width: pct + '%' }" /></view>
        <text class="hero-n">{{ quest.passed_count }}/{{ quest.total }} 细目已过</text>
      </view>
      <view
        v-for="(f, i) in quest.facets" :key="f.name"
        class="facet" :class="{ done: f.passed, cur: isCurrent(i), lock: f.locked && !f.passed }"
        @tap="openFacet(i)"
      >
        <view class="chk" :class="{ on: f.passed, next: isCurrent(i) }">{{ f.passed ? '✓' : '' }}</view>
        <view class="facet-body">
          <text class="facet-name">{{ f.name }}</text>
          <text class="facet-meta">
            {{ facetMeta(f) }}
          </text>
        </view>
        <text v-if="f.passed" class="go">重练</text>
        <text v-else-if="!f.locked" class="go">去学</text>
      </view>
      <view v-if="quest.all_passed" class="done-bar" @tap="backToList">
        <text>细目全过 · 返回单元清单</text>
      </view>
    </template>

    <!-- 看句 -->
    <template v-else-if="phase === 'learn' && curFacet">
      <view class="steps">
        <text class="st done">地图</text>
        <text class="st on">看句</text>
        <text class="st">三练</text>
      </view>
      <view class="rule">
        <text class="rule-h">细目 · {{ curFacet.name }}</text>
        <text class="rule-b">
          {{ curFacet.source === 'ai_demo'
            ? '本细目暂无可用教材句，以下为教学示范句。下一屏用同一句做挖空→改错→选用。'
            : '先看本单元教材原句，下一屏用同一句做挖空→改错→选用。' }}
        </text>
      </view>
      <view
        v-for="(s, i) in displaySentences" :key="i"
        class="sent" :class="{ demo: s.source === 'ai_demo' }"
      >
        <text v-if="s.source === 'ai_demo'" class="badge">示范句</text>
        <text v-else class="badge book">教材原句</text>
        <text class="sent-en">{{ s.text }}</text>
        <text v-if="s.zh_hint" class="sent-zh">{{ s.zh_hint }}</text>
      </view>
      <view class="ft">
        <view class="btn ghost" @tap="phase = 'map'"><text>返回</text></view>
        <view class="btn pri" @tap="startTriple">
          <text>{{ quizList.length ? '开始一句三练' : '暂无练习，返回' }}</text>
        </view>
      </view>
    </template>

    <!-- 一句三练 -->
    <template v-else-if="phase === 'quiz' && curQ">
      <view class="triple">
        <view class="t" :class="stepCls(0)"><text class="n">1</text><text>挖空</text></view>
        <view class="t" :class="stepCls(1)"><text class="n">2</text><text>改错</text></view>
        <view class="t" :class="stepCls(2)"><text class="n">3</text><text>选用</text></view>
      </view>
      <view
        class="src"
        :class="{ demo: curQ.source === 'ai_demo', fold: srcFolded }"
        @tap="onSrcBarTap"
      >
        <view class="src-top">
          <text class="src-l">{{ srcLabel }}</text>
          <view class="src-acts">
            <text v-if="canFoldSrc" class="fold-btn" @tap.stop="toggleSrcFold">{{ srcFolded ? '展开 ›' : '收起' }}</text>
            <view class="ic-btn" :class="{ on: speaking }" @tap.stop="playSrc(true)">
              <view class="ic ic-volume" />
            </view>
          </view>
        </view>
        <text v-if="!srcFolded" class="src-en">{{ curQ.source_sentence }}</text>
      </view>
      <text class="tag">{{ kindLabel(curQ.kind) }} · 第 {{ qi + 1 }}/{{ quizList.length }} 题</text>
      <text class="stem">{{ curQ.stem }}</text>
      <view
        v-for="(opt, oi) in curQ.options" :key="oi"
        class="opt" :class="optCls(opt)"
        @tap="pick(opt)"
      >
        <text>{{ letter(oi) }}. {{ opt }}</text>
      </view>
      <view v-if="picked" class="fb">
        <text :class="lastCorrect ? 'ok' : 'bad'">{{ lastCorrect ? '✓ 答对' : '✗ 答错' }}</text>
        <text class="fb-x">{{ curQ.explanation }}</text>
      </view>
      <view class="ft" v-if="picked">
        <view class="btn pri" @tap="nextQuiz">
          <text>{{ qi >= quizList.length - 1 ? '结算' : nextBtnLabel }}</text>
        </view>
      </view>
    </template>
  </view>
</template>

<script setup lang="ts">
/**
 * 课程语法细目闯关 Q+：细目地图 → 看句 → 一句三练(挖空/改错/选用) → 过关
 * 挖空原句展开;改错/选用默认折叠。进题听原句开关仅在「我的→设置」(方案 B)。
 */
import { computed, ref, watch } from 'vue'
import { onLoad, onShow, onUnload, onHide } from '@dcloudio/uni-app'
import {
  grFacetQuest, grFacetQuestEnsureDemo, grFacetQuestPass,
  type FacetQuest, type FacetQuestItem, type FacetClozeItem, type FacetSentenceItem,
} from '@/api/curriculum'
import { resolveSpeakUrl } from '@/utils/tts'
import { playAudioUrl, stopWordPlay } from '@/utils/wordPlay'
import { getFacetAutoSpeak } from '@/utils/readSeq'

const loading = ref(true)
const quest = ref<FacetQuest | null>(null)
const unitId = ref('')
const nodeId = ref('')
const kpName = ref('')

type Phase = 'map' | 'learn' | 'quiz'
const phase = ref<Phase>('map')
const facetIdx = ref(0)
const quizList = ref<FacetClozeItem[]>([])
const qi = ref(0)
const picked = ref('')
const lastCorrect = ref(false)
const correctCount = ref(0)
/** 改错/选用用户是否手动展开原句 */
const srcUserExpand = ref(false)
const speaking = ref(false)

const pct = computed(() => {
  const q = quest.value
  if (!q || !q.total) return 0
  return Math.round((q.passed_count / q.total) * 100)
})
const curFacet = computed(() => quest.value?.facets[facetIdx.value] || null)
const curQ = computed(() => quizList.value[qi.value] || null)

/** 当前题在本句三练中的步序号 0/1/2 */
const stepInTriple = computed(() => qi.value % 3)

const displaySentences = computed((): FacetSentenceItem[] => {
  const f = curFacet.value
  if (!f) return []
  if (f.sentence_items?.length) return f.sentence_items
  return (f.sentences || []).map((text) => ({
    text,
    source: (f.source || 'textbook') as FacetSentenceItem['source'],
  }))
})

const nextBtnLabel = computed(() => {
  const n = stepInTriple.value
  if (n === 0) return '下一练 · 改错'
  if (n === 1) return '下一练 · 选用'
  return '下一句三练'
})

/** 改错/选用默认折叠原句;挖空始终展开 */
const canFoldSrc = computed(() => {
  const k = curQ.value?.kind
  return k === 'error_fix' || k === 'choose'
})
const srcFolded = computed(() => canFoldSrc.value && !srcUserExpand.value)
const srcLabel = computed(() => {
  const demo = curQ.value?.source === 'ai_demo'
  if (srcFolded.value) return demo ? '示范句（已折叠）' : '教材原句（已折叠）'
  return demo ? '本句示范句（钉住）' : '本句教材原句（钉住）'
})

/**
 * @param {FacetQuestItem} f
 * @returns {string}
 */
function facetMeta(f: FacetQuestItem) {
  const n = f.triples?.length || Math.ceil((f.questions?.length || f.cloze?.length || 0) / 3)
  if (f.need_demo && !n) {
    if (f.passed) return '已过关 · 示范句准备中'
    if (f.locked) return '锁定 · 先完成上一细目'
    return '示范句准备中 · 点进加载'
  }
  const tag = f.source === 'ai_demo' ? '示范句' : '教材句'
  const drill = n ? `${tag} · ${n} 句 × 三练` : '暂无练习'
  if (f.passed) return `已过关 · ${drill}`
  if (f.locked) return '锁定 · 先完成上一细目'
  return drill
}

function letter(i: number) { return String.fromCharCode(65 + i) }
function isCurrent(i: number) {
  const f = quest.value?.facets[i]
  return !!(f && !f.passed && !f.locked)
}
function optCls(opt: string) {
  if (!picked.value) return ''
  if (opt === curQ.value?.answer) return 'ok'
  if (opt === picked.value && !lastCorrect.value) return 'bad'
  return ''
}
/**
 * @param {number} step
 */
function stepCls(step: number) {
  const cur = stepInTriple.value
  if (step < cur) return 'done'
  if (step === cur) return 'on'
  return ''
}
/**
 * @param {string | undefined} kind
 */
function kindLabel(kind?: string) {
  if (kind === 'error_fix') return '改错'
  if (kind === 'choose') return '选用'
  return '挖空'
}

function toggleSrcFold() {
  srcUserExpand.value = !srcUserExpand.value
}
/** 折叠条点空白处展开 */
function onSrcBarTap() {
  if (srcFolded.value) srcUserExpand.value = true
}

/**
 * 播放当前题原句;manual=true 忽略设置开关。
 * @param {boolean} [manual]
 */
async function playSrc(manual = false) {
  const text = (curQ.value?.source_sentence || '').trim()
  if (!text) return
  if (!manual && !getFacetAutoSpeak()) return
  stopWordPlay()
  speaking.value = true
  try {
    const url = await resolveSpeakUrl(text)
    playAudioUrl(url, {
      onEnd: () => { speaking.value = false },
      onError: () => { speaking.value = false },
    })
  } catch {
    speaking.value = false
  }
}

/**
 * 扁平化细目三练题序：优先 triples.steps，否则 questions，再退 cloze。
 * @param {FacetQuestItem} f
 */
function flattenQuiz(f: FacetQuestItem): FacetClozeItem[] {
  if (f.triples?.length) {
    const out: FacetClozeItem[] = []
    for (const t of f.triples) {
      for (const s of t.steps || []) out.push(s)
    }
    return out
  }
  if (f.questions?.length) return f.questions
  return f.cloze || []
}

async function load() {
  if (!unitId.value || !nodeId.value) return
  loading.value = true
  try {
    quest.value = await grFacetQuest(unitId.value, nodeId.value)
    if (quest.value?.point_name) {
      uni.setNavigationBarTitle({ title: quest.value.point_name })
    }
  } catch (e: any) {
    uni.showToast({ title: e?.message || '加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}

async function openFacet(i: number) {
  let f = quest.value?.facets[i]
  if (!f || (f.locked && !f.passed)) {
    uni.showToast({ title: '请先完成上一细目', icon: 'none' })
    return
  }
  if (f.passed) {
    uni.showToast({ title: '已过关，可复看', icon: 'none' })
  }
  facetIdx.value = i
  // 缺句且无缓存:点进时同步 ensure(可付费一次),落物理缓存后任何人不再打 LLM
  if (f.need_demo || !flattenQuiz(f).length) {
    uni.showLoading({ title: '示范句准备中…', mask: true })
    try {
      quest.value = await grFacetQuestEnsureDemo(unitId.value, nodeId.value, f.name)
      f = quest.value?.facets[i]
    } catch (e: any) {
      uni.showToast({ title: e?.message || '示范句加载失败', icon: 'none' })
      return
    } finally {
      uni.hideLoading()
    }
  }
  quizList.value = f ? flattenQuiz(f) : []
  phase.value = 'learn'
}

function startTriple() {
  const f = curFacet.value
  if (!f) return
  const list = flattenQuiz(f)
  if (!list.length) {
    phase.value = 'map'
    return
  }
  quizList.value = list
  qi.value = 0
  picked.value = ''
  correctCount.value = 0
  srcUserExpand.value = false
  phase.value = 'quiz'
  // watch(qi) 会在进入 quiz 后触发进题播
}

function pick(opt: string) {
  if (picked.value || !curQ.value) return
  picked.value = opt
  lastCorrect.value = opt === curQ.value.answer
  if (lastCorrect.value) correctCount.value += 1
}

async function nextQuiz() {
  if (qi.value < quizList.value.length - 1) {
    qi.value += 1
    picked.value = ''
    srcUserExpand.value = false
    return
  }
  const need = quizList.value.length
  if (correctCount.value < need) {
    uni.showModal({
      title: '尚未过关',
      content: `本题组 ${correctCount.value}/${need} 对。需全部答对才勾选细目，要重练吗？`,
      confirmText: '重练',
      success: (r) => {
        if (r.confirm) startTriple()
        else phase.value = 'learn'
      },
    })
    return
  }
  const name = curFacet.value?.name || ''
  try {
    quest.value = await grFacetQuestPass(unitId.value, nodeId.value, name)
    uni.showToast({ title: '细目过关', icon: 'success' })
    phase.value = 'map'
  } catch (e: any) {
    uni.showToast({ title: e?.message || '过关失败', icon: 'none' })
  }
}

/** 课程链不进四维/讲解页，回单元语法清单 */
function backToList() {
  uni.navigateBack({ fail: () => uni.showToast({ title: '细目已全过', icon: 'success' }) })
}

/** 进入每一题(含切题)时:重置折叠 + 按设置自动播原句 */
watch(
  () => (phase.value === 'quiz' ? `${qi.value}|${curQ.value?.id || ''}` : ''),
  (key) => {
    if (!key || !curQ.value) return
    srcUserExpand.value = false
    speaking.value = false
    stopWordPlay()
    playSrc(false)
  },
)

onLoad((q: any) => {
  unitId.value = q.unit || q.unit_id || ''
  nodeId.value = q.node || q.node_id || q.id || ''
  kpName.value = q.name ? decodeURIComponent(q.name) : ''
  if (kpName.value) uni.setNavigationBarTitle({ title: kpName.value })
  load()
})
onShow(() => {
  if (quest.value && phase.value === 'map') load()
})
onHide(() => { stopWordPlay(); speaking.value = false })
onUnload(() => { stopWordPlay(); speaking.value = false })
</script>

<style scoped>
.page { min-height: 100vh; background: #f0f6fc; padding: 24rpx; box-sizing: border-box; padding-bottom: 160rpx; }
.tip { text-align: center; color: #94a3b8; padding: 80rpx 24rpx; }
.hero {
  position: relative; overflow: hidden; border-radius: 20rpx; padding: 28rpx;
  background: linear-gradient(135deg, #5b8def, #3d8bf5 55%, #2f6fd4); color: #fff; margin-bottom: 20rpx;
}
.hero-t { font-size: 34rpx; font-weight: 700; display: block; }
.hero-s { font-size: 22rpx; opacity: .9; display: block; margin-top: 6rpx; }
.prog { height: 10rpx; border-radius: 5rpx; background: rgba(255,255,255,.25); margin: 18rpx 0 8rpx; overflow: hidden; }
.fill { height: 100%; background: #fff; border-radius: 5rpx; transition: width .3s; }
.hero-n { font-size: 22rpx; opacity: .95; }
.facet {
  display: flex; align-items: flex-start; gap: 16rpx; background: #fff;
  border: 1rpx solid #e8edf3; border-radius: 16rpx; padding: 22rpx; margin-bottom: 14rpx;
}
.facet.done { background: #f3fbf8; border-color: #b7e4d4; }
.facet.cur { border-color: #bfdbfe; box-shadow: 0 0 0 4rpx #dbeafe; }
.facet.lock { opacity: .5; }
.chk {
  width: 36rpx; height: 36rpx; border-radius: 50%; border: 4rpx solid #cbd5e1;
  display: flex; align-items: center; justify-content: center; font-size: 20rpx; color: #fff; flex-shrink: 0; margin-top: 4rpx;
}
.chk.on { background: #2fa98a; border-color: #2fa98a; }
.chk.next { border-color: #3d8bf5; }
.facet-body { flex: 1; min-width: 0; }
.facet-name { font-size: 28rpx; font-weight: 700; color: #1e293b; display: block; }
.facet-meta { font-size: 22rpx; color: #94a3b8; margin-top: 6rpx; display: block; }
.go { font-size: 24rpx; color: #3d8bf5; flex-shrink: 0; padding-top: 4rpx; }
.done-bar {
  margin-top: 12rpx; background: #2fa98a; color: #fff; text-align: center;
  border-radius: 14rpx; padding: 24rpx; font-size: 28rpx; font-weight: 600;
}
.steps { display: flex; gap: 10rpx; margin-bottom: 16rpx; flex-wrap: wrap; }
.st { font-size: 20rpx; padding: 8rpx 16rpx; border-radius: 999rpx; background: #f1f5f9; color: #94a3b8; }
.st.on { background: #e8f2ff; color: #3d8bf5; font-weight: 700; }
.st.done { background: #e9f6f1; color: #1f7a61; }
.rule {
  background: #e8f2ff; border-radius: 16rpx; padding: 22rpx; margin-bottom: 16rpx;
}
.rule-h { font-size: 28rpx; font-weight: 700; color: #1e4a7a; display: block; }
.rule-b { font-size: 24rpx; color: #3d5a80; margin-top: 8rpx; display: block; line-height: 1.5; }
.sent {
  background: #fff; border: 1rpx solid #e8edf3; border-radius: 12rpx;
  padding: 20rpx; margin-bottom: 12rpx;
}
.sent.demo { background: #fff8eb; border-color: #f3d19e; }
.badge {
  display: inline-block; font-size: 20rpx; padding: 2rpx 12rpx; border-radius: 999rpx;
  background: #fff3d6; color: #9a6700; font-weight: 600; margin-bottom: 8rpx;
}
.badge.book { background: #e8f2ff; color: #3d8bf5; }
.sent-en { font-size: 28rpx; color: #334155; line-height: 1.55; display: block; }
.sent-zh { font-size: 22rpx; color: #94a3b8; margin-top: 8rpx; display: block; }
.triple {
  display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10rpx; margin-bottom: 16rpx;
}
.triple .t {
  text-align: center; font-size: 20rpx; padding: 12rpx 4rpx; border-radius: 12rpx;
  background: #f1f5f9; color: #94a3b8; display: flex; flex-direction: column; align-items: center;
}
.triple .t .n { font-size: 26rpx; font-weight: 800; }
.triple .t.on { background: #e8f2ff; color: #3d8bf5; font-weight: 700; }
.triple .t.done { background: #e9f6f1; color: #1f7a61; }
.src {
  background: #fff8eb; border: 1rpx solid #f3d19e; border-radius: 12rpx;
  padding: 16rpx 18rpx; margin-bottom: 14rpx;
}
.src.demo { background: #fff8eb; }
.src.fold { padding: 14rpx 16rpx; }
.src-top { display: flex; align-items: center; justify-content: space-between; gap: 12rpx; }
.src-l { font-size: 20rpx; color: #9a6700; font-weight: 600; flex: 1; min-width: 0; }
.src-acts { display: flex; align-items: center; gap: 12rpx; flex-shrink: 0; }
.fold-btn { font-size: 22rpx; color: #3d8bf5; font-weight: 600; }
.ic-btn {
  width: 52rpx; height: 52rpx; border-radius: 12rpx; border: 1rpx solid #f3d19e;
  background: #fff; display: flex; align-items: center; justify-content: center;
}
.ic-btn.on { background: #e8f2ff; border-color: #bfdbfe; }
.ic-btn .ic { width: 32rpx; height: 32rpx; }
.src-en { font-size: 28rpx; font-weight: 700; color: #1e293b; margin-top: 10rpx; display: block; }
.tag {
  display: inline-block; font-size: 20rpx; padding: 4rpx 14rpx; border-radius: 999rpx;
  background: #e8f2ff; color: #3d8bf5; font-weight: 600; margin-bottom: 10rpx;
}
.stem { font-size: 32rpx; font-weight: 700; color: #1e293b; display: block; margin: 8rpx 0 20rpx; line-height: 1.45; white-space: pre-wrap; }
.opt {
  background: #fff; border: 2rpx solid #e8edf3; border-radius: 14rpx;
  padding: 22rpx; margin-bottom: 12rpx; font-size: 28rpx; color: #334155;
}
.opt.ok { border-color: #b7e4d4; background: #f3fbf8; }
.opt.bad { border-color: #fecaca; background: #fff5f5; }
.fb { background: #eef6ff; border-radius: 12rpx; padding: 18rpx; margin-top: 8rpx; }
.fb .ok { color: #1f7a61; font-weight: 700; display: block; }
.fb .bad { color: #b91c1c; font-weight: 700; display: block; }
.fb-x { font-size: 24rpx; color: #1e4a7a; margin-top: 8rpx; display: block; line-height: 1.5; }
.ft {
  position: fixed; left: 0; right: 0; bottom: 0; display: flex; gap: 16rpx;
  padding: 20rpx 24rpx calc(20rpx + env(safe-area-inset-bottom)); background: #fff;
  border-top: 1rpx solid #e8edf3;
}
.btn {
  flex: 1; height: 80rpx; border-radius: 14rpx; display: flex; align-items: center; justify-content: center;
  font-size: 28rpx; font-weight: 600;
}
.btn.pri { background: #3d8bf5; color: #fff; }
.btn.ghost { background: #f1f5f9; color: #475569; }
</style>
