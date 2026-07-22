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

      <!-- 关1:找主干(按次序点成分 · 分色下划线 · 记正确率)-->
      <view v-if="stage === 0" class="stage">
        <view class="stitle"><text class="snum">1</text>先找主干:按提示<text class="em">依次</text>点出成分</view>
        <!-- 步骤条:按次序识别成分 -->
        <view class="cstep">
          <block v-for="(t, i) in coreTargets" :key="i">
            <view class="cs">
              <text class="cs-d" :class="{ done: i < curStep, cur: i === curStep && !corePassed }"
                :style="i < curStep ? { background: compColor(t.seg.type) } : {}">{{ i < curStep ? '✓' : i + 1 }}</text>
              <text class="cs-l" :style="{ color: i <= curStep ? compColor(t.seg.type) : '' }">{{ t.role }}</text>
            </view>
            <view v-if="i < coreTargets.length - 1" class="cs-line" />
          </block>
        </view>
        <view v-if="!corePassed" class="cprompt">第 {{ curStep + 1 }} 步 · 点出主句的「<text class="cp-role" :style="{ color: compColor(curTarget && curTarget.seg.type || '') }">{{ curTarget && curTarget.role }}</text>」</view>
        <!-- 句子 token:点对=该成分色下划线+✓,点错闪红 -->
        <view class="q-sent">
          <text v-for="(s, i) in segList" :key="i" class="tk"
            :class="{ found: !!foundColor[idxOf(s)], wrong: wrongIdx === idxOf(s), done: corePassed }"
            :style="foundColor[idxOf(s)] ? { color: foundColor[idxOf(s)] } : {}"
            @tap="tapCore(s)">{{ s.text }}<text v-if="foundColor[idxOf(s)]" class="tk-chk">✓</text> </text>
        </view>
        <!-- 图例 + 选中正确率 -->
        <view class="cfoot">
          <view class="clegend">
            <text v-for="(t, i) in coreTargets" :key="i" class="clg"><text class="clgc" :style="{ background: compColor(t.seg.type) }" />{{ t.role }}</text>
          </view>
          <view class="crate"><text class="crate-n">{{ coreAccuracy }}%</text><text class="crate-l">选中正确率 {{ coreCorrect }}/{{ coreCorrect + coreWrong }}</text></view>
        </view>
        <view v-if="corePassed" class="ok"><text>✓ 主干找齐了!主干 = {{ coreTargets.map(t => t.role).join(' + ') }},先抓它。</text></view>
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

      <!-- 关3:拆修饰(按次序点修饰成分 · 分色下划线 · 记正确率,先状语后定语)-->
      <view v-else-if="stage === 2" class="stage">
        <view class="stitle"><text class="snum">3</text>拆修饰:按提示<text class="em">依次</text>点出修饰成分(先状语后定语)</view>
        <!-- 步骤条:逐层 -->
        <view class="cstep">
          <block v-for="(m, i) in mods" :key="i">
            <view class="cs">
              <text class="cs-d" :class="{ done: i < modStep, cur: i === modStep && !modsPassed }"
                :style="i < modStep ? { background: compColor(m.type) } : {}">{{ i < modStep ? '✓' : i + 1 }}</text>
            </view>
            <view v-if="i < mods.length - 1" class="cs-line" />
          </block>
        </view>
        <view v-if="!modsPassed && curModT" class="cprompt">第 {{ modStep + 1 }} 层 · 点出「<text class="cp-role" :style="{ color: compColor(curModT.type) }">{{ shortType(curModT.type) }}</text>」<text class="cp-hint"> · {{ curModT.grpLabel }}</text></view>
        <view class="q-sent">
          <text v-for="(s, i) in segList" :key="i" class="tk"
            :class="{ found: !!modFound[idxOf(s)], wrong: modWrong === idxOf(s), done: modsPassed }"
            :style="modFound[idxOf(s)] ? { color: modFound[idxOf(s)] } : {}"
            @tap="tapMod2(s)">{{ s.text }}<text v-if="modFound[idxOf(s)]" class="tk-chk">✓</text> </text>
        </view>
        <view class="cfoot">
          <view class="clegend">
            <text v-for="(l, i) in modLegend" :key="i" class="clg"><text class="clgc" :style="{ background: l.color }" />{{ l.label }}</text>
          </view>
          <view class="crate"><text class="crate-n">{{ modAccuracy }}%</text><text class="crate-l">选中正确率 {{ modHit }}/{{ modHit + modMiss }}</text></view>
        </view>
        <view v-if="modsPassed" class="ok"><text>✓ 修饰全拆开了!主干 + 各层修饰 = 完整长句。</text></view>
      </view>

      <!-- 关4:合成长句(主干起手,逐层插修饰 · 插对→被修饰成分打✓ · 记归位正确率) -->
      <view v-else class="stage">
        <view class="stitle"><text class="snum">4</text>合成长句:主干 + 逐层修饰</view>
        <view v-if="asmMods.length === 0" class="hint">本句无额外修饰,主干即整句。</view>
        <template v-else>
          <view class="prog2">已加 {{ asmStep }} / {{ asmMods.length }} 层修饰 · 插对一层,它说明的成分打 ✓</view>
          <!-- 当前句:主干 + 已插修饰 + ＋槽 -->
          <view class="asm-zone" :class="{ done: asmPassed }">
            <text class="zlb2" :class="{ ok: asmPassed }">{{ asmPassed ? '✓ 完整长句' : '当前句' }}</text>
            <view class="asm-sent">
              <block v-for="(seg, k) in placedSegs" :key="seg.__idx">
                <text v-if="!asmPassed" class="ins2" :class="{ wrong: asmWrongSlot === k }" @tap="tapSlot(k)">＋</text>
                <text class="asm-w" :class="{ chk: checked[seg.__idx] }" :style="{ color: compColor(seg.type) }">{{ seg.text }}<text v-if="checked[seg.__idx]" class="asm-ck">✓</text> </text>
              </block>
              <text v-if="!asmPassed" class="ins2" :class="{ wrong: asmWrongSlot === placedSegs.length }" @tap="tapSlot(placedSegs.length)">＋</text>
            </view>
          </view>
          <template v-if="!asmPassed">
            <view class="cprompt">把「<text class="cp-role" :style="{ color: compColor(asmCur && asmCur.type || '') }">{{ asmCur && shortType(asmCur.type) }}</text>」插到正确 ＋ 处 —— 它说明谁,谁就打 ✓</view>
            <view class="pool2"><text class="zlb2">待放修饰</text><text class="asm-chip" :style="{ color: compColor(asmCur && asmCur.type || ''), 'border-color': compColor(asmCur && asmCur.type || '') }">{{ asmCur && asmCur.text }}</text></view>
          </template>
          <view class="cfoot">
            <view class="clegend"><text v-for="(l, i) in coreLegend" :key="i" class="clg"><text class="clgc" :style="{ background: l.color }" />{{ l.label }}</text></view>
            <view class="crate"><text class="crate-n">{{ asmAccuracy }}%</text><text class="crate-l">归位正确率 {{ asmHit }}/{{ asmHit + asmMiss }}</text></view>
          </view>
          <view v-if="asmPassed" class="ok"><text>✓ 主干 + 各层修饰 = 这句长句。下次遇同型能拆能装。</text></view>
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
import { recordIntensiveCore, recordComponentError } from '@/api/longSentence'

