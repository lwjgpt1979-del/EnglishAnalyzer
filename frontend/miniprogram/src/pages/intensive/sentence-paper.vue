<template>
  <view class="page">
    <view v-if="loading" class="tip">加载中…</view>
    <!-- 卷学习页(卷头进度即底色 + 待学清单);点句进逐句解析(看过即算学过),作业/课程同一套 -->
    <template v-else>
      <!-- 蓝-4 徽章环:卷头满环激励 -->
      <view v-if="sentences.length" class="se-ban">
        <view class="ic ic-trophy se-ban-ic"></view>
        <text class="se-ban-t">{{ ringBannerText }}</text>
      </view>
      <PaperChecklist :items="sentences" :date="sub" unit="句"
          @open="(s) => goAnalyze(s.text)" @start="(i) => goAnalyze(sentences[i] && sentences[i].text)">
        <!-- 每句 n/3 徽章环(认成分 + 认语法 + 重点词) -->
        <template #tick="{ item }">
          <view class="se-ring" :style="ringStyle(item.ring || 0)">
            <view class="se-ring-in"><text class="se-ring-n">{{ item.ring || 0 }}</text></view>
          </view>
        </template>
        <template #item="{ item }"><text class="se-text">{{ item.text }}</text></template>
        <template #empty>该{{ mode === 'homework' ? '批次' : '单元' }}没有长难句</template>
      </PaperChecklist>
      <text v-if="sentences.length" class="se-foot">环满 3/3 = 认成分 + 认语法 + 重点词 全过</text>
    </template>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import PaperChecklist from '@/components/PaperChecklist.vue'
import { seHwSentences, seCourseSentences, type SentenceItem } from '@/api/curriculum'

const mode = ref('homework')
const groupId = ref('')
const sub = ref('')
const sentences = ref<SentenceItem[]>([])
const loading = ref(true)

// 蓝-4 徽章环:卷头满环激励 + 每句 n/3 环(SVG 背景,mp-weixin 安全)
const ringBannerText = computed(() => {
  const total = sentences.value.length
  if (!total) return ''
  const full = sentences.value.filter(s => (s.ring || 0) >= 3).length
  const left = total - full
  return left <= 0 ? '全卷满环 · 已解锁「长难句能手」' : `${full} 句满环 · 再攻 ${left} 句解锁「长难句能手」`
})
function ringStyle(n: number) {
  const C = 94.2                                   // 2π·15
  const arc = Math.max(0, Math.min(3, n)) / 3 * C
  const svg = `%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 36 36'%3E`
    + `%3Ccircle cx='18' cy='18' r='15' fill='none' stroke='%23e6eaf0' stroke-width='4'/%3E`
    + `%3Ccircle cx='18' cy='18' r='15' fill='none' stroke='%233d8bf5' stroke-width='4' stroke-linecap='round' stroke-dasharray='${arc.toFixed(1)} ${(C - arc).toFixed(1)}' transform='rotate(-90 18 18)'/%3E`
    + `%3C/svg%3E`
  return { backgroundImage: `url("data:image/svg+xml,${svg}")` }
}

function goAnalyze(text: string) {
  if (!text) return
  // 作业模式带上批次卷号,学习页里加入的语法/单词才能归到同一作业批次
  const pid = mode.value === 'homework' && groupId.value ? `&paperId=${groupId.value}` : ''
  uni.navigateTo({ url: `/pages/user-papers/sentence?text=${encodeURIComponent(text)}${pid}` })
}

async function load() {
  loading.value = true
  sentences.value = []
  try {
    sentences.value = mode.value === 'homework'
      ? (await seHwSentences(groupId.value)).sentences
      : (await seCourseSentences(groupId.value)).sentences
  } catch (e: any) { uni.showToast({ title: e?.message || '加载失败', icon: 'none' }) }
  finally { loading.value = false }
}

onLoad((q: any) => {
  mode.value = q.mode || 'homework'
  groupId.value = q.id || ''
  sub.value = q.sub ? decodeURIComponent(q.sub) : ''
  if (q.title) uni.setNavigationBarTitle({ title: decodeURIComponent(q.title) })
  load()
})
// 从逐句解析返回 → 刷新进度与打勾(跳过 onLoad 后首次)
let _shown = false
onShow(() => { if (!_shown) { _shown = true; return } load() })
</script>

<style scoped>
.page { min-height: 100vh; background: var(--c-bg, #f5f7fa); padding: 24rpx; box-sizing: border-box; }
.tip { text-align: center; color: var(--c-text-hint); padding: 70rpx 24rpx; line-height: 1.6; }
.se-text { font-size: 27rpx; line-height: 1.6; color: var(--c-ink); }
/* 蓝-4 徽章环 */
.se-ban { display: flex; align-items: center; gap: 14rpx; background: #e9f2fe; border: 2rpx solid #cfe2ff; border-radius: 16rpx; padding: 18rpx 20rpx; margin-bottom: 16rpx; }
.se-ban-ic { width: 40rpx; height: 40rpx; flex-shrink: 0; }
.se-ban-t { flex: 1; font-size: 26rpx; color: #185fa5; font-weight: 500; }
.se-ring { width: 52rpx; height: 52rpx; flex-shrink: 0; background-size: contain; background-repeat: no-repeat; background-position: center; display: flex; align-items: center; justify-content: center; }
.se-ring-n { font-size: 24rpx; font-weight: 800; color: var(--c-primary, #3d8bf5); }
.se-foot { display: block; font-size: 21rpx; color: var(--c-text-hint); margin: 4rpx 8rpx 0; }
</style>
