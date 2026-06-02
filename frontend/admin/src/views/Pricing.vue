<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getPricing, updatePricing } from '../api/admin'

const form = reactive({ basic: 0, pro: 0, promax: 0 })
const loading = ref(false)
const saving = ref(false)

async function load() {
  loading.value = true
  try {
    const p = await getPricing()
    form.basic = p.basic
    form.pro = p.pro
    form.promax = p.promax
  } finally {
    loading.value = false
  }
}

async function onSave() {
  saving.value = true
  try {
    await updatePricing({ basic: form.basic, pro: form.pro, promax: form.promax })
    ElMessage.success('已保存')
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <el-card v-loading="loading" style="max-width: 480px">
    <template #header>学期会员定价（元 / 学期）</template>
    <el-form label-width="100px">
      <el-form-item label="basic">
        <el-input-number v-model="form.basic" :min="1" />
      </el-form-item>
      <el-form-item label="pro">
        <el-input-number v-model="form.pro" :min="1" />
      </el-form-item>
      <el-form-item label="promax">
        <el-input-number v-model="form.promax" :min="1" />
      </el-form-item>
      <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
    </el-form>
  </el-card>
</template>
