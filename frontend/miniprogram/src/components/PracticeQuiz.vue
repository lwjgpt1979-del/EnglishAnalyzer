<!-- 多题练习·逐题作答判分(全项目练习作答统一组件;支持 选择/判断/填空) -->
<template>
  <view class="modal" @tap="close">
    <view class="modal-card" @tap.stop>
      <view class="modal-head">
        <text class="modal-title">{{ kp ? '同类练习 · ' + kp : '练习' }}</text>
        <view class="modal-x" @tap.stop="close"><text>✕</text></view>
      </view>

      <!-- 答题阶段 -->
      <block v-if="!done && cur">
        <view class="pr-top">
          <text class="pr-idx">第 {{ idx + 1 }} / {{ questions.length }} 题</text>
          <view class="pr-dots">
            <view v-for="(q, i) in questions" :key="i" class="pr-dot" :class="dotCls(q, i)" />
          </view>
        </view>
        <scroll-view scroll-y class="modal-body">
          <text class="pq-stem">{{ cur.stem }}</text>

          <!-- 选择/判断:点选 -->
          <view v-if="hasOptions(cur)" class="pq-opts">
            <view
              v-for="(v, oi) in cur.options"
              :key="oi"
              class="pq-opt"
              :class="optCls(cur, oi)"
              @tap.stop="pick(cur, oi)"
            >
              <text v-if="!isJudge(cur)" class="opt-badge">{{ letter(oi) }}</text>
              <text class="opt-txt">{{ optText(v) }}</text>
            </view>
          </view>
          <!-- 填空:文本输入 -->
          <view v-else class="pq-fill">
            <input
              class="pq-input"
              :value="fillInput"
              :disabled="!!state[cur.id]"
              placeholder="请输入答案"
              @input="fillInput = $event.detail.value"
              @confirm="submitFill(cur)"
            />
          </view>

          <view v-if="state[cur.id]" class="pq-fb">
            <text :class="state[cur.id].correct ? 'fb-ok' : 'fb-no'">
              {{ state[cur.id].correct ? '✓ 答对' : '✗ 答错，正确：' + fbAnswer(cur) }}
            </text>
            <text v-if="state[cur.id].explanation" class="pq-expl">{{ state[cur.id].explanation }}</text>
          </view>
          <view v-else-if="judging" class="pq-judging">判分中…</view>
        </scroll-view>

        <view class="modal-actions">
          <!-- 填空未答:提交按钮 -->
          <view
            v-if="!hasOptions(cur) && !state[cur.id]"
            class="modal-btn primary"
            :class="{ disabled: !fillInput.trim() || judging }"
            @tap.stop="submitFill(cur)"
          ><text>{{ judging ? '判分中…' : '提交答案' }}</text></view>
          <!-- 已答/选择题:下一题 -->
          <view
            v-else
            class="modal-btn primary"
            :class="{ disabled: !state[cur.id] || saving }"
            @tap.stop="next"
          ><text>{{ isLast ? (saving ? '结算中…' : lastLabel) : '下一题 →' }}</text></view>
        </view>
      </block>

      <!-- 结果阶段(hideResult 时由页面自渲染) -->
      <block v-else-if="done">
        <view class="pr-result">
          <text class="pr-score">{{ correctCount }}/{{ questions.length }}</text>
          <text class="pr-msg">{{ resultMsg }}</text>
        </view>
        <view class="modal-actions">
          <view class="modal-btn ghost" @tap.stop="close"><text>完成</text></view>
        </view>
      </block>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { PracticeQuestion } from '@/api/wrongQuestions'

type JudgeResult = { correct: boolean; correct_answer: string; explanation?: string }
export type ChosenAnswer = { index: number; letter: string; text: string; input: string }
const props = defineProps<{
  kp: string
  questions: PracticeQuestion[]
  recorder?: (total: number, correct: number) => Promise<string>
  // 服务端判分钩子:传则每题走它(题不含答案的练习/自适应);不传则本地按 q.answer 判。
  judge?: (q: PracticeQuestion, ans: ChosenAnswer) => Promise<JudgeResult>
  // 页面自渲染结果页(如自适应按考点统计):做完 emit finish + close,不显组件内结果页。
  hideResult?: boolean
  lastLabel?: string
}>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'finish', total: number, correct: number): void }>()

