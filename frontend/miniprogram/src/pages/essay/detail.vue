<template>
  <view class="page">
    <view v-if="!essay" class="tip">加载中…</view>
    <view v-else>
      <view class="card">
        <view class="card-title">总分 {{ essay.total }}</view>
        <view v-for="s in essay.scores" :key="s.dimension" class="score-row">
          <text class="dim">{{ s.dimension }}</text>
          <text class="sc">{{ s.score }} / {{ s.full }}</text>
        </view>
      </view>

      <view class="card">
        <view class="card-title">原文</view>
        <text class="para">{{ essay.original_text }}</text>
      </view>

      <view class="card">
        <view class="card-title">AI 优化版</view>
        <text class="para">{{ essay.polished_text }}</text>
      </view>

      <view v-if="essay.issues.length" class="card">
        <view class="card-title">逐处建议</view>
        <view v-for="(it, i) in essay.issues" :key="i" class="issue" :class="it.color">
          <text class="issue-head">{{ it.original }} → {{ it.suggestion }}（{{ it.type }}）</text>
          <text class="issue-exp">{{ it.explanation }}</text>
        </view>
      </view>

      <view v-if="essay.rounds && essay.rounds.length > 1" class="card">
        <view class="card-title">进步轨迹</view>
        <view v-for="r in essay.rounds" :key="r.round" class="score-row">
          <text class="dim">第 {{ r.round }} 轮</text>
          <text class="sc">{{ r.total }} 分</text>
        </view>
      </view>

      <view v-if="tpl" class="card">
        <view class="card-title">模板与范文</view>
        <text class="para">{{ tpl.template }}</text>
        <view v-for="(s, i) in tpl.samples" :key="i" class="sample">{{ i + 1 }}. {{ s }}</view>
        <view class="sample-tip">ProMax 可查看更多范文</view>
      </view>

      <view class="card">
        <button v-if="!showRevise" class="btn-ghost" @tap="showRevise = true">再改一版（ProMax）</button>
        <view v-else>
          <textarea v-model="revised" class="essay-input" placeholder="粘贴你修改后的作文…" />
          <button class="btn-primary" :disabled="repolishing || !revised.trim()" @tap="onRepolish">
            {{ repolishing ? '批改中…' : '提交新一轮' }}
          </button>
        </view>
      </view>
    </view>

    <Paywall :open="showPaywall" :feature="ent.feature('essay.rewrite')" emoji="✍️"
      title="多轮重写是 ProMax 专属" @close="showPaywall = false" />
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getEssay, repolishEssay, getEssayTemplates } from '@/api/essay'
import type { EssayDetail, EssayTemplates } from '@/types/api'
import { useEntitlementsStore } from '@/stores/entitlements'
import Paywall from '@/components/Paywall.vue'

const ent = useEntitlementsStore()
const showPaywall = ref(false)
const essay = ref<EssayDetail | null>(null)
const tpl = ref<EssayTemplates | null>(null)
const revised = ref('')
const showRevise = ref(false)
const repolishing = ref(false)

function loadEssay(id: string) {
  getEssay(id).then((e) => {
    essay.value = e
    getEssayTemplates(e.essay_type || undefined).then((t) => { tpl.value = t }).catch(() => {})
  }).catch((e) => uni.showToast({ title: (e as Error).message, icon: 'none' }))
}

onLoad((q) => {
  ent.ensure()
  const id = (q as { id?: string })?.id
  if (id) loadEssay(id)
})

async function onRepolish() {
  if (!essay.value || !revised.value.trim()) return
  if (!ent.can('essay.rewrite')) { showPaywall.value = true; return }
  repolishing.value = true
  try {
    essay.value = await repolishEssay(essay.value.id, revised.value)
    revised.value = ''
    showRevise.value = false
    uni.showToast({ title: '已生成新一轮', icon: 'success' })
  } catch (e) {
    if ((e as { code?: number }).code === 403) { showPaywall.value = true }
    else uni.showToast({ title: (e as Error).message, icon: 'none' })
  } finally {
    repolishing.value = false
  }
}
</script>

<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.tip { text-align: center; padding: 120rpx 0; color: var(--c-text-hint); }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin-bottom: 20rpx; }
.card-title { font-size: var(--fs-h2); font-weight: 700; color: var(--c-ink); margin-bottom: 16rpx; }
.score-row { display: flex; justify-content: space-between; padding: 8rpx 0; font-size: 28rpx; color: var(--c-text-body); }
.sc { font-weight: 700; color: var(--c-gold); }
.para { font-size: 28rpx; color: var(--c-text-body); line-height: 1.7; white-space: pre-wrap; }
.issue { padding: 12rpx; border-radius: 12rpx; margin-bottom: 12rpx; background: var(--c-bg-page); border-left: 6rpx solid var(--c-border); }
.issue.red { border-left-color: #e54d42; }
.issue.yellow { border-left-color: #f0ad4e; }
.issue.blue { border-left-color: #3b82f6; }
.issue-head { display: block; font-size: 26rpx; font-weight: 700; color: var(--c-ink); }
.issue-exp { display: block; font-size: 24rpx; color: var(--c-text-second); margin-top: 6rpx; line-height: 1.6; }
.sample { font-size: 24rpx; color: var(--c-text-second); line-height: 1.7; margin-top: 8rpx; }
.sample-tip { font-size: 22rpx; color: var(--c-text-hint); margin-top: 10rpx; }
.essay-input { width: 100%; height: 240rpx; font-size: 28rpx; color: var(--c-text-body); line-height: 1.6; }
.btn-primary { background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-btn); padding: 20rpx; font-weight: 700; font-size: 28rpx; margin-top: 12rpx; }
.btn-primary[disabled] { background: var(--c-primary-soft); color: #9aa7b8; }
.btn-ghost { background: var(--c-bg-page); color: var(--c-text-body); border-radius: var(--r-btn); padding: 18rpx; font-size: 28rpx; }
</style>
