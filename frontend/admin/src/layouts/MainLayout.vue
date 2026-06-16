<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { computed } from 'vue'
import { useAuthStore } from '../stores/auth'
import { branding } from '../branding'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const active = computed(() => route.path)

function onLogout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <el-container style="height: 100vh">
    <el-aside width="200px" class="aside">
      <div class="logo">{{ branding.app_name }} 运营</div>
      <el-menu
        :default-active="active"
        router
        class="side-menu"
        background-color="#001529"
        text-color="rgba(255,255,255,0.75)"
        active-text-color="#ffffff"
      >
        <el-menu-item index="/overview">数据大盘</el-menu-item>
        <el-menu-item index="/curriculum-units">📚 课程内容生成</el-menu-item>
        <el-menu-item index="/theme-center">🎨 主题中心</el-menu-item>
        <el-menu-item index="/vocab-media">🔤 词力通媒体</el-menu-item>
        <el-menu-item index="/teacher-cert">👨‍🏫 教师认证审核</el-menu-item>
        <el-menu-item index="/questions">仿真题审核</el-menu-item>
        <el-menu-item index="/content-feedback">📝 内容反馈</el-menu-item>
        <el-menu-item index="/support">🎧 客服工单</el-menu-item>
        <el-menu-item index="/faq">❓ FAQ 管理</el-menu-item>
        <el-menu-item index="/feedback">💡 意见反馈</el-menu-item>
        <el-menu-item index="/coupons">🎟️ 优惠券</el-menu-item>
        <el-menu-item index="/sensitive-words">🛡️ 敏感词库</el-menu-item>
        <el-menu-item index="/contents">知识点内容审核</el-menu-item>
        <el-menu-item index="/pricing">定价配置</el-menu-item>
        <el-menu-item index="/campaigns">🎉 限时活动价</el-menu-item>
        <el-menu-item index="/entitlements">🔐 会员权益配置</el-menu-item>
        <el-menu-item index="/refunds">💸 退款/申诉审核</el-menu-item>
        <el-menu-item index="/payment-accounts">🏦 收款主体</el-menu-item>
        <el-menu-item index="/branch-companies">🏢 分公司管理</el-menu-item>
        <el-menu-item index="/users">👥 用户管理</el-menu-item>
        <el-menu-item index="/ban-appeals">🛡️ 封禁申诉</el-menu-item>
        <el-menu-item index="/finance">💰 财务管理</el-menu-item>
        <el-menu-item index="/invoices">🧾 发票申请</el-menu-item>
        <el-menu-item index="/tts-speed">🔊 听力语音</el-menu-item>
        <el-menu-item index="/tts-usage">📊 TTS 用量/预热</el-menu-item>
        <el-menu-item index="/speaking-scenarios">💬 口语场景</el-menu-item>
        <el-menu-item index="/vocab-image-gen">🖼️ 词力通配图</el-menu-item>
        <el-menu-item index="/essay-templates">作文模板</el-menu-item>
        <el-menu-item index="/institutions">机构审核</el-menu-item>
        <el-menu-item index="/exam-papers">📝 真题试卷管理</el-menu-item>
        <el-menu-item index="/notifications">通知</el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <span class="spacer" />
        <el-button text @click="onLogout">退出登录</el-button>
      </el-header>
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.aside { background: #001529; overflow: hidden; }
.logo { color: #fff; font-weight: 700; text-align: center; padding: 18px 0; font-size: 16px; }
.side-menu { width: 100%; border-right: none; }
.header { display: flex; align-items: center; background: #fff; border-bottom: 1px solid #eee; }
.spacer { flex: 1; }
</style>