const props = defineProps<{ a: any; text?: string }>()

const stages = ['找主干', '读主干', '拆修饰', '合成长句']
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
// 主干 = 主谓宾表(按成分类型判,不依赖 parent 树);parent 树只用于「被修饰成分打勾」。
// (依存树里 宾语/表语 parent=谓语,若按 parent===null 会掉出主干,故按类型判)
function isCoreSeg(s: any): boolean {
  return /主语|谓语|宾语|表语|主句|主干/.test(s.type || '')
}
const cores = computed(() => segList.value.filter(isCoreSeg))
const comps = computed(() => props.a?.components || {})
const dataOk = computed(() =>
  segList.value.length > 0 && (cores.value.length > 0 || comps.value.subject || comps.value.predicate))

// ── 关1:按次序点主干成分(主语→谓语→[宾/表])· 分色下划线 · 记正确率 ──
function compColor(type: string): string {
  const t = type || ''
  if (/主语/.test(t)) return '#2fa98a'
  if (/谓语/.test(t)) return '#3d8bf5'
  if (/宾语/.test(t)) return '#c77d2e'
  if (/表语/.test(t)) return '#d98a3a'
  if (/定语/.test(t)) return '#7a5cd0'   // 定语/定语从句 紫
  if (/状语/.test(t)) return '#e0863a'   // 状语 橙
  if (/同位/.test(t)) return '#d17ba8'   // 同位语 品红
  if (/从句|非谓语|插入|补语/.test(t)) return '#5a9e6f'   // 其它修饰/从句 绿
  return '#8a94a6'
}
// 主干目标成分:按语法序 主→谓→宾/表,仅取本句存在的(去重)
const coreTargets = computed<any[]>(() => {
  const out: any[] = []
  for (const role of ['主语', '谓语', '宾语', '表语']) {
    const seg = cores.value.find(s => new RegExp(role).test(s.type || ''))
    if (seg && !out.some(o => o.seg.__idx === seg.__idx)) out.push({ seg, role })
  }
  return out
})
const curStep = ref(0)
const foundColor = ref<Record<number, string>>({})   // __idx → 成分色(已点对)
const wrongIdx = ref<number | null>(null)             // 刚点错的段(闪红)
const coreCorrect = ref(0)
const coreWrong = ref(0)
const corePassedRaw = ref(false)
const corePassed = computed(() => corePassedRaw.value || coreTargets.value.length === 0)
const curTarget = computed(() => coreTargets.value[curStep.value] || null)
const coreAccuracy = computed(() => {
  const t = coreCorrect.value + coreWrong.value
  return t ? Math.round((coreCorrect.value / t) * 100) : 100
})
// 方案B·句子成分理解:每次细分对错回传 (句,技能,角色);fire-and-forget 不阻塞
function recComp(skill: 'trunk' | 'modifier' | 'relation', role: string, correct: boolean) {
  if (!props.text || !role) return
  recordComponentError(props.text, skill, role, correct).catch(() => { /* 静默 */ })
}
function tapCore(s: any) {
  if (corePassed.value || foundColor.value[s.__idx]) return
  const tgt = curTarget.value
  if (!tgt) return
  if (s.__idx === tgt.seg.__idx) {   // 点对当前目标成分 → 分色下划线 + 进下一步
    foundColor.value = { ...foundColor.value, [s.__idx]: compColor(tgt.seg.type) }
    coreCorrect.value++
    recComp('trunk', shortType(tgt.seg.type), true)
    wrongIdx.value = null
    curStep.value++
    if (curStep.value >= coreTargets.value.length) { corePassedRaw.value = true; recordCore() }
  } else {   // 点错 → 计一次错、闪红、可继续
    coreWrong.value++
    recComp('trunk', shortType(tgt.seg.type), false)
    wrongIdx.value = s.__idx
    setTimeout(() => { if (wrongIdx.value === s.__idx) wrongIdx.value = null }, 600)
  }
}
async function recordCore() {   // 选中正确率回传;全对推进、有错反哺「长难句薄弱·成分维」
  if (!props.text) return
  try { await recordIntensiveCore(props.text, coreWrong.value === 0) } catch { /* 静默 */ }
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
// ── 关3:按次序点修饰成分(先状语后定语)· 分色下划线 · 记正确率(同关1机制)──
const modStep = ref(0)
const modFound = ref<Record<number, string>>({})   // __idx → 成分色(已点对)
const modWrong = ref<number | null>(null)           // 刚点错(闪红)
const modHit = ref(0)
const modMiss = ref(0)
const modsPassedRaw = ref(false)
const modsPassed = computed(() => modsPassedRaw.value || mods.value.length === 0)
const curModT = computed(() => mods.value[modStep.value] || null)
const modAccuracy = computed(() => {
  const t = modHit.value + modMiss.value
  return t ? Math.round((modHit.value / t) * 100) : 100
})
const modLegend = computed(() => {
  const seen = new Map<string, string>()
  mods.value.forEach(m => { const l = shortType(m.type); if (l && !seen.has(l)) seen.set(l, compColor(m.type)) })
  return [...seen].map(([label, color]) => ({ label, color }))
})
function tapMod2(s: any) {
  if (modsPassed.value || modFound.value[s.__idx]) return
  const tgt = curModT.value
  if (!tgt) return
  if (s.__idx === tgt.__idx) {   // 点对当前层修饰成分 → 分色下划线 + 进下一层
    modFound.value = { ...modFound.value, [s.__idx]: compColor(tgt.type) }
    recComp('modifier', shortType(tgt.type), true)
    modHit.value++; modWrong.value = null; modStep.value++
    if (modStep.value >= mods.value.length) { modsPassedRaw.value = true; recordMods() }
  } else {   // 点错 → 计一次错、闪红、可继续
    recComp('modifier', shortType(tgt.type), false)
    modMiss.value++; modWrong.value = s.__idx
    setTimeout(() => { if (modWrong.value === s.__idx) modWrong.value = null }, 600)
  }
}
async function recordMods() {   // 拆修饰也归「成分」维:全对推进、有错反哺长难句薄弱·成分维
  if (!props.text) return
  try { await recordIntensiveCore(props.text, modMiss.value === 0) } catch { /* 静默 */ }
}

// ── 关4:合成长句(主干起手,逐层插修饰 · 插对→被修饰成分打✓ · 记归位正确率)──
const asmMods = computed<any[]>(() => mods.value)   // 修饰序列(状语→定语,同关3)
const asmStep = ref(0)
const placed = ref<number[]>([])                     // 已在句中的 seg __idx(初始=主干按原文序)
const checked = ref<Record<number, boolean>>({})     // 被修饰成分打勾(用 structure.parent)
const asmHit = ref(0)
const asmMiss = ref(0)
const asmWrongSlot = ref<number | null>(null)
const asmPassedRaw = ref(false)
const asmPassed = computed(() => asmPassedRaw.value || asmMods.value.length === 0)
const asmCur = computed(() => asmMods.value[asmStep.value] || null)
const placedSegs = computed<any[]>(() => placed.value.map(i => byIdx.value[i]).filter(Boolean))
const asmAccuracy = computed(() => {
  const t = asmHit.value + asmMiss.value
  return t ? Math.round((asmHit.value / t) * 100) : 100
})
const coreLegend = computed(() => {
  const seen = new Map<string, string>()
  segList.value.forEach(s => { const l = shortType(s.type); if (l && !seen.has(l)) seen.set(l, compColor(s.type)) })
  return [...seen].map(([label, color]) => ({ label, color }))
})
function initAsm() {   // 主干起手:按原文序排好主干成分
  placed.value = cores.value.map(c => c.__idx).sort((a, b) => a - b)
  asmStep.value = 0; checked.value = {}; asmHit.value = 0; asmMiss.value = 0
  asmWrongSlot.value = null; asmPassedRaw.value = false
}
// 当前修饰的正确槽 = 已放成分里 idx 小于它的个数(插入后仍按原文序)
const asmCorrectSlot = computed(() => {
  const m = asmCur.value; if (!m) return -1
  return placed.value.filter(i => i < m.__idx).length
})
function tapSlot(k: number) {
  if (asmPassed.value) return
  const m = asmCur.value; if (!m) return
  if (k === asmCorrectSlot.value) {   // 插对 → 入句 + 被修饰成分打✓
    const arr = [...placed.value]; arr.splice(k, 0, m.__idx); placed.value = arr
    const p = parentOf.value[m.__idx]
    if (p != null && byIdx.value[p]) checked.value = { ...checked.value, [p]: true }
    recComp('relation', shortType(m.type), true)
    asmHit.value++; asmWrongSlot.value = null; asmStep.value++
    if (asmStep.value >= asmMods.value.length) { asmPassedRaw.value = true; recordAsm() }
  } else {   // 点错 → 计一次错、闪红、可继续
    recComp('relation', shortType(m.type), false)
    asmMiss.value++; asmWrongSlot.value = k
    setTimeout(() => { if (asmWrongSlot.value === k) asmWrongSlot.value = null }, 600)
  }
}
async function recordAsm() {   // 合成归「成分」维:全对推进、有错反哺长难句薄弱·成分维
  if (!props.text) return
  try { await recordIntensiveCore(props.text, asmMiss.value === 0) } catch { /* 静默 */ }
}

// ── 关卡推进 ──
const canNext = computed(() => {
  if (stage.value === 0) return corePassed.value
  if (stage.value === 2) return modsPassed.value
  return true   // 关4 为末关,按钮=「重来」,始终可点
})
function next() {
  if (stage.value >= stages.length - 1) { reset(); return }
  if (!canNext.value) return
  stage.value += 1
  if (stage.value === 3 && placed.value.length === 0) initAsm()   // 进关4 → 主干起手
}
function prev() { if (stage.value > 0) stage.value -= 1 }
function reset() {
  stage.value = 0
  curStep.value = 0; foundColor.value = {}; wrongIdx.value = null
  coreCorrect.value = 0; coreWrong.value = 0; corePassedRaw.value = false
  modStep.value = 0; modFound.value = {}; modWrong.value = null
  modHit.value = 0; modMiss.value = 0; modsPassedRaw.value = false
  asmStep.value = 0; placed.value = []; checked.value = {}
  asmHit.value = 0; asmMiss.value = 0; asmWrongSlot.value = null; asmPassedRaw.value = false
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
.q-sent { font-size: 30rpx; line-height: 2.2; color: var(--c-ink); }
.tk { border-radius: 6rpx; padding: 2rpx 4rpx 4rpx; }
.tk.found { border-bottom: 5rpx solid; border-radius: 6rpx 6rpx 0 0; font-weight: 600; }
.tk.wrong { background: #fdecec; color: #d9573f; }
.tk.done { opacity: 0.92; }
.tk-chk { font-size: 18rpx; vertical-align: super; margin-left: 2rpx; }
.stitle .em { color: #3d8bf5; }
/* 步骤条(按次序识别成分) */
.cstep { display: flex; align-items: center; gap: 6rpx; margin-bottom: 16rpx; }
.cs { display: flex; align-items: center; gap: 8rpx; }
.cs-d { width: 40rpx; height: 40rpx; border-radius: 50%; background: #cfd6df; color: #fff; font-size: 22rpx; font-weight: 800; display: flex; align-items: center; justify-content: center; flex: none; }
.cs-d.cur { box-shadow: 0 0 0 6rpx #d5e6fb; }
.cs-l { font-size: 24rpx; font-weight: 700; color: #93a0b3; }
.cs-line { flex: 1; height: 3rpx; background: #e0e5ec; }
.cprompt { font-size: 27rpx; font-weight: 700; color: var(--c-ink); margin-bottom: 16rpx; }
.cp-role { font-weight: 800; }
.cp-hint { font-size: 22rpx; font-weight: 400; color: #93a0b3; }
/* 图例 + 正确率 */
.cfoot { display: flex; align-items: flex-end; justify-content: space-between; margin-top: 22rpx; padding-top: 16rpx; border-top: 2rpx solid #eef1f5; }
.clegend { display: flex; flex-wrap: wrap; gap: 16rpx; }
.clg { display: flex; align-items: center; gap: 8rpx; font-size: 21rpx; color: #6b7684; }
.clgc { width: 26rpx; height: 6rpx; border-radius: 3rpx; }
.crate { text-align: right; flex: none; }
.crate-n { display: block; font-size: 34rpx; font-weight: 900; color: #2fa98a; line-height: 1; }
.crate-l { font-size: 19rpx; color: #93a0b3; }
/* 关4 合成长句 */
.prog2 { font-size: 21rpx; color: #93a0b3; margin-bottom: 14rpx; }
.asm-zone { background: #fff; border: 2rpx dashed #cfd8e3; border-radius: 16rpx; padding: 20rpx 18rpx; margin-bottom: 16rpx; }
.asm-zone.done { border-style: solid; border-color: #bfe5d6; background: #f4fbf8; }
.zlb2 { display: block; font-size: 20rpx; color: #93a0b3; font-weight: 700; margin-bottom: 14rpx; }
.zlb2.ok { color: #2fa98a; }
.asm-sent { font-size: 30rpx; line-height: 2.6; }
.asm-w { font-weight: 600; padding: 2rpx 4rpx; }
.asm-w.chk { border-bottom: 4rpx solid currentColor; border-radius: 6rpx 6rpx 0 0; }
.asm-ck { font-size: 20rpx; font-weight: 900; color: #2fa98a; vertical-align: super; margin-left: 2rpx; }
.ins2 { display: inline-flex; align-items: center; justify-content: center; min-width: 56rpx; height: 52rpx; padding: 0 12rpx; border-radius: 26rpx; border: 3rpx dashed #e0863a; color: #e0863a; font-size: 24rpx; margin: 0 6rpx; vertical-align: middle; }
.ins2.wrong { background: #fdecec; border-color: #d9573f; color: #d9573f; }
.pool2 { background: #f6f8fb; border-radius: 16rpx; padding: 18rpx; margin-bottom: 4rpx; }
.asm-chip { display: inline-block; margin-top: 10rpx; border: 3rpx solid; border-radius: 12rpx; padding: 12rpx 16rpx; font-size: 26rpx; font-weight: 600; line-height: 1.5; }
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
