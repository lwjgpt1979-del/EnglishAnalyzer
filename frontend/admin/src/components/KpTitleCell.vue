<script setup lang="ts">
/** 知识图谱 · 展示标题单元(树/列表共用):主行 display_label,副行匹配名 name。 */
defineProps<{
  name: string
  displayLabel: string
  titleSource?: 'pending' | 'rule' | 'ai' | string | null
  showMatch?: boolean
  link?: boolean
}>()
defineEmits<{ click: [] }>()

const SRC_LABEL: Record<string, string> = { pending: '未整理', rule: '规则', ai: 'AI' }
</script>

<template>
  <div class="kp-cell" :class="{ 'only-name': displayLabel === name }">
    <div class="title-line">
      <el-link v-if="link" type="primary" class="display" @click.stop="$emit('click')">{{ displayLabel }}</el-link>
      <span v-else class="display">{{ displayLabel }}</span>
      <span
        v-if="titleSource && titleSource !== 'pending'"
        class="src-tag"
        :class="titleSource"
      >{{ SRC_LABEL[titleSource] || titleSource }}</span>
      <span v-else-if="titleSource === 'pending'" class="src-tag pending">{{ SRC_LABEL.pending }}</span>
    </div>
    <div v-if="showMatch && displayLabel !== name" class="match" :title="name">
      <b>匹配名</b> {{ name }}
    </div>
  </div>
</template>

<style scoped>
.kp-cell { min-width: 0; line-height: 1.35; display: flex; flex-direction: column; gap: 2px; }
.title-line { display: flex; align-items: center; gap: 6px; min-width: 0; max-width: 100%; }
.kp-cell .display {
  flex: 1; min-width: 0;
  font-size: 13px; font-weight: 700;
  display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.kp-cell :deep(.el-link.display) {
  flex: 1; min-width: 0; max-width: 100%; justify-content: flex-start;
}
.kp-cell :deep(.el-link.display .el-link__inner) {
  display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.kp-cell.only-name .display { font-weight: 650; color: var(--el-text-color-primary); }
.kp-cell .match {
  display: block; width: 100%;
  font-size: 11px; color: #94a3b8;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.kp-cell .match b { font-weight: 700; color: #cbd5e1; }
.src-tag {
  flex-shrink: 0;
  display: inline-block; font-size: 10px; font-weight: 800; padding: 1px 6px;
  border-radius: 5px;
}
.src-tag.rule { background: #e0f2fe; color: #0ea5e9; }
.src-tag.ai { background: #f3eefc; color: #7c5cbf; }
.src-tag.pending { background: #f1f5f9; color: #94a3b8; }
</style>
