<script setup lang="ts">
/**
 * 长难句结构预览:彩色虚线下划线 + 序号 + 译文 + 图例(与 long-sentence/index 原句区一致)。
 */
import { computed } from 'vue'

const props = defineProps<{
  analysis?: { segments?: { idx: number; text?: string; type?: string; color?: string }[]; translation?: string } | null
  plain?: string
}>()

const PALETTE = ['#3b6fe0', '#1f9d6b', '#8a5cf0', '#e08a2f', '#e0529c', '#0e9aa7', '#2f9fc4', '#6366f1', '#ef4444']

const segments = computed(() =>
  (props.analysis?.segments || []).slice().sort((a, b) => (a.idx ?? 0) - (b.idx ?? 0)).map(s => {
    const toks = (s.text || '').trim().split(/\s+/)
    return { ...s, first: toks[0] || '', rest: toks.slice(1).join(' ') }
  }))

const colorMap = computed(() => {
  const m: Record<number, string> = {}
  for (const s of segments.value) if (s.color) m[s.idx] = s.color
  return m
})

/** @param idx 成分序号 */
function colorOf(idx: number) {
  return colorMap.value[idx] || PALETTE[(idx - 1) % PALETTE.length] || '#666'
}

const legend = computed(() => {
  const seen = new Set<string>()
  const out: { color: string; label: string }[] = []
  for (const s of segments.value) {
    const c = s.color
    if (!c || seen.has(c)) continue
    seen.add(c)
    const label = (s.type || '').replace(/(连词|关联词|第[一二三四五六七八九十]+分句|分句|部分)$/, '') || s.type || '成分'
    out.push({ color: c, label })
  }
  return out
})

const hasStruct = computed(() => segments.value.length > 0)
</script>

<template>
  <view class="ssb">
    <view v-if="hasStruct" class="sentence">
      <text
        v-for="s in segments"
        :key="s.idx"
        class="seg"
        :style="{ color: colorOf(s.idx), borderBottomColor: colorOf(s.idx) }"
      >
        <text class="fw">
          {{ s.first }}
          <text class="badge" :style="{ background: colorOf(s.idx) }">{{ s.idx }}</text>
        </text>{{ (s.rest ? ' ' + s.rest : '') + ' ' }}
      </text>
    </view>
    <text v-else class="plain">{{ plain }}</text>
    <view v-if="hasStruct && analysis?.translation" class="trans">{{ analysis.translation }}</view>
    <view v-if="hasStruct && legend.length" class="legend">
      <view v-for="l in legend" :key="l.color" class="lg-item">
        <text class="lg-dot" :style="{ background: l.color }" />
        <text class="lg-tx">{{ l.label }}</text>
      </view>
    </view>
  </view>
</template>

<style scoped>
.ssb { display: flex; flex-direction: column; gap: 0; }
/* 连续流式段落;序号锚在每段首词下方(与 long-sentence 原句区一致) */
.sentence {
  font-family: Georgia, 'Times New Roman', 'Songti SC', serif;
  font-size: 32rpx; line-height: 3;
  background: #fdf8ee; border-radius: 16rpx; padding: 20rpx 22rpx;
}
.seg { border-bottom: 2rpx dashed; padding-bottom: 6rpx; }
.fw { position: relative; }
.badge {
  position: absolute; left: 50%; top: 130%; transform: translateX(-50%);
  width: 32rpx; height: 32rpx; line-height: 32rpx; text-align: center;
  border-radius: 50%; color: #fff; font-size: 18rpx;
}
.plain { font-size: 30rpx; line-height: 1.7; color: var(--c-ink); }
.trans {
  margin-top: 16rpx; padding: 18rpx 20rpx;
  background: #f0f2f6; border-radius: 14rpx;
  font-size: 28rpx; color: #555; line-height: 1.7;
}
.legend {
  margin-top: 18rpx; padding-top: 16rpx; border-top: 1rpx solid #ebe6dc;
  display: flex; flex-wrap: wrap; gap: 12rpx 22rpx;
}
.lg-item { display: flex; align-items: center; gap: 8rpx; }
.lg-dot { width: 18rpx; height: 18rpx; border-radius: 5rpx; flex-shrink: 0; }
.lg-tx { font-size: 23rpx; color: #777; }
</style>
