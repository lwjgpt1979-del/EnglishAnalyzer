<template>
  <view class="si">
    <!-- 数据不足(旧缓存无 structure/components)→ 降级提示,回快速看树 -->
    <view v-if="!dataOk" class="si-fallback">
      <text>本句暂无足够结构数据做精读闯关,请切换「快速看树」查看。</text>
    </view>

    <template v-else>
      <!-- 闯关路径:找主干 → 读主干 → 拆修饰 → 句型迁移 -->
      <view class="path">
        <template v-for="(st, i) in stages" :key="i">
          <view class="seg-line" v-if="i > 0" :class="{ done: i <= stage }"></view>
          <view class="node">
            <view class="dotc" :class="i < stage ? 'done' : (i === stage ? 'now' : 'lock')">
              <text v-if="i < stage">✓</text>
              <text v-else-if="i === stage">{{ i + 1 }}</text>
              <text v-else class="lk">·</text>
            </view>
            <text class="nl" :class="{ a: i === stage }">{{ st }}</text>
          </view>
        </template>
      </view>

      <!-- 关1:找主干 -->
      <view v-if="stage === 0" class="stage">
        <view class="stitle"><text class="snum">1</text>先找主干:点出主句的「主语」和「谓语」</view>
        <view class="q-sent">
          <text v-for="(s, i) in segList" :key="i" class="tk"
            :class="{ pick: picked.has(idxOf(s)), done: corePassed }" @tap="tapCore(s)">{{ s.text }} </text>
        </view>
        <text v-if="!corePassed" class="hint">先别看解析——自己找。抓住主干,长句就塌成一句简单句。</text>
        <view v-else class="ok"><text>✓ 找对了!主干 = 主语 + 谓语,先抓它。</text></view>
      </view>

      <!-- 关2:读主干 -->
      <view v-else-if="stage === 1" class="stage">
        <view class="stitle"><text class="snum">2</text>读主干:剥掉修饰,先读懂骨架</view>
        <view class="core-box">
          <view v-for="(c, i) in coreRows" :key="i" class="core-row">
            <text class="core-role">{{ c.role }}</text>
            <text class="core-en">{{ c.text }}</text>
          </view>
        </view>
        <text class="hint">工作记忆先装下这几个组块(谁 → 做了什么 → 得到什么),再往上加修饰。</text>
      </view>

      <!-- 关3:拆修饰(先状语后定语),每层一道微测 -->
      <view v-else-if="stage === 2" class="stage">
        <view class="stitle"><text class="snum">3</text>拆修饰:一次一层 · {{ modDone }}/{{ mods.length }}</view>
        <view v-if="curMod" class="qbox" :class="'lv-' + curMod.grp">
          <text class="qh">{{ curMod.grpLabel }} · 先状语后定语</text>
          <text class="qs">{{ curMod.text }}</text>
          <text class="q-ask">{{ curMod.ask }}</text>
          <view class="opt" v-for="(o, oi) in curMod.options" :key="oi"
            :class="optCls(oi)" @tap="tapMod(oi)">
            <text>{{ o }}</text>
          </view>
          <view v-if="modAnswered" class="mfeed">
            <text class="mfeed-r" :class="{ ok: modCorrect }">{{ modCorrect ? '✓ 对' : '✗ 再看一眼' }}</text>
            <text class="mfeed-a">{{ curMod.answerNote }}</text>
            <text class="mfeed-next" @tap="nextMod">{{ modDone + 1 >= mods.length ? '拆完 → 看句型' : '下一层 ›' }}</text>
          </view>
        </view>
      </view>

      <!-- 关4:句型 + 练同型句(接迁移探针:同结构新句 + 理解检测) -->
      <view v-else class="stage">
        <view class="stitle"><text class="snum">4</text>抽成句型:下次遇同型能套</view>
        <view class="patc">
          <text v-for="(p, i) in patternParts" :key="i" class="pp" :class="{ core: p.core }">{{ p.label }}<text v-if="i < patternParts.length - 1" class="pp-plus"> + </text></text>
        </view>

        <!-- 默认:入口 -->
        <template v-if="t4 === 'pattern'">
          <text class="hint">学的不是"这一句",是"这类句子"。练一句同型新句,验证你真会这个句法。</text>
          <view class="mig" @tap="startTransfer"><text>练同型长句 ›</text></view>
        </template>

        <view v-else-if="t4 === 'loading'" class="tp-tip">找同型新句中…</view>
        <view v-else-if="t4 === 'none'" class="tp-tip">
          <text>暂无同结构的新句(该句法较少见),晚点再试。</text>
          <view class="mig ghost" @tap="t4 = 'pattern'"><text>返回</text></view>
        </view>

        <!-- 同型新句 + 理解检测 -->
        <template v-else-if="t4 === 'quiz' && tfItem">
          <view class="tf-sent"><text class="tf-lb">同型新句(同结构 · 新内容)</text><text class="tf-text">{{ tfItem.text }}</text></view>
          <view v-if="tfShared.length" class="tf-shared"><text v-for="(s, i) in tfShared" :key="i" class="tf-chip">{{ s }}</text></view>
          <view v-for="p in tfProbes" :key="p.key" class="tf-probe">
            <text class="tf-q">{{ p.prompt }}</text>
            <view v-for="(o, oi) in p.options" :key="oi" class="opt" :class="{ 'opt-sel': tfAnswers[p.key] === o }" @tap="pickTf(p.key, o)"><text>{{ o }}</text></view>
          </view>
          <view class="mig" :class="{ ghost: !allTfAnswered || tfSubmitting }" @tap="submitTf"><text>{{ tfSubmitting ? '判分中…' : '提交' }}</text></view>
        </template>

        <!-- 结论:真会 vs 疑似记住 -->
        <template v-else-if="t4 === 'result' && tfResult">
          <view class="tf-res" :class="{ ok: tfResult.passed }">
            <text class="tf-res-t">{{ tfResult.passed ? '✓ 同型新句也读懂了 —— 你真掌握了这个句法' : '✗ 换句就卡了 —— 像是记住了原句,再练几句' }}</text>
          </view>
          <view v-for="pr in (tfResult.probes || [])" :key="pr.key" class="tf-pr" :class="{ ok: pr.correct }">
            <text>{{ pr.correct ? '✓' : '✗' }} 正确:{{ pr.correct_answer }}</text>
          </view>
          <view class="tf-btns">
            <view class="mig ghost" @tap="t4 = 'pattern'"><text>完成</text></view>
            <view class="mig" @tap="startTransfer"><text>再来一句 ›</text></view>
          </view>
        </template>
      </view>

      <!-- 关卡导航 -->
      <view class="nav">
        <view class="nav-btn" :class="{ dis: stage === 0 }" @tap="prev"><text>‹ 上一步</text></view>
        <view class="nav-btn primary" :class="{ dis: !canNext }" @tap="next">
          <text>{{ stage >= stages.length - 1 ? '重来 ↺' : '下一步 ›' }}</text>
        </view>
      </view>
    </template>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { getTransferForText, submitComprehension, type ComprehensionProbe, type TransferItem } from '@/api/longSentence'

