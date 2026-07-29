<template>
  <view v-if="text" class="card-mask" @tap="emit('close')">
    <view class="card-pop" @tap.stop>
      <view class="cp-kicker">{{ kicker }}</view>
      <view class="cp-head">
        <view class="ic ic-idea cp-ic"></view>
        <text class="cp-tt">长难句</text>
      </view>
      <!-- 有 parts 时分段着色:填绿 / 未填红占位;否则纯文本 -->
      <view v-if="parts && parts.length" class="cp-text">
        <text
          v-for="(p, i) in parts" :key="i"
          :class="{ 'cp-fill': p.kind === 'fill', 'cp-hole': p.kind === 'hole' }"
        >{{ p.t }}</text>
      </view>
      <text v-else class="cp-text">{{ text }}</text>
      <view v-if="chips.length" class="cp-chips">
        <text
          v-for="(c, i) in chips" :key="i"
          class="cp-chip" :class="{ ok: !!c.word }"
        >{{ c.word ? `空${c.no} → ${c.word}` : `空${c.no} 未填` }}</text>
      </view>
      <text class="cp-hint">{{ hint }}</text>
      <view class="cp-go" @tap="goFull">
        <text>查看完整精讲</text>
        <view class="ic ic-arrow-right cp-go-ic"></view>
      </view>
      <text v-if="note" class="cp-note">{{ note }}</text>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed } from 'vue'

/** 句卡分段:普通文 / 已填正确答案 / 无答案占位 */
export type SentenceFillPart = { kind: 'text' | 'fill' | 'hole'; t: string }
/** 空号芯片:有 word=已填,无=未填 */
export type SentenceFillChip = { no: string; word?: string }

const props = defineProps<{
  text: string | null
  paperId?: string
  /** 方案 C:分段渲染(填绿/未填红) */
  parts?: SentenceFillPart[] | null
  /** 方案 C:填空芯片 */
  chips?: SentenceFillChip[] | null
  /** 方案 C:无标准答的空号 */
  missing?: string[] | null
}>()
const emit = defineEmits<{ (e: 'close'): void }>()

const chips = computed(() => props.chips || [])
const missing = computed(() => props.missing || [])

const kicker = computed(() => {
  if (missing.value.length) return '长难句 · 部分空未填'
  if (chips.value.some(c => c.word)) return '长难句 · 已填正确答案'
  return '长难句 · 点开句卡'
})

const hint = computed(() => {
  if (missing.value.length) {
    return `部分空无标准答,已保留占位:(${missing.value.join(')(')})。有标准答的空已填绿。`
  }
  if (chips.value.some(c => c.word)) {
    return '结构较复杂,点击查看逐句精讲(结构 · 语法 · 重点词)。精讲将基于上方满句,不再带着空号调 LLM。'
  }
  return '结构较复杂,点击查看逐句精讲(结构 · 语法 · 重点词)'
})

const note = computed(() => {
  if (!chips.value.length && !missing.value.length) return ''
  return '卷面原文空号胶囊不变;仅句卡 / 完整精讲使用满句。无 correct_answer 时保留 (n)。'
})

function goFull() {
  if (!props.text) return
  uni.navigateTo({ url: `/pages/user-papers/sentence?text=${encodeURIComponent(props.text)}&paperId=${props.paperId || ''}` })
}
</script>

<style scoped>
.card-mask { position: fixed; left: 0; right: 0; top: 0; bottom: 0; background: rgba(0,0,0,.45); display: flex; align-items: center; justify-content: center; z-index: 300; padding: 40rpx; }
/* 浅蓝色风格:顶条+踢头+按钮统一主色,提示区淡蓝底 */
.card-pop { width: 100%; max-width: 620rpx; background: #fff; border-radius: 24rpx; padding: 28rpx; box-sizing: border-box; border-top: 8rpx solid var(--c-primary); }
.cp-kicker { font-size: 22rpx; font-weight: 700; color: var(--c-primary); margin-bottom: 10rpx; }
.cp-head { display: flex; align-items: center; gap: 10rpx; }
.cp-ic { width: 32rpx; height: 32rpx; flex: none; }
.cp-tt { font-size: 30rpx; font-weight: 800; color: var(--c-ink); }
.cp-text { display: block; font-size: 27rpx; color: var(--c-ink); line-height: 1.7; margin-top: 16rpx; }
.cp-fill {
  font-weight: 800; color: #1f8a6e; background: #e9f6f1;
  border-radius: 6rpx; padding: 0 6rpx; border-bottom: 3rpx solid #2fa98a;
}
.cp-hole {
  font-weight: 800; color: #a32d2d; background: #fcebeb;
  border-radius: 6rpx; padding: 0 6rpx;
}
.cp-chips { display: flex; flex-wrap: wrap; gap: 8rpx; margin-top: 14rpx; }
.cp-chip {
  font-size: 20rpx; font-weight: 700; padding: 4rpx 12rpx; border-radius: 999rpx;
  background: #eaf2fe; color: var(--c-primary);
}
.cp-chip.ok { background: #e9f6f1; color: #1f8a6e; }
.cp-hint { display: block; font-size: 23rpx; color: #3a4353; line-height: 1.6; margin-top: 14rpx; background: #eef5ff; border-radius: 12rpx; padding: 14rpx 16rpx; }
.cp-go { margin-top: 20rpx; display: flex; align-items: center; justify-content: center; gap: 6rpx; font-size: 26rpx; font-weight: 700; color: #fff; background: var(--c-primary); border-radius: 999rpx; padding: 16rpx; }
.cp-go-ic { width: 26rpx; height: 26rpx; filter: brightness(0) invert(1); }
.cp-note { display: block; margin-top: 12rpx; font-size: 20rpx; color: #93a0b3; line-height: 1.5; }
</style>
