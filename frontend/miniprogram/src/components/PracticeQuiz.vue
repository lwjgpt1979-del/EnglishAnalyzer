<!-- 练同类·逐题作答判分(我的错题 / 作业详情 共用) -->
<template>
  <view class="modal" @tap="close">
    <view class="modal-card" @tap.stop>
      <view class="modal-head">
        <text class="modal-title">同类练习 · {{ kp }}</text>
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
          <view v-if="cur.options" class="pq-opts">
            <view
              v-for="(v, oi) in cur.options"
              :key="oi"
              class="pq-opt"
              :class="optCls(cur, v)"
              @tap.stop="pick(cur, v)"
            >
              <text class="opt-badge">{{ letter(oi) }}</text>
              <text class="opt-txt">{{ optText(v) }}</text>
            </view>
          </view>
          <view v-if="state[cur.id]" class="pq-fb">
            <text :class="state[cur.id].correct ? 'fb-ok' : 'fb-no'">
              {{ state[cur.id].correct ? '✓ 答对' : '✗ 答错，正确：' + optText(cur.answer || '') }}
            </text>
            <text v-if="cur.explanation" class="pq-expl">{{ cur.explanation }}</text>
          </view>
        </scroll-view>
        <view class="modal-actions">
          <view
            class="modal-btn primary"
            :class="{ disabled: !state[cur.id] || saving }"
            @tap.stop="next"
          ><text>{{ isLast ? (saving ? '结算中…' : '查看结果') : '下一题 →' }}</text></view>
        </view>
      </block>

      <!-- 结果阶段 -->
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
import { computed, reactive, ref } from 'vue'
import type { PracticeQuestion } from '@/api/wrongQuestions'

const props = defineProps<{
  kp: string
  questions: PracticeQuestion[]
  // 结算器:回写成绩并返回结果文案。不传则只本地统计。
  recorder?: (total: number, correct: number) => Promise<string>
}>()
const emit = defineEmits<{ (e: 'close'): void }>()

const idx = ref(0)
const done = ref(false)
const saving = ref(false)
const recorded = ref(false)
const resultMsg = ref('')
const state = reactive<Record<string, { picked: string; correct: boolean }>>({})

const cur = computed<PracticeQuestion | undefined>(() => props.questions[idx.value])
const isLast = computed(() => idx.value >= props.questions.length - 1)
const answeredCount = computed(() => Object.keys(state).length)
const correctCount = computed(() => Object.values(state).filter(s => s.correct).length)
const letter = (i: number) => String.fromCharCode(65 + i)

function optText(v: string): string {
  return (v || '').replace(/^\s*[A-Da-d][.、)]\s*/, '')
}
function pick(q: PracticeQuestion, opt: string) {
  if (state[q.id]) return
  state[q.id] = { picked: opt, correct: (q.answer || '').trim() === opt.trim() }
}
function optCls(q: PracticeQuestion, opt: string): string {
  const st = state[q.id]
  if (!st) return ''
  if ((q.answer || '').trim() === opt.trim()) return 'opt-correct'
  if (st.picked === opt) return 'opt-wrong'
  return 'opt-dim'
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
  await doRecord()
  done.value = true
}
async function close() {
  if (answeredCount.value > 0 && !recorded.value) await doRecord()
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
.pq-fb { margin-top: 14rpx; }
.pq-fb .fb-ok { font-size: 24rpx; color: #128a4c; font-weight: 600; }
.pq-fb .fb-no { font-size: 24rpx; color: #c33; font-weight: 600; }
.pq-expl { display: block; margin-top: 8rpx; font-size: 23rpx; color: var(--c-text-second); line-height: 1.6; }
.pr-result { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 60rpx 0; gap: 16rpx; }
.pr-score { font-size: 72rpx; font-weight: 800; color: var(--c-primary); }
.pr-msg { font-size: 27rpx; color: var(--c-text-second); text-align: center; padding: 0 24rpx; line-height: 1.6; }
.modal-actions { display: flex; gap: 16rpx; }
.modal-btn { flex: 1; text-align: center; font-size: 27rpx; font-weight: 700; border-radius: 999rpx; padding: 16rpx; }
.modal-btn.ghost { background: var(--c-bg-soft); color: var(--c-text-second); }
.modal-btn.primary { background: var(--c-primary); color: #fff; }
.modal-btn.disabled { opacity: 0.5; }
</style>