const props = defineProps<{ a: any; text?: string }>()

const stages = ['找主干', '读主干', '拆修饰', '句型迁移']
const stage = ref(0)

// ── 从分析 JSON 派生(纯规则,无 LLM):segments + structure(parent) + components ──
function idxOf(s: any): number { return s.__idx }
const segList = computed<any[]>(() =>
  (props.a?.segments || []).map((s: any, i: number) => ({ ...s, __idx: s.idx ?? i + 1 })))
const parentOf = computed<Record<number, number | null>>(() => {
  const m: Record<number, number | null> = {}
  ;(props.a?.structure || []).forEach((x: any) => { m[x.idx] = x.parent ?? null })
  return m
})
const byIdx = computed<Record<number, any>>(() => {
  const m: Record<number, any> = {}; segList.value.forEach(s => { m[s.__idx] = s }); return m
})
// 主干 = structure.parent 为 null 的成分;缺 structure 时按 type 兜底(主/谓/宾/表)
function isCoreSeg(s: any): boolean {
  const p = parentOf.value[s.__idx]
  if (p !== undefined) return p === null
  return /主语|谓语|宾语|表语|主句|主干/.test(s.type || '')
}
const cores = computed(() => segList.value.filter(isCoreSeg))
const comps = computed(() => props.a?.components || {})
const dataOk = computed(() =>
  segList.value.length > 0 && (cores.value.length > 0 || comps.value.subject || comps.value.predicate))

// 主语/谓语 段(关1 正确答案)
const subjSeg = computed(() => cores.value.find(s => /主语/.test(s.type || '')))
const predSeg = computed(() => cores.value.find(s => /谓语/.test(s.type || '')))

