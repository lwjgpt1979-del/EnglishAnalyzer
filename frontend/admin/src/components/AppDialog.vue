<script setup lang="ts">
/**
 * 全项目统一弹框:在 el-dialog 基础上,标题栏固定提供「最大化 / 复原 / 关闭」三个控件
 * (见 CLAUDE.md「弹框统一控件」铁律)。近乎 el-dialog 的透明替换——
 * 把 `<el-dialog ...>` 改成 `<AppDialog ...>` 即可,v-model / title / width / 其余属性与插槽照常透传。
 * 最大化 = fullscreen;复原 = 退出 fullscreen;关闭 = 收起(不再单独用 el-dialog 自带的 X)。
 */
import { computed, ref, useSlots } from 'vue'
import { FullScreen, ScaleToOriginal, Close } from '@element-plus/icons-vue'

defineOptions({ inheritAttrs: false })
defineProps<{ modelValue?: boolean; title?: string }>()
const emit = defineEmits<{ 'update:modelValue': [boolean] }>()

const full = ref(false)
const slots = useSlots()
// 透传除 header 外的所有插槽(header 由本组件接管,加三控件)
const forwardSlots = computed(() => Object.keys(slots).filter((n) => n !== 'header'))

function onClose() { emit('update:modelValue', false) }
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="(v: boolean) => { emit('update:modelValue', v); if (!v) full = false }"
    :fullscreen="full"
    :show-close="false"
    v-bind="$attrs"
  >
    <template #header="hp">
      <div class="app-dlg-hd">
        <span class="app-dlg-title"><slot name="header" v-bind="hp">{{ title }}</slot></span>
        <span class="app-dlg-ctrls">
          <el-icon v-if="!full" class="app-dlg-btn" title="最大化" @click="full = true"><FullScreen /></el-icon>
          <el-icon v-else class="app-dlg-btn" title="复原" @click="full = false"><ScaleToOriginal /></el-icon>
          <el-icon class="app-dlg-btn app-dlg-close" title="关闭" @click="onClose"><Close /></el-icon>
        </span>
      </div>
    </template>

    <!-- 透传默认 / footer / 其余具名插槽 -->
    <template v-for="name in forwardSlots" #[name]="sp" :key="name">
      <slot :name="name" v-bind="sp || {}" />
    </template>
  </el-dialog>
</template>

<style scoped>
.app-dlg-hd { display: flex; align-items: center; gap: 12px; }
.app-dlg-title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-size: 16px; font-weight: 600; color: var(--el-text-color-primary); }
.app-dlg-ctrls { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.app-dlg-btn { cursor: pointer; padding: 4px; border-radius: 4px; font-size: 16px;
  color: var(--el-text-color-secondary); transition: background .15s, color .15s; }
.app-dlg-btn:hover { background: var(--el-fill-color-light); color: var(--el-text-color-primary); }
.app-dlg-close:hover { background: var(--el-color-danger-light-9); color: var(--el-color-danger); }
</style>
