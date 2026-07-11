<template>
  <view class="page">
    <view class="hd">
      <text class="hd-title">课程精讲</text>
      <text class="hd-sub">来自教材课程,按 版本 → 年级 → 上下册 → 单元 学。</text>
    </view>
    <view v-for="m in modules" :key="m.kind" class="card mod" @tap="go(m)">
      <view class="mod-ic" :class="m.ic" />
      <view class="mod-text">
        <text class="mod-title">{{ m.title }}</text>
        <text class="mod-sub">{{ m.sub }}</text>
      </view>
      <text class="mod-arrow">›</text>
    </view>
  </view>
</template>

<script setup lang="ts">
const modules = [
  { kind: 'word', title: '单词', sub: '按教材单元背单词', ic: 'ic-vocab' },
  { kind: 'grammar', title: '语法精讲', sub: '按教材单元学语法', ic: 'ic-grammar' },
  { kind: 'sentence', title: '长难句', sub: '按教材单元拆长难句', ic: 'ic-sentence' },
]
function go(m: { kind: string }) {
  uni.navigateTo({ url: `/pages/intensive/module?mode=course&kind=${m.kind}` })
}
</script>

<style scoped>
.page { min-height: 100vh; background: var(--c-bg, #f5f7fa); padding: 24rpx; box-sizing: border-box; }
.hd { padding: 8rpx 4rpx 20rpx; }
.hd-title { font-size: 40rpx; font-weight: 800; color: var(--c-ink); display: block; }
.hd-sub { font-size: 24rpx; color: var(--c-text-hint); margin-top: 8rpx; display: block; line-height: 1.5; }
.card { background: #fff; border-radius: 20rpx; padding: 28rpx 24rpx; margin-bottom: 18rpx; }
.mod { display: flex; align-items: center; gap: 18rpx; }
.mod-ic { width: 56rpx; height: 56rpx; flex-shrink: 0; border-radius: 14rpx; background: #eafaf1; }
.mod-text { flex: 1; display: flex; flex-direction: column; gap: 4rpx; }
.mod-title { font-size: 30rpx; font-weight: 800; color: var(--c-ink); }
.mod-sub { font-size: 22rpx; color: var(--c-text-hint); }
.mod-arrow { font-size: 34rpx; color: var(--c-text-hint); }
</style>