// ── 关1:点主干 ──
const picked = ref<Set<number>>(new Set())
const corePassed = ref(false)
function tapCore(s: any) {
  if (corePassed.value) return
  const set = new Set(picked.value)
  set.has(s.__idx) ? set.delete(s.__idx) : set.add(s.__idx)
  picked.value = set
  const needS = subjSeg.value ? set.has(subjSeg.value.__idx) : true
  const needP = predSeg.value ? set.has(predSeg.value.__idx) : true
  if (needS && needP && (subjSeg.value || predSeg.value)) corePassed.value = true
}

// ── 关2:主干各成分带角色标 ──
const coreRows = computed(() => cores.value.map(s => ({ role: shortType(s.type), text: s.text })))

// ── 关3:修饰成分(先状语后定语)+ 每层微测 ──
function grpRank(type: string): number {
  if (/定语/.test(type)) return 1               // 定语(含定语从句)最后
  if (/状语|从句/.test(type)) return 0          // 状语、其它从句先
  return 2
}
const TYPE_POOL = ['时间状语', '地点状语', '原因状语', '后置定语', '定语从句', '宾语从句', '非谓语', '同位语']
const mods = computed(() => {
  const list = segList.value.filter(s => !isCoreSeg(s))
    .sort((x, y) => grpRank(x.type) - grpRank(y.type) || x.__idx - y.__idx)
  return list.map(s => {
    const grp = grpRank(s.type)
    const grpLabel = grp === 0 ? '状语层' : grp === 1 ? '定语层' : '修饰层'
    const isAttr = /定语/.test(s.type || '')
    const head = parentOf.value[s.__idx] != null ? byIdx.value[parentOf.value[s.__idx]!] : null
    // 定语且能查到中心词 → 「修饰哪个词?」;否则 → 「这是什么成分?」
    if (isAttr && head && /主语|宾语|表语/.test(head.type || '')) {
      const nouns = cores.value.filter(c => /主语|宾语|表语/.test(c.type || ''))
      let opts = uniq([head.text, ...nouns.map(n => n.text)])
      if (opts.length < 2) opts = uniq([head.text, ...cores.value.map(c => c.text)])
      opts = opts.slice(0, 3)
      return { ...s, grp, grpLabel, ask: '这个后置定语修饰哪个词?',
        options: opts, correct: opts.indexOf(head.text),
        answerNote: `修饰:${head.text}` }
    }
    const ct = shortType(s.type)
    const distract = TYPE_POOL.filter(t => t !== ct).slice(0, 2)
    const opts = uniq([ct, ...distract]).slice(0, 3)
    return { ...s, grp, grpLabel, ask: '这是什么成分?',
      options: opts, correct: opts.indexOf(ct),
      answerNote: head ? `${ct} · 修饰/隶属:${head.text}` : ct }
  })
})
const modDone = ref(0)
const modPick = ref<number | null>(null)
const curMod = computed(() => mods.value[modDone.value] || null)
const modAnswered = computed(() => modPick.value != null)
const modCorrect = computed(() => curMod.value && modPick.value === curMod.value.correct)
function tapMod(oi: number) { if (modPick.value == null) modPick.value = oi }
function nextMod() {
  if (modDone.value + 1 >= mods.value.length) { stage.value = 3; return }
  modDone.value += 1; modPick.value = null
}
function optCls(oi: number) {
  if (modPick.value == null) return ''
  if (curMod.value && oi === curMod.value.correct) return 'opt-ok'
  if (oi === modPick.value) return 'opt-no'
  return 'opt-dim'
}

// ── 关4:句型卡(按原文顺序把每段映射成角色标,主干加粗)──
const patternParts = computed(() =>
  segList.value.map(s => ({ label: shortType(s.type), core: isCoreSeg(s) })))

// ── 关卡推进 ──
const canNext = computed(() => {
  if (stage.value === 0) return corePassed.value
  if (stage.value === 2) return modDone.value >= mods.value.length - 1 && modAnswered.value
  return true
})
function next() {
  if (stage.value >= stages.length - 1) { reset(); return }
  if (!canNext.value) return
  stage.value += 1
}
function prev() { if (stage.value > 0) stage.value -= 1 }
function reset() {
  stage.value = 0; picked.value = new Set(); corePassed.value = false
  modDone.value = 0; modPick.value = null
  t4.value = 'pattern'; tfItem.value = null; tfResult.value = null; tfAnswers.value = {}
}

