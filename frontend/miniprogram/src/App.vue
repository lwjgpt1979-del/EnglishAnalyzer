<!-- src/App.vue -->
<script setup lang="ts">
import { onLaunch } from '@dcloudio/uni-app'
import { request } from '@/utils/request'
import { useAuthStore } from '@/stores/auth'
import { useBrandingStore } from '@/stores/branding'

// M11：启动拉取平台上线主题，H5 注入 CSS 变量（小程序见 build 期 token）
async function applyActiveTheme() {
  try {
    const data = await request<{ key: string; name: string; tokens: Record<string, string> }>(
      '/api/v1/config/theme', { method: 'GET' },
    )
    const t = data?.tokens
    if (!t) return
    // #ifdef H5
    const id = 'app-active-theme'
    let el = document.getElementById(id) as HTMLStyleElement | null
    if (!el) { el = document.createElement('style'); el.id = id; document.head.appendChild(el) }
    el.textContent = `page,uni-page-body{
      --c-primary:${t.c_primary}!important;--c-primary-deep:${t.c_primary_deep}!important;
      --c-primary-soft:${t.c_primary_soft}!important;--c-primary-faint:${t.c_primary_faint}!important;
      --c-gold:${t.c_gold}!important;--c-accent:${t.c_accent}!important;--c-olive:${t.c_olive}!important;
      --c-bg-page:${t.c_bg_page}!important;--c-bg-soft:${t.c_bg_soft}!important;--c-border:${t.c_border}!important;
      --g-primary:${t.g_primary}!important;--g-hero:${t.g_hero}!important;--shadow-primary:${t.shadow_primary}!important;
    }`
    // #endif
  } catch { /* 主题拉取失败用 App.vue 内置默认，不影响使用 */ }
}

async function checkBan() {
  // 被封用户(token 仍有效)→ 跳封禁说明/申诉页（§5.3.1）
  try {
    const { getBanStatus } = await import('@/api/ban')
    const s = await getBanStatus()
    if (s?.banned) uni.reLaunch({ url: '/pages/account/ban' })
  } catch { /* 未登录或网络异常忽略 */ }
}

onLaunch((options) => {
  console.log('[App] launched')
  // 获客渠道（§5.5）：扫码/分享带 ?channel=school|stationery|training|search|referral|other
  // 落地暂存，首次 wx-login 时上报；仅在尚无记录时写入（保留最早来源）
  const ch = (options?.query as Record<string, string> | undefined)?.channel
  const VALID = ['school', 'stationery', 'training', 'search', 'referral', 'other']
  if (ch && VALID.includes(ch) && !uni.getStorageSync('acq_channel')) {
    uni.setStorageSync('acq_channel', ch)
  }
  applyActiveTheme()
  useBrandingStore().fetch()   // 项目名从后端统一读取
  // 已有 token → 恢复用户信息（个人页等依赖 auth.user）
  useAuthStore().restore()
  checkBan()
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
  /* —— 品牌 / 天空蓝系（v0.3 清新活力·上线主题）—— */
  --c-primary: #3d8bf5;        /* 主色：天空蓝（白字！见 --c-on-primary） */
  --c-primary-deep: #2b6fd6;   /* 主色深：渐变末端 / 按下态 */
  --c-primary-soft: #dbe9ff;   /* 主色浅：浅填充 / 标签底 */
  --c-primary-faint: #eef5ff;  /* 主色极浅：选中底 / 批注底 */
  --c-on-primary: #ffffff;     /* 主色之上的文字（白） */
  --c-gold: #ffb020;           /* 暖琥珀强调：XP / 星标 / 进度 / 激活 */
  --c-accent: #ff7a59;         /* 珊瑚橙：点赞 / 重点高亮 */
  --c-olive: #6ec0ff;          /* 浅天蓝：二级按钮 / 标签 */
  --c-orange: #ff8a3d;         /* 暖橙：通知 / 吉祥物 */

  /* —— 墨色 / 文字（冷调石板，更现代）—— */
  --c-ink: #1d2b33;            /* 深石板：大标题 */
  --c-surface-dark: #18242b;   /* 深色编辑区块（白字） */
  --c-text-body: #34424a;      /* 正文 */
  --c-text-second: #6f7d86;    /* 次要文字 */
  --c-text-hint: #a6b1b8;      /* 提示 / 占位 */

  /* —— 背景 / 描边（清爽冷白）—— */
  --c-bg-page: #f1f5fc;        /* 页面背景：清爽冷白 */
  --c-bg-card: #ffffff;        /* 卡片背景 */
  --c-bg-soft: #eaf1fb;        /* 搜索框 / chips / 浅块 */
  --c-border: #e2eaf5;         /* 描边 / 分割线 */

  /* —— 语义色 —— */
  --c-success: #2fc58a;
  --c-success-bg: #e6f9f1;
  --c-success-dark: #1f9e6e;
  --c-danger: #ff5a5f;
  --c-danger-bg: #ffe9ea;
  --c-danger-dark: #d63d42;

  /* —— 渐变 —— */
  --g-primary: linear-gradient(135deg, #5aa0ff 0%, #3570e0 100%);
  --g-hero: linear-gradient(135deg, #62a8ff 0%, #2f6fe0 100%);
  --g-warm: linear-gradient(135deg, #ffcf6e 0%, #ff9d4d 100%);

  /* —— 阴影（统一柔和层级）—— */
  --shadow-sm: 0 4rpx 16rpx rgba(30, 70, 120, 0.06);
  --shadow-md: 0 10rpx 36rpx rgba(30, 70, 120, 0.10);
  --shadow-primary: 0 10rpx 28rpx rgba(43, 111, 214, 0.30);

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

  /* —— 圆角（rpx，整体更圆润）—— */
  --r-sm: 16rpx;     /* 小标签 */
  --r-md: 28rpx;     /* 输入框 / 控件 */
  --r-btn: 36rpx;    /* 按钮 */
  --r-lg: 44rpx;     /* 卡片 */
  --r-xl: 56rpx;     /* 弹窗 / 大卡片 */
  --r-pill: 999rpx;  /* 胶囊 */

  background: var(--c-bg-page);
  color: var(--c-text-body);

  /* —— 中文字体栈 + 抗锯齿(全局观感)—— */
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB",
    "Microsoft YaHei", "Source Han Sans SC", "Noto Sans CJK SC", "WenQuanYi Micro Hei", sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-rendering: optimizeLegibility;
}

/* H5:确保 body 同字体与抗锯齿(部分组件挂在 body 下) */
uni-page-body, body {
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB",
    "Microsoft YaHei", "Source Han Sans SC", "Noto Sans CJK SC", "WenQuanYi Micro Hei", sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
</style>
