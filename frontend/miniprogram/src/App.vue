<!-- src/App.vue -->
<script setup lang="ts">
import { onLaunch } from '@dcloudio/uni-app'

onLaunch(() => {
  // Token is restored from storage by the Pinia auth store on init.
  // We do NOT force-login on launch — let users explore the home page first.
  console.log('[App] launched')
})
</script>

<template>
  <layout />
</template>

<style>
/* ====================================================================
   engGramer 全局 Design Tokens —— 黄油相机风 v0.2（决策 D-071）
   定义在 page 选择器上，微信小程序支持 CSS 自定义变量，全页面可用 var()。
   单位为 rpx（小程序 750rpx = 屏宽）。规范见 docs/design/style-guide.html
   ==================================================================== */
page {
  /* —— 品牌 / 黄系 —— */
  --c-primary: #fbe26b;        /* 主色：主按钮底（按钮文字用墨黑！） */
  --c-primary-soft: #fcefa9;   /* 主色浅：禁用 / 浅填充 / 黄标签底 */
  --c-primary-faint: #fffbe8;  /* 主色极浅：选中底 / 批注底 */
  --c-gold: #fbc53d;           /* 金黄强调：激活 / 图标 / 下划线 / 进度 */
  --c-olive: #c9c96e;          /* 橄榄黄：二级按钮 / 标签 */
  --c-orange: #f2913e;         /* 暖橙：点赞 / 通知 / 吉祥物 */

  /* —— 墨色 / 文字 —— */
  --c-ink: #1f1f1f;            /* 墨黑：大标题 / 黄按钮上的字 */
  --c-surface-dark: #1c1c1c;   /* 深色编辑区块（白字） */
  --c-text-body: #333333;      /* 正文 */
  --c-text-second: #7a7a7a;    /* 次要文字 */
  --c-text-hint: #b5b5b5;      /* 提示 / 占位 */

  /* —— 背景 / 描边 —— */
  --c-bg-page: #f6f5f1;        /* 页面背景：暖白 */
  --c-bg-card: #ffffff;        /* 卡片背景 */
  --c-bg-soft: #f5f4f1;        /* 搜索框 / chips / 浅块 */
  --c-border: #ededeb;         /* 描边 / 分割线 */

  /* —— 语义色 —— */
  --c-success: #5fb878;
  --c-success-bg: #eef8f0;
  --c-success-dark: #3f9159;
  --c-danger: #f0603c;
  --c-danger-bg: #fdeee9;
  --c-danger-dark: #c8401f;

  /* —— 字号（rpx）—— */
  --fs-display: 60rpx;
  --fs-h1: 36rpx;
  --fs-h2: 30rpx;
  --fs-body: 28rpx;
  --fs-sm: 26rpx;
  --fs-aux: 24rpx;
  --fs-tiny: 22rpx;

  /* —— 间距（rpx）—— */
  --sp-1: 8rpx;
  --sp-2: 16rpx;
  --sp-3: 24rpx;
  --sp-4: 32rpx;
  --sp-5: 48rpx;

  /* —— 圆角（rpx）—— */
  --r-sm: 16rpx;     /* 小标签 */
  --r-md: 28rpx;     /* 输入框 / 控件 */
  --r-btn: 32rpx;    /* 按钮 */
  --r-lg: 40rpx;     /* 卡片 */
  --r-xl: 56rpx;     /* 弹窗 / 大卡片 */
  --r-pill: 999rpx;  /* 胶囊 */

  background: var(--c-bg-page);
  color: var(--c-text-body);
}
</style>