// ── 关4:练同型句(接迁移探针:同结构新句 + 理解检测,判分复用 submitComprehension)──
const t4 = ref<'pattern' | 'loading' | 'quiz' | 'none' | 'result'>('pattern')
const tfItem = ref<TransferItem | null>(null)
const tfProbes = ref<ComprehensionProbe[]>([])
const tfShared = ref<string[]>([])
const tfAnswers = ref<Record<string, string>>({})
const tfResult = ref<any>(null)
const tfSubmitting = ref(false)
const allTfAnswered = computed(() => tfProbes.value.length > 0 && tfProbes.value.every(p => !!tfAnswers.value[p.key]))
async function startTransfer() {
  t4.value = 'loading'; tfResult.value = null; tfAnswers.value = {}
  try {
    const r = await getTransferForText(props.text || '', tfItem.value ? [tfItem.value.id] : [])
    if (!r.item) { t4.value = 'none'; return }
    tfItem.value = r.item; tfProbes.value = r.probes || []; tfShared.value = r.shared || []
    t4.value = 'quiz'
  } catch (e: any) { t4.value = 'pattern'; uni.showToast({ title: e?.message || '取同型句失败', icon: 'none' }) }
}
function pickTf(key: string, o: string) { tfAnswers.value = { ...tfAnswers.value, [key]: o } }
async function submitTf() {
  if (!allTfAnswered.value || tfSubmitting.value || !tfItem.value) return
  tfSubmitting.value = true
  try { tfResult.value = await submitComprehension(tfItem.value.id, tfAnswers.value); t4.value = 'result' }
  catch (e: any) { uni.showToast({ title: e?.message || '判分失败', icon: 'none' }) }
  finally { tfSubmitting.value = false }
}

function shortType(t: string): string { return (t || '成分').replace(/（.*?）|\(.*?\)/g, '').trim() }
function uniq(arr: string[]): string[] { return [...new Set(arr.filter(Boolean))] }
</script>

