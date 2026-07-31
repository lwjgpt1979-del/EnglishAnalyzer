<script setup lang="ts">
/** 单独逻辑题预览:语境句 + 选项 + 答案 */
export interface LogicDisplay {
  ready?: boolean
  logic_type?: 'mcq' | 'fill' | string
  logic_stem?: string
  logic_options_line?: string
  logic_answer?: string | null
  logic_answer_text?: string | null
}

defineProps<{
  logic?: LogicDisplay | null
  compact?: boolean
}>()
</script>

<template>
  <div v-if="logic?.ready && logic.logic_stem" class="logic-box" :class="{ compact }">
    <div class="logic-label">
      单独逻辑题 · {{ logic.logic_type === 'fill' ? '填空' : '四选一' }}
    </div>
    <div class="logic-stem">{{ logic.logic_stem }}</div>
    <div v-if="logic.logic_options_line" class="logic-opts">{{ logic.logic_options_line }}</div>
    <div v-if="logic.logic_answer_text" class="logic-ans">
      答案：<span v-if="logic.logic_answer">{{ logic.logic_answer }} · </span>{{ logic.logic_answer_text }}
    </div>
  </div>
  <div v-else-if="logic && logic.ready === false" class="logic-box muted">
    <div class="logic-label warn">单独逻辑题 · 未生成</div>
    <div class="logic-hint">logic_stem 缺失/未自足或校验未过(程序兜底亦失败)</div>
  </div>
</template>

<style scoped>
.logic-box {
  margin-top: 8px;
  padding: 8px 10px;
  background: #f8fafc;
  border: 1px solid #e8edf4;
  border-left: 3px solid var(--el-color-primary, #3d8bf5);
  border-radius: 4px;
}
.logic-box.compact { margin-top: 6px; padding: 6px 8px; }
.logic-box.muted { border-left-color: #e6a23c; opacity: .85; }
.logic-label { font-size: 11px; font-weight: 700; color: #3d8bf5; margin-bottom: 4px; }
.logic-label.warn { color: #e6a23c; }
.logic-stem { font-size: 13px; line-height: 1.55; color: #303133; }
.logic-opts { font-size: 12px; color: #606266; margin-top: 6px; }
.logic-ans { font-size: 11px; color: #2fa98a; margin-top: 4px; font-weight: 600; }
.logic-hint { font-size: 12px; color: #909399; }
</style>