interface St { pickedIdx: number; correct: boolean; correctIdx: number; correctText: string; explanation: string }
const idx = ref(0)
const done = ref(false)
const saving = ref(false)
const judging = ref(false)
const recorded = ref(false)
const resultMsg = ref('')
const fillInput = ref('')
const state = reactive<Record<string, St>>({})

const cur = computed<PracticeQuestion | undefined>(() => props.questions[idx.value])
const isLast = computed(() => idx.value >= props.questions.length - 1)
const answeredCount = computed(() => Object.keys(state).length)
const correctCount = computed(() => Object.values(state).filter(s => s.correct).length)
const lastLabel = computed(() => props.lastLabel || '查看结果')
const letter = (i: number) => String.fromCharCode(65 + i)
watch(idx, () => { fillInput.value = '' })

function hasOptions(q: PracticeQuestion): boolean { return !!(q.options && q.options.length) }
function isJudge(q: PracticeQuestion): boolean {
  return !!(q.options && q.options.length === 2 && q.options.every(o => o === '对' || o === '错'))
}
function optText(v: string): string {
  return (v || '').replace(/^\s*[A-Da-d][.、)]\s*/, '')
}
function answerToIdx(ans: string, q: PracticeQuestion): number {
  const a = (ans || '').trim()
  if (!a || !q.options) return -1
  const byLetter = a.toUpperCase().charCodeAt(0) - 65
  if (a.length === 1 && byLetter >= 0 && byLetter < q.options.length) return byLetter
  return q.options.findIndex(o => optText(o).trim() === a || (o || '').trim() === a)
}
function apply(q: PracticeQuestion, pickedIdx: number, r: JudgeResult) {
  state[q.id] = { pickedIdx, correct: r.correct, correctIdx: answerToIdx(r.correct_answer, q),
                  correctText: r.correct_answer, explanation: r.explanation || '' }
}
async function pick(q: PracticeQuestion, oi: number) {
  if (state[q.id] || judging.value) return
  const ans: ChosenAnswer = { index: oi, letter: letter(oi), text: optText(q.options![oi]), input: '' }
  if (props.judge) {
    judging.value = true
    try { apply(q, oi, await props.judge(q, ans)) }
    catch (e: any) { uni.showToast({ title: e?.message || '判分失败', icon: 'none' }) }
    finally { judging.value = false }
  } else {
    const ci = answerToIdx(q.answer || '', q)
    apply(q, oi, { correct: ci === oi, correct_answer: q.answer || '', explanation: q.explanation || '' })
  }
}
async function submitFill(q: PracticeQuestion) {
  if (state[q.id] || judging.value) return
  const input = fillInput.value.trim()
  if (!input) return
  const ans: ChosenAnswer = { index: -1, letter: '', text: input, input }
  if (props.judge) {
    judging.value = true
    try { apply(q, -1, await props.judge(q, ans)) }
    catch (e: any) { uni.showToast({ title: e?.message || '判分失败', icon: 'none' }) }
    finally { judging.value = false }
  } else {
    const correct = (q.answer || '').trim().toLowerCase() === input.toLowerCase()
    apply(q, -1, { correct, correct_answer: q.answer || '', explanation: q.explanation || '' })
  }
}
function optCls(q: PracticeQuestion, oi: number): string {
  const st = state[q.id]
  if (!st) return ''
  if (oi === st.correctIdx) return 'opt-correct'
  if (oi === st.pickedIdx) return 'opt-wrong'
  return 'opt-dim'
}
function fbAnswer(q: PracticeQuestion): string {
  const st = state[q.id]
  if (st && st.correctIdx >= 0 && q.options) return optText(q.options[st.correctIdx])
  return st ? st.correctText : ''
}
function dotCls(q: PracticeQuestion, i: number): string {
  if (i === idx.value) return 'cur'
  const st = state[q.id]
  if (!st) return ''
  return st.correct ? 'ok' : 'no'
}
async function doRecord() {
  if (recorded.value || saving.value || answeredCount.value === 0) return
  saving.value = true
  try {
    resultMsg.value = props.recorder
      ? await props.recorder(answeredCount.value, correctCount.value)
      : `本轮 ${correctCount.value}/${answeredCount.value} 正确`
    recorded.value = true
  } catch (e: any) {
    uni.showToast({ title: e?.message || '结算失败', icon: 'none' })
  } finally { saving.value = false }
}
async function next() {
  if (!cur.value || !state[cur.value.id]) return
  if (!isLast.value) { idx.value += 1; return }
  if (props.hideResult) { emit('finish', answeredCount.value, correctCount.value); emit('close'); return }
  await doRecord()
  emit('finish', answeredCount.value, correctCount.value)
  done.value = true
}
async function close() {
  if (!props.hideResult && answeredCount.value > 0 && !recorded.value) await doRecord()
  emit('close')
}
</script>

