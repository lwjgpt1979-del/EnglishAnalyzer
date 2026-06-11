<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getTtsSpeed, updateTtsSpeed } from '../api/admin'

const form = reactive({ primary: 0.8, junior: 1.0, senior: 1.1 })
const loading = ref(false)
const saving = ref(false)

async function load() {
  loading.value = true
  try {
    const s = await getTtsSpeed()
    form.primary = s.primary
    form.junior = s.junior
    form.senior = s.senior
  } finally {
    loading.value = false
  }
}

async function onSave() {
  saving.value = true
  try {
    await updateTtsSpeed({ primary: form.primary, junior: form.junior, senior: form.senior })
    ElMessage.success('已保存，约 1 分钟内全端生效')
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <el-card v-loading="loading" style="max-width: 520px">
    <template #header>听力语速（speed_ratio · 0.5~2.0）</template>
    <p style="color:#909399;font-size:13px;margin:0 0 16px">
      听力音频按学生学段使用对应语速；词力通单词统一使用「初中」档。值越小越慢。
    </p>
    <el-form label-width="120px">
      <el-form-item label="小学（慢）">
        <el-input-number v-model="form.primary" :min="0.5" :max="2" :step="0.05" :precision="2" />
      </el-form-item>
      <el-form-item label="初中（标准）">
        <el-input-number v-model="form.junior" :min="0.5" :max="2" :step="0.05" :precision="2" />
      </el-form-item>
      <el-form-item label="高中（略快）">
        <el-input-number v-model="form.senior" :min="0.5" :max="2" :step="0.05" :precision="2" />
      </el-form-item>
      <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
    </el-form>
  </el-card>
</template>
