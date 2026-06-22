<!-- 句子结构思维导图:递归树节点(盒子 + 连线) -->
<template>
  <view class="tnode">
    <view class="tbox" :style="{ background: tintOf(node.idx), borderColor: colorOf(node.idx) }">
      <view class="thead">
        <text class="tno" :style="{ background: colorOf(node.idx) }">{{ node.idx }}</text>
        <text class="ttype" :style="{ color: colorOf(node.idx) }">{{ node.type }}</text>
      </view>
      <text class="ttext">{{ node.text }}</text>
    </view>
    <view v-if="node.children && node.children.length" class="tchildren">
      <LsTreeNode v-for="c in node.children" :key="c.idx" :node="c" :color-of="colorOf" :tint-of="tintOf" />
    </view>
  </view>
</template>

<script setup lang="ts">
import LsTreeNode from './LsTreeNode.vue'

interface TNode { idx: number; type: string; text: string; children: TNode[] }
defineProps<{
  node: TNode
  colorOf: (idx: number) => string
  tintOf: (idx: number) => string
}>()
</script>

<style scoped>
.tnode { display: flex; flex-direction: column; align-items: center; position: relative; padding: 0 10rpx; }
.tbox { border: 1rpx solid; border-radius: 14rpx; padding: 14rpx 16rpx; width: 300rpx; box-sizing: border-box; }
.thead { display: flex; align-items: center; gap: 10rpx; margin-bottom: 6rpx; }
.tno { width: 30rpx; height: 30rpx; line-height: 30rpx; text-align: center; border-radius: 50%; color: #fff; font-size: 20rpx; flex-shrink: 0; }
.ttype { font-size: 24rpx; font-weight: 700; }
.ttext { font-size: 24rpx; color: #555; line-height: 1.4; }

/* 子节点行 + 连线(org-chart 经典做法) */
.tchildren { display: flex; justify-content: center; padding-top: 40rpx; position: relative; }
/* 父盒子底部向下的竖线 */
.tchildren::before { content: ''; position: absolute; top: 0; left: 50%; width: 0; height: 40rpx; border-left: 2rpx solid #cfd6e0; }
/* 每个子节点:顶部到横向母线的连线 */
.tchildren > .tnode { padding-top: 40rpx; }
.tchildren > .tnode::before,
.tchildren > .tnode::after { content: ''; position: absolute; top: 0; right: 50%; width: 50%; height: 40rpx; border-top: 2rpx solid #cfd6e0; }
.tchildren > .tnode::after { right: auto; left: 50%; border-left: 2rpx solid #cfd6e0; }
/* 单子节点:不要左右横线,只留竖线 */
.tchildren > .tnode:only-child::before,
.tchildren > .tnode:only-child::after { display: none; }
.tchildren > .tnode:only-child { padding-top: 40rpx; }
.tchildren > .tnode:only-child::before { display: block; border-top: none; border-left: 2rpx solid #cfd6e0; width: 0; left: 50%; height: 40rpx; }
/* 首/末子节点:外侧不画横线(避免出头) */
.tchildren > .tnode:first-child::before { border: none; }
.tchildren > .tnode:last-child::after { border: none; }
</style>
