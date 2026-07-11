<template>
  <view class="page">
    <view class="hd">
      <text class="hd-title">我的语法树</text>
      <text class="hd-sub">按当前教材进度铺开——绿色已学、灰色未学。点未学去看讲解。</text>
    </view>

    <view v-if="loading" class="tip">加载中…</view>

    <!-- 未设进度 -->
    <view v-else-if="tree && !tree.has_progress" class="empty-card">
      <text class="empty-t">还没设置教材进度</text>
      <text class="empty-x">去「我的 → 教材偏好」选好教材/年级/学期(以及学到第几单元),这里才能按进度算出你的语法树。</text>
      <view class="empty-btn" @tap="goProfile"><text>去设置</text></view>
    </view>

    <template v-else-if="tree">
      <!-- 汇总 -->
      <view class="sum">
        <view class="sum-cell"><text class="sum-n ok">{{ tree.totals.learned }}</text><text class="sum-l">已学</text></view>
        <view class="sum-cell"><text class="sum-n no">{{ tree.totals.unlearned }}</text><text class="sum-l">未学</text></view>
        <view class="sum-cell"><text class="sum-n">{{ progressPct }}%</text><text class="sum-l">掌握占比</text></view>
      </view>

      <!-- 词法 / 句法 两棵 -->
      <view v-for="r in tree.roots" :key="r.code" class="root">
        <view class="root-hd" @tap="toggleRoot(r.code)">
          <text class="root-bar" />
          <text class="root-name">{{ r.name }}</text>
          <text class="root-meta">已学 {{ r.learned }} · 未学 {{ r.unlearned }}</text>
          <text class="root-caret">{{ rootOpen[r.code] === false ? '▸' : '▾' }}</text>
        </view>
        <view v-if="rootOpen[r.code] !== false" class="cats">
          <view v-for="c in r.cats" :key="c.code" class="cat">
            <view class="cat-hd" @tap="toggleCat(c.code)">
              <text class="cat-name">{{ c.name }}</text>
              <text class="cat-meta">{{ c.learned }}/{{ c.learned + c.unlearned }}</text>
              <text class="cat-caret">{{ catOpen[c.code] ? '▾' : '▸' }}</text>
            </view>
            <view v-if="catOpen[c.code]" class="items">
              <view v-for="it in c.items" :key="it.node_id" class="item"
                    :class="{ 'is-learned': it.status === 'learned' }" @tap="goNode(it)">
                <text class="dot" :class="it.status === 'learned' ? 'dot-ok' : 'dot-no'" />
                <text class="item-name">{{ it.name }}</text>
                <text v-if="it.status !== 'learned'" class="item-go">去学 ›</text>
              </view>
            </view>
          </view>
        </view>
      </view>

      <!-- 个人自建(未收录图谱) -->
      <view v-if="tree.personal.length" class="root">
        <view class="root-hd" @tap="toggleRoot('__personal')">
          <text class="root-bar personal" />
          <text class="root-name">自建 · 未收录</text>
          <text class="root-meta">{{ tree.personal.length }} 个</text>
          <text class="root-caret">{{ rootOpen['__personal'] === false ? '▸' : '▾' }}</text>
        </view>
        <view v-if="rootOpen['__personal'] !== false" class="cats">
          <text class="personal-tip">这些来自你上传的试卷/作业,图谱里还没收录,先归到你自己的语法树。</text>
          <view class="items">
            <view v-for="p in tree.personal" :key="p.personal_id" class="item">
              <text class="dot dot-no" />
              <text class="item-name">{{ p.name }}</text>
              <text class="item-tag">{{ p.source === 'upload_paper' ? '试卷' : '作业' }}</text>
            </view>
          </view>
        </view>
      </view>
    </template>
  </view>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getGrammarTree, type GrammarTree, type GrammarTreeItem } from '@/api/curriculum'

const tree = ref<GrammarTree | null>(null)
const loading = ref(true)
const rootOpen = reactive<Record<string, boolean>>({})   // 默认展开(undefined 视为开)
const catOpen = reactive<Record<string, boolean>>({})    // 默认折叠

const progressPct = computed(() => {
  const t = tree.value
  if (!t) return 0
  const tot = t.totals.learned + t.totals.unlearned
  return tot ? Math.round((t.totals.learned / tot) * 100) : 0
})