<style scoped>
.si { }
.si-fallback { text-align: center; color: var(--c-text-hint); font-size: 25rpx; padding: 50rpx 24rpx; line-height: 1.6; }
/* 闯关路径 */
.path { display: flex; align-items: flex-start; justify-content: space-between; margin: 6rpx 8rpx 26rpx; }
.node { display: flex; flex-direction: column; align-items: center; gap: 8rpx; flex: none; width: 96rpx; }
.dotc { width: 46rpx; height: 46rpx; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 24rpx; font-weight: 800; }
.dotc.done { background: #2fa98a; color: #fff; }
.dotc.now { background: #3d8bf5; color: #fff; }
.dotc.lock { background: #eef1f6; color: #b7c2d4; }
.nl { font-size: 20rpx; color: #8a95a5; text-align: center; }
.nl.a { color: #2f74d6; font-weight: 700; }
.seg-line { flex: 1; height: 4rpx; background: #e6eaf0; margin-top: 22rpx; }
.seg-line.done { background: #9fddc9; }
/* 关卡 */
.stage { }
.stitle { display: flex; align-items: center; gap: 10rpx; font-size: 27rpx; font-weight: 700; color: var(--c-ink); margin-bottom: 18rpx; line-height: 1.5; }
.snum { width: 38rpx; height: 38rpx; border-radius: 50%; background: #eaf2fe; color: #2f74d6; font-size: 22rpx; display: flex; align-items: center; justify-content: center; flex: none; }
.q-sent { font-size: 30rpx; line-height: 2; color: var(--c-ink); }
.tk { border-radius: 6rpx; padding: 2rpx 4rpx; }
.tk.pick { background: #e6f1fb; color: #185fa5; box-shadow: inset 0 -4rpx 0 #3d8bf5; }
.tk.done { background: #eaf4fb; color: #185fa5; }
.hint { display: block; font-size: 23rpx; color: #93a0b3; margin-top: 18rpx; line-height: 1.6; }
.ok { margin-top: 16rpx; }
.ok text { font-size: 24rpx; color: #1a9059; font-weight: 600; }
.core-box { background: #f4f9ff; border: 2rpx solid #d7e6fb; border-radius: 16rpx; padding: 8rpx 20rpx; }
.core-row { display: flex; align-items: baseline; gap: 16rpx; padding: 14rpx 0; border-bottom: 2rpx solid #e8f0fb; }
.core-row:last-child { border-bottom: none; }
.core-role { font-size: 21rpx; color: #2f74d6; font-weight: 700; flex: none; min-width: 96rpx; }
.core-en { font-size: 28rpx; color: #185fa5; font-weight: 600; }
/* 关3 微测 */
.qbox { border: 3rpx solid #bcd9fb; background: #f4f9ff; border-radius: 16rpx; padding: 20rpx; }
.qbox.lv-1 { border-color: #a9dcc4; background: #f1faf5; }
.qh { display: block; font-size: 21rpx; color: #2f74d6; font-weight: 700; margin-bottom: 10rpx; }
.lv-1 .qh { color: #178a56; }
.qs { display: block; font-size: 29rpx; color: var(--c-ink); line-height: 1.6; }
.q-ask { display: block; font-size: 25rpx; color: #55607a; margin: 14rpx 0 10rpx; }
.opt { font-size: 27rpx; color: #46506a; border: 2rpx solid #dfe4ec; border-radius: 12rpx; padding: 16rpx 20rpx; margin-top: 10rpx; background: #fff; }
.opt.opt-ok { background: #e8f6ef; border-color: #2fa98a; color: #178a56; font-weight: 600; }
.opt.opt-no { background: #fdecec; border-color: #e35b5b; color: #c33; }
.opt.opt-dim { opacity: .5; }
.mfeed { margin-top: 14rpx; }
.mfeed-r { font-size: 24rpx; color: #c33; font-weight: 700; }
.mfeed-r.ok { color: #178a56; }
.mfeed-a { display: block; font-size: 23rpx; color: #7a8698; margin-top: 6rpx; }
.mfeed-next { display: block; text-align: center; margin-top: 14rpx; color: #2f74d6; font-size: 26rpx; font-weight: 700; }
/* 关4 句型 */
.patc { background: #f4f9ff; border: 2rpx solid #d7e6fb; border-radius: 16rpx; padding: 18rpx 20rpx; line-height: 2; }
.pp { font-size: 25rpx; color: #7a8698; }
.pp.core { color: #2f74d6; font-weight: 700; }
.pp-plus { color: #b7c2d4; }
.mig { margin-top: 18rpx; text-align: center; font-size: 28rpx; font-weight: 700; color: #fff; background: #3d8bf5; border-radius: 14rpx; padding: 20rpx 0; }
.mig.ghost { background: #f2f4f7; color: #5b677a; }
/* 关4 练同型句 */
.tp-tip { text-align: center; color: #93a0b3; font-size: 25rpx; padding: 30rpx 0; }
.tf-sent { margin-top: 16rpx; background: #f6f8fc; border-radius: 14rpx; padding: 16rpx; }
.tf-lb { display: block; font-size: 20rpx; color: #93a0b3; margin-bottom: 6rpx; }
.tf-text { font-size: 29rpx; line-height: 1.7; color: var(--c-ink); }
.tf-shared { display: flex; flex-wrap: wrap; gap: 8rpx; margin-top: 12rpx; }
.tf-chip { font-size: 20rpx; color: #2f74d6; background: #eaf2fe; border-radius: 999rpx; padding: 4rpx 14rpx; }
.tf-probe { margin-top: 16rpx; }
.tf-q { display: block; font-size: 26rpx; color: var(--c-ink); font-weight: 600; margin-bottom: 8rpx; line-height: 1.5; }
.opt.opt-sel { background: #eaf4fb; border-color: #7bbde8; color: #185fa5; }
.tf-res { margin-top: 16rpx; border-radius: 14rpx; padding: 16rpx; background: #fdecec; }
.tf-res.ok { background: #eef8f3; }
.tf-res-t { font-size: 26rpx; font-weight: 700; color: #c33; line-height: 1.6; }
.tf-res.ok .tf-res-t { color: #178a56; }
.tf-pr { font-size: 23rpx; color: #7a8698; margin-top: 8rpx; }
.tf-pr.ok { color: #178a56; }
.tf-btns { display: flex; gap: 16rpx; }
.tf-btns .mig { flex: 1; }
/* 导航 */
.nav { display: flex; gap: 16rpx; margin-top: 24rpx; }
.nav-btn { flex: 1; text-align: center; font-size: 27rpx; font-weight: 700; border-radius: 14rpx; padding: 20rpx 0; border: 2rpx solid #dfe4ec; color: #5b677a; }
.nav-btn.primary { background: #3d8bf5; color: #fff; border-color: #3d8bf5; }
.nav-btn.dis { opacity: .4; }
</style>