<style scoped>
.modal { position: fixed; inset: 0; background: rgba(0,0,0,.45); display: flex; align-items: center; justify-content: center; z-index: 100; padding: 40rpx; }
.modal-card { width: 100%; max-width: 640rpx; max-height: 80vh; background: #fff; border-radius: 24rpx; padding: 28rpx; box-sizing: border-box; display: flex; flex-direction: column; }
.modal-head { display: flex; align-items: center; justify-content: space-between; gap: 12rpx; }
.modal-title { font-size: 30rpx; font-weight: 800; color: var(--c-ink); }
.modal-x { width: 56rpx; height: 56rpx; display: flex; align-items: center; justify-content: center; font-size: 30rpx; color: var(--c-text-hint); flex-shrink: 0; }
.modal-body { flex: 1; margin: 16rpx 0; }
.pr-top { display: flex; align-items: center; justify-content: space-between; gap: 16rpx; margin-top: 8rpx; }
.pr-idx { font-size: 24rpx; color: var(--c-text-second); font-weight: 600; white-space: nowrap; }
.pr-dots { display: flex; gap: 10rpx; flex-wrap: wrap; }
.pr-dot { width: 18rpx; height: 18rpx; border-radius: 50%; background: #dfe4ea; }
.pr-dot.cur { background: var(--c-primary); transform: scale(1.15); }
.pr-dot.ok { background: #18a058; }
.pr-dot.no { background: #e35b5b; }
.pq-stem { display: block; font-size: 28rpx; line-height: 1.6; color: var(--c-ink); font-weight: 600; }
.pq-opts { display: flex; flex-direction: column; gap: 12rpx; margin-top: 14rpx; }
.pq-opt { display: flex; align-items: center; gap: 14rpx; font-size: 26rpx; color: var(--c-ink); background: var(--c-bg-card); border: 2rpx solid var(--c-border); border-radius: 16rpx; padding: 18rpx 20rpx; line-height: 1.4; }
.opt-badge { flex-shrink: 0; width: 44rpx; height: 44rpx; border-radius: 50%; background: var(--c-bg-soft); color: var(--c-text-second); font-size: 24rpx; font-weight: 700; display: flex; align-items: center; justify-content: center; }
.opt-txt { flex: 1; }
.pq-opt.opt-correct { background: #e6f8ee; border-color: #18a058; color: #128a4c; font-weight: 600; }
.pq-opt.opt-correct .opt-badge { background: #18a058; color: #fff; }
.pq-opt.opt-wrong { background: #fdecec; border-color: #e35b5b; color: #c33; }
.pq-opt.opt-wrong .opt-badge { background: #e35b5b; color: #fff; }
.opt-dim { opacity: 0.5; }
.pq-fill { margin-top: 14rpx; }
.pq-input { height: 84rpx; background: var(--c-bg-card); border: 2rpx solid var(--c-border); border-radius: 16rpx; padding: 0 22rpx; font-size: 28rpx; }
.pq-fb { margin-top: 14rpx; }
.pq-fb .fb-ok { font-size: 24rpx; color: #128a4c; font-weight: 600; }
.pq-fb .fb-no { font-size: 24rpx; color: #c33; font-weight: 600; }
.pq-expl { display: block; margin-top: 8rpx; font-size: 23rpx; color: var(--c-text-second); line-height: 1.6; }
.pq-judging { margin-top: 14rpx; font-size: 24rpx; color: var(--c-text-hint); }
.pr-result { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 60rpx 0; gap: 16rpx; }
.pr-score { font-size: 72rpx; font-weight: 800; color: var(--c-primary); }
.pr-msg { font-size: 27rpx; color: var(--c-text-second); text-align: center; padding: 0 24rpx; line-height: 1.6; }
.modal-actions { display: flex; gap: 16rpx; }
.modal-btn { flex: 1; text-align: center; font-size: 27rpx; font-weight: 700; border-radius: 999rpx; padding: 16rpx; }
.modal-btn.ghost { background: var(--c-bg-soft); color: var(--c-text-second); }
.modal-btn.primary { background: var(--c-primary); color: #fff; }
.modal-btn.disabled { opacity: 0.5; }
</style>