function toggleRoot(code: string) { rootOpen[code] = rootOpen[code] === false ? true : false }
function toggleCat(code: string) { catOpen[code] = !catOpen[code] }
function goNode(it: GrammarTreeItem) {
  if (it.status === 'learned') return
  uni.navigateTo({ url: `/pages/curriculum/kp-content?id=${it.node_id}&name=${encodeURIComponent(it.name)}&cat=grammar` })
}
function goProfile() { uni.switchTab({ url: '/pages/profile/index' }) }

async function load() {
  loading.value = true
  try { tree.value = await getGrammarTree() } catch (e: any) { uni.showToast({ title: e?.message || '加载失败', icon: 'none' }) }
  finally { loading.value = false }
}
onLoad(() => { load() })
</script>

<style scoped>
.page { min-height: 100vh; background: var(--c-bg, #f5f7fa); padding: 24rpx 24rpx 60rpx; box-sizing: border-box; }
.hd { padding: 8rpx 4rpx 20rpx; }
.hd-title { font-size: 40rpx; font-weight: 800; color: var(--c-ink); display: block; }
.hd-sub { font-size: 24rpx; color: var(--c-text-hint); margin-top: 8rpx; display: block; line-height: 1.5; }
.tip { text-align: center; color: var(--c-text-hint); padding: 80rpx 0; }

.empty-card { background: #fff; border-radius: 20rpx; padding: 40rpx 32rpx; display: flex; flex-direction: column; align-items: center; gap: 16rpx; margin-top: 20rpx; }
.empty-t { font-size: 30rpx; font-weight: 700; color: var(--c-ink); }
.empty-x { font-size: 25rpx; color: var(--c-text-sub); text-align: center; line-height: 1.6; }
.empty-btn { margin-top: 8rpx; background: var(--c-primary); color: #fff; font-size: 27rpx; padding: 16rpx 48rpx; border-radius: 999rpx; }

.sum { display: flex; background: #fff; border-radius: 20rpx; padding: 26rpx 0; margin-bottom: 20rpx; }
.sum-cell { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 6rpx; }
.sum-n { font-size: 40rpx; font-weight: 800; color: var(--c-ink); }
.sum-n.ok { color: #2ecc71; }
.sum-n.no { color: var(--c-text-sub); }
.sum-l { font-size: 22rpx; color: var(--c-text-hint); }

.root { background: #fff; border-radius: 20rpx; margin-bottom: 20rpx; overflow: hidden; }
.root-hd { display: flex; align-items: center; gap: 14rpx; padding: 26rpx 24rpx; }
.root-bar { width: 8rpx; height: 32rpx; border-radius: 6rpx; background: var(--c-primary); }
.root-bar.personal { background: #b9892e; }
.root-name { font-size: 30rpx; font-weight: 800; color: var(--c-ink); }
.root-meta { flex: 1; font-size: 22rpx; color: var(--c-text-hint); }
.root-caret { font-size: 26rpx; color: var(--c-text-hint); }

.cats { padding: 0 24rpx 12rpx; }
.cat { border-top: 2rpx solid var(--c-line, #eef1f5); }
.cat-hd { display: flex; align-items: center; gap: 12rpx; padding: 20rpx 4rpx; }
.cat-name { font-size: 27rpx; font-weight: 600; color: var(--c-ink); }
.cat-meta { flex: 1; font-size: 22rpx; color: var(--c-text-hint); }
.cat-caret { font-size: 24rpx; color: var(--c-text-hint); }

.items { padding: 0 4rpx 12rpx; display: flex; flex-direction: column; gap: 4rpx; }
.item { display: flex; align-items: center; gap: 14rpx; padding: 14rpx 12rpx; border-radius: 12rpx; background: var(--c-bg-soft, #f7f9fc); }
.item.is-learned { opacity: .7; }
.dot { width: 14rpx; height: 14rpx; border-radius: 50%; flex-shrink: 0; }
.dot-ok { background: #2ecc71; }
.dot-no { background: #cbd3dd; }
.item-name { flex: 1; font-size: 26rpx; color: var(--c-ink); }
.item-go { font-size: 22rpx; color: var(--c-primary); }
.item-tag { font-size: 20rpx; color: #b9892e; background: #fdf3e2; border-radius: 8rpx; padding: 2rpx 12rpx; }
.personal-tip { display: block; font-size: 22rpx; color: var(--c-text-hint); line-height: 1.5; padding: 12rpx 4rpx; }
</style>
