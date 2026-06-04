<template>
  <view class="page">
    <view class="card join-card" @tap="() => uni.navigateTo({ url: '/pages/teacher/join-institution' })">
      <text class="join-text">🏫 加入机构</text>
      <text class="arrow">›</text>
    </view>
    <view class="card">
      <view class="card-title">创建班级</view>
      <input v-model="newName" class="input" placeholder="班级名称" />
      <button class="btn-primary" :disabled="!newName || creating" @tap="onCreate">
        {{ creating ? '创建中…' : '创建' }}
      </button>
    </view>
    <view v-if="loading" class="tip">加载中…</view>
    <view v-else-if="classes.length === 0" class="tip">还没有班级</view>
    <view v-for="c in classes" :key="c.id" class="card class-item" @tap="goDetail(c.id)">
      <view>
        <text class="class-name">{{ c.name }}</text>
        <text class="class-cnt">{{ c.student_count }} 名学生</text>
      </view>
      <text class="arrow">›</text>
    </view>
  </view>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listClasses, createClass } from '@/api/classes'
import type { ClassOut } from '@/types/api'
const newName = ref('')
const creating = ref(false)
const classes = ref<ClassOut[]>([])
const loading = ref(false)
async function load() {
  loading.value = true
  try { const r = await listClasses(); classes.value = r.data || [] }
  finally { loading.value = false }
}
async function onCreate() {
  creating.value = true
  try { await createClass(newName.value); newName.value = ''; await load(); uni.showToast({ title: '已创建', icon: 'success' }) }
  catch (e: any) { uni.showToast({ title: e?.message || '失败', icon: 'none' }) }
  finally { creating.value = false }
}
function goDetail(id: string) { uni.navigateTo({ url: `/pages/teacher/class-detail?classId=${id}` }) }
onMounted(load)
</script>
<style scoped>
.page { padding: 16rpx; background: var(--c-bg-page); min-height: 100vh; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin-bottom: 16rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.card-title { font-size: var(--fs-h2); font-weight: 700; color: var(--c-ink); margin-bottom: 16rpx; }
.input { border: 2rpx solid var(--c-border); border-radius: var(--r-md); padding: 16rpx; font-size: 28rpx; width: 100%; box-sizing: border-box; margin-bottom: 16rpx; }
.btn-primary { background: var(--c-primary); color: var(--c-ink); border-radius: var(--r-btn); padding: 20rpx; font-weight: 700; font-size: 28rpx; }
.btn-primary[disabled] { background: var(--c-primary-soft); color: #b9a94e; }
.tip { text-align: center; padding: 80rpx 0; color: var(--c-text-hint); }
.class-item { display: flex; justify-content: space-between; align-items: center; }
.class-name { font-size: 28rpx; font-weight: 700; color: var(--c-ink); display: block; }
.class-cnt { font-size: 24rpx; color: var(--c-text-hint); }
.arrow { font-size: 32rpx; color: var(--c-text-hint); }
.join-card { display: flex; align-items: center; justify-content: space-between; }
.join-text { font-weight: 700; font-size: 30rpx; }
</style>
