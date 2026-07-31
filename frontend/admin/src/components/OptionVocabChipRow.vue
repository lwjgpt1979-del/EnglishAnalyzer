<script setup lang="ts">
/**
 * 真题选项词只读 chip：主·考（绿）/ 次·干扰（粉）；对不齐时灰字提示。
 */
export type OptionVocabView = {
  correct?: string[]
  distractor?: string[]
  unresolved?: boolean
}

defineProps<{
  /** 挂词预览或已落库边 */
  vocab?: OptionVocabView | null
  /** 是否显示「主考/干扰」前缀（列表紧凑可关） */
  withPrefix?: boolean
}>()
</script>

<template>
  <div v-if="vocab && ((vocab.correct?.length) || (vocab.distractor?.length) || vocab.unresolved)"
    class="ov-row">
    <template v-if="vocab.unresolved && !(vocab.correct?.length)">
      <span class="ov-miss">主考未抽出</span>
    </template>
    <template v-else>
      <span v-for="(t, i) in (vocab.correct || [])" :key="'c' + i" class="ov-chip main">
        {{ withPrefix !== false ? `主·考 ${t}` : t }}
      </span>
      <span v-for="(t, i) in (vocab.distractor || [])" :key="'d' + i" class="ov-chip sec">
        {{ withPrefix !== false ? `次·干扰 ${t}` : t }}
      </span>
    </template>
  </div>
</template>

<style scoped>
.ov-row {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
  margin-top: 4px;
}
.ov-chip {
  font-size: 11px;
  line-height: 1.4;
  padding: 1px 8px;
  border-radius: 999px;
  border: 1px solid;
}
.ov-chip.main {
  background: #e9f6f1;
  border-color: #b7e4d4;
  color: #1f7a61;
}
.ov-chip.sec {
  background: #fef0f0;
  border-color: #f5c2c2;
  color: #c45656;
}
.ov-miss {
  font-size: 11px;
  color: #94a3b8;
}
</style>
