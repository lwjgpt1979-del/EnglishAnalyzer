<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { computed, type Component } from 'vue'
import {
  Collection, Document, Headset, User, UserFilled, Coin, Setting,
  Histogram, Connection, Cpu,
} from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'
import { branding } from '../branding'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const active = computed(() => route.path)

// 导航分组：所有页面按业务归类，默认全部展开、可折叠，侧栏可滚动。
// 项多的分组(如内容生产)可再分二级子类(subs);否则直接 items。
interface NavItem { path: string; label: string; icon?: Component }
interface NavSub { title: string; items: NavItem[] }
interface NavGroup { key: string; title: string; icon: Component; items?: NavItem[]; subs?: NavSub[] }

const navGroups: NavGroup[] = [
  { key: 'g-content', title: '内容生产', icon: Collection, subs: [
    { title: '课程 / 教材', items: [
      { path: '/curriculum-units', label: '课程内容生成' },
      { path: '/curriculum-gen-jobs', label: '课程生成任务' },
    ] },
    { title: '真题 / 仿真', items: [
      { path: '/platform-questions', label: '平台真题(上传真题)' },
      { path: '/questions', label: '仿真题审核' },
    ] },
    { title: '知识图谱 / 考点', items: [
      { path: '/kp-candidates', label: '候选知识点审核' },
      { path: '/knowledge-graph', label: '知识图谱(节点总览)', icon: Connection },
      { path: '/exam-type-stats', label: '考试类型统计' },
      { path: '/kp-prompts', label: '习题匹配知识脑图提示词' },
      { path: '/node-resources', label: '知识点资源' },
      { path: '/lecture-split', label: '详解拆分审核' },
    ] },
    { title: '句子 / 写作', items: [
      { path: '/long-sentences', label: '长难句管理' },
      { path: '/essay-templates', label: '作文模板' },
    ] },
  ] },
  { key: 'g-vocab', title: '词汇 / 词力通', icon: Document, items: [
    { path: '/vocab-lists', label: '通用词库' },
    { path: '/textbook-word-stats', label: '教材高频词统计' },
    { path: '/vocab-media', label: '词力通媒体' },
    { path: '/vocab-image-gen', label: '词力通配图' },
  ] },
  { key: 'g-speak', title: '口语 / 听力 / 主题', icon: Headset, items: [
    { path: '/speaking-scenarios', label: '口语场景' },
    { path: '/tts-speed', label: '听力语音' },
    { path: '/tts-usage', label: 'TTS 用量 / 预热' },
    { path: '/theme-center', label: '主题中心' },
  ] },
  { key: 'g-teacher', title: '教师 / 机构', icon: User, items: [
    { path: '/teacher-cert', label: '教师认证审核' },
    { path: '/teacher-limits', label: '老师限额配置' },
    { path: '/institutions', label: '机构审核' },
    { path: '/institution-packages', label: '机构套餐' },
  ] },
  { key: 'g-ops', title: '用户 / 运营', icon: UserFilled, items: [
    { path: '/users', label: '用户管理' },
    { path: '/ban-appeals', label: '封禁申诉' },
    { path: '/coupons', label: '优惠券' },
    { path: '/campaigns', label: '限时活动价' },
    { path: '/announcements', label: '公告管理' },
    { path: '/notifications', label: '通知' },
  ] },
  { key: 'g-finance', title: '营收 / 财务', icon: Coin, items: [
    { path: '/pricing', label: '定价配置' },
    { path: '/entitlements', label: '会员权益配置' },
    { path: '/refunds', label: '退款 / 申诉审核' },
    { path: '/payment-accounts', label: '收款主体' },
    { path: '/branch-companies', label: '分公司管理' },
    { path: '/finance', label: '财务管理' },
    { path: '/invoices', label: '发票申请' },
  ] },
  { key: 'g-support', title: '支持 / 反馈', icon: Headset, items: [
    { path: '/support', label: '客服工单' },
    { path: '/faq', label: 'FAQ 管理' },
    { path: '/feedback', label: '意见反馈' },
    { path: '/content-feedback', label: '内容反馈' },
  ] },
  { key: 'g-system', title: '系统配置', icon: Setting, items: [
    { path: '/llm-config', label: '模型配置', icon: Cpu },
    { path: '/sensitive-words', label: '敏感词库' },
    { path: '/regions', label: '地区管理' },
    { path: '/system-settings', label: '系统参数' },
  ] },
]

// 默认展开全部分组（含二级子类）：保证所有页面可见、不被折叠或裁切
const defaultOpeneds = navGroups.flatMap(g =>
  [g.key, ...(g.subs ? g.subs.map((_, i) => `${g.key}-${i}`) : [])])

function onLogout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <el-container style="height: 100vh">
    <el-aside width="220px" class="aside">
      <div class="logo">{{ branding.app_name }} 运营</div>
      <el-menu
        :default-active="active"
        :default-openeds="defaultOpeneds"
        router
        class="side-menu"
        background-color="#001529"
        text-color="rgba(255,255,255,0.75)"
        active-text-color="#ffffff"
      >
        <el-menu-item index="/overview">
          <el-icon><Histogram /></el-icon>
          <span>数据大盘</span>
        </el-menu-item>
        <el-sub-menu v-for="g in navGroups" :key="g.key" :index="g.key">
          <template #title>
            <el-icon><component :is="g.icon" /></el-icon>
            <span>{{ g.title }}</span>
          </template>
          <!-- 有二级子类:再嵌一层子菜单 -->
          <template v-if="g.subs">
            <el-sub-menu v-for="(s, si) in g.subs" :key="`${g.key}-${si}`" :index="`${g.key}-${si}`">
              <template #title>{{ s.title }}</template>
              <el-menu-item v-for="it in s.items" :key="it.path" :index="it.path">
                <el-icon v-if="it.icon"><component :is="it.icon" /></el-icon>
                <span>{{ it.label }}</span>
              </el-menu-item>
            </el-sub-menu>
          </template>
          <!-- 普通分组:直接列项 -->
          <template v-else>
            <el-menu-item v-for="it in g.items" :key="it.path" :index="it.path">
              <el-icon v-if="it.icon"><component :is="it.icon" /></el-icon>
              <span>{{ it.label }}</span>
            </el-menu-item>
          </template>
        </el-sub-menu>
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
.aside { background: #001529; overflow-y: auto; overflow-x: hidden; }
/* 暗色滚动条，避免在深色侧栏上突兀 */
.aside::-webkit-scrollbar { width: 6px; }
.aside::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.18); border-radius: 3px; }
.aside::-webkit-scrollbar-track { background: transparent; }
.logo { color: #fff; font-weight: 700; text-align: center; padding: 18px 0; font-size: 16px; position: sticky; top: 0; background: #001529; z-index: 1; }
.side-menu { width: 100%; border-right: none; }
.header { display: flex; align-items: center; background: #fff; border-bottom: 1px solid #eee; }
.spacer { flex: 1; }
</style>
