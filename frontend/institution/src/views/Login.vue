<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'

const form = reactive({ username: '', password: '' })
const loading = ref(false)
const router = useRouter()
const auth = useAuthStore()

async function onSubmit() {
  if (!form.username || !form.password) { ElMessage.warning('请输入用户名和密码'); return }
  loading.value = true
  try {
    await auth.login(form.username, form.password)
    router.push('/')
  } catch (e) {
    ElMessage.error((e as Error).message || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-wrap">
    <el-card class="login-card">
      <h2 class="t">机构管理后台</h2>
      <el-form @submit.prevent="onSubmit">
        <el-form-item><el-input v-model="form.username" placeholder="用户名" /></el-form-item>
        <el-form-item><el-input v-model="form.password" type="password" placeholder="密码" show-password @keyup.enter="onSubmit" /></el-form-item>
        <el-button type="primary" :loading="loading" style="width:100%" @click="onSubmit">登录</el-button>
      </el-form>
      <div class="apply-entry">
        还没有机构账号？<el-link type="primary" @click="router.push('/apply')">立即申请入驻 →</el-link>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.login-wrap { height: 100vh; display: flex; align-items: center; justify-content: center; background: #f0f2f5; }
.login-card { width: 360px; }
.t { text-align: center; margin: 0 0 20px; }
.apply-entry { text-align: center; margin-top: 16px; font-size: 13px; color: #909399; }
</style>
