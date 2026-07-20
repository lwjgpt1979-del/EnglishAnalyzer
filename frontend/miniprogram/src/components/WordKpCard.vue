<template>
  <view class="mask" @tap="emit('close')">
    <view class="sheet" @tap.stop>
      <view class="sheet-head">
        <view class="sheet-title">
          <text class="sheet-word">{{ word }}</text>
          <text v-if="zh" class="sheet-zh">{{ zh }}</text>
        </view>
        <view class="sheet-x" @tap="emit('close')"><text>✕</text></view>
      </view>

      <scroll-view scroll-y class="sheet-body">
        <view v-if="loading" class="kp-tip">考点生成中…</view>
        <view v-else-if="!hasContent" class="kp-tip">该词暂无考点</view>
        <template v-else>
          <view v-for="dim in kp!.dims" :key="dim.key" class="kp-sec">
            <text class="kp-sec-h">{{ dim.label }}</text>
            <view v-if="dim.relational" class="kp-chips">
              <text v-for="(it, i) in dim.items" :key="i" class="kp-chip">{{ it.text }}<text v-if="it.zh" class="kp-chip-zh"> {{ it.zh }}</text></text>
            </view>
            <template v-else>
              <view v-for="(it, i) in dim.items" :key="i" class="kp-line">
                <text class="kp-en">{{ it.text }}</text>
                <text v-if="it.zh || it.note" class="kp-zh">{{ it.zh }}{{ it.note ? (it.zh ? ' · ' : '') + it.note : '' }}</text>
              </view>
            </template>
          </view>
        </template>
      </scroll-view>

      <button class="kp-test-btn" :class="{ dis: testLoading }" @tap="openTest">
        {{ testLoading ? '出题中…' : '考点扩展测试' }}
      </button>
    </view>

    <PracticeQuiz v-if="testOpen" kp="考点扩展" :questions="testQs" @close="testOpen = false" />
  </view>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { getWordKp, getKpTest } from '@/api/vocabulary'
import type { WordKp, KpTestQuestion } from '@/api/vocabulary'
import PracticeQuiz from '@/components/PracticeQuiz.vue'

const props = defineProps<{ wordId: string; word: string; zh?: string }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const kp = ref<WordKp | null>(null)
const loading = ref(true)
const hasContent = computed(() => {
  const k = kp.value
  return !!k && Array.isArray(k.dims) && k.dims.length > 0
})

onMounted(async () => {
  try { kp.value = await getWordKp(props.wordId) } catch { kp.value = null }
  finally { loading.value = false }
})

const testOpen = ref(false)
const testLoading = ref(false)
const testQs = ref<Array<{ id: string; stem: string; options: string[]; answer: string; explanation: string }>>([])
async function openTest() {
  if (testLoading.value) return
  testLoading.value = true
  try {
    const qs: KpTestQuestion[] = await getKpTest(props.wordId)
    if (!qs.length) { uni.showToast({ title: '该词暂无考点题', icon: 'none' }); return }
    testQs.value = qs.map(q => ({ id: q.id, stem: `【${q.dimension_label}】${q.stem}`, options: q.options, answer: q.answer, explanation: q.explanation }))
    testOpen.value = true
  } catch { uni.showToast({ title: '出题失败,稍后重试', icon: 'none' }) }
  finally { testLoading.value = false }
}
</script>

<style scoped>
.mask { position: fixed; inset: 0; background: rgba(0,0,0,.45); z-index: 80; display: flex; align-items: flex-end; }
.sheet { width: 100%; max-height: 78vh; background: #fff; border-radius: 28rpx 28rpx 0 0; display: flex; flex-direction: column; padding: 24rpx 28rpx 30rpx; box-sizing: border-box; }
.sheet-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12rpx; }
.sheet-title { display: flex; align-items: baseline; gap: 12rpx; }
.sheet-word { font-size: 40rpx; font-weight: 800; color: #0C447C; }
.sheet-zh { font-size: 26rpx; color: #4A6785; }
.sheet-x { width: 56rpx; height: 56rpx; display: flex; align-items: center; justify-content: center; color: #9aa3b0; font-size: 34rpx; }
.sheet-body { flex: 1; min-height: 120rpx; }
.kp-tip { text-align: center; color: #9aa3b0; font-size: 26rpx; padding: 40rpx 0; }
.kp-sec { padding-top: 14rpx; margin-top: 14rpx; border-top: 1rpx solid #EEF2F7; }
.kp-sec:first-child { border-top: none; margin-top: 0; }
.kp-sec-h { display: block; font-size: 22rpx; color: #6A8CB5; margin-bottom: 8rpx; }
.kp-line { display: flex; align-items: baseline; gap: 12rpx; margin: 4rpx 0; }
.kp-en { font-size: 26rpx; color: #0C447C; font-weight: 500; }
.kp-zh { flex: 1; font-size: 24rpx; color: #4A6785; }
.kp-chips { display: flex; flex-wrap: wrap; gap: 10rpx; }
.kp-chip { font-size: 24rpx; color: #0C447C; background: #D6E6FA; padding: 6rpx 16rpx; border-radius: 10rpx; }
.kp-chip-zh { color: #4A6785; font-size: 22rpx; }
.kp-tips { display: block; font-size: 24rpx; color: #4A6785; line-height: 1.6; }
.kp-test-btn { margin-top: 18rpx; background: var(--c-primary); color: #fff; font-size: 28rpx; font-weight: 700; border-radius: var(--r-pill); padding: 18rpx 0; }
.kp-test-btn.dis { opacity: .6; }
</style>
