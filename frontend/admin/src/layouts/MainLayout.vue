<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch, type Component } from 'vue'
import { Close, RefreshRight } from '@element-plus/icons-vue'
import {
  Collection, Document, Headset, User, UserFilled, Coin, Setting,
  Histogram, Connection, Cpu, Phone,
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
      { path: '/textbook-catalog', label: '教材版本维护' },
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
      { path: '/grammar-usage', label: '语法使用统计' },
      { path: '/grammar-calibration', label: '语法判定校准(R10)' },
      { path: '/kp-prompts', label: '习题匹配知识脑图提示词' },
    ] },
    { title: '句子 / 写作', items: [
      { path: '/long-sentences', label: '长难句管理' },
      { path: '/essay-templates', label: '作文模板' },
    ] },
  ] },
  { key: 'g-vocab', title: '词汇 / 词力通', icon: Document, items: [
    { path: '/vocab-lists', label: '通用词库' },
    { path: '/vocab-reviews', label: '缺词审核入库' },
    { path: '/textbook-word-stats', label: '教材高频词统计' },
    { path: '/vocab-media', label: '词力通媒体' },
    { path: '/vocab-image-gen', label: '词力通配图' },
    { path: '/kp-mcq-review', label: '考点题复核' },
    { path: '/kp-review', label: '考点复核' },
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
  { key: 'g-sales', title: '销售 / 电销 CRM', icon: Phone, items: [
    { path: '/sales-leads', label: '电销线索' },
    { path: '/reach', label: '存量召回 / 触达' },
    { path: '/baidu-leads', label: '地图获客' },
    { path: '/textbook-map', label: '教材版本地图' },
    { path: '/sales-call-center', label: '呼叫中心接入' },
  ] },
  { key: 'g-finance', title: '营收 / 财务', icon: Coin, items: [
    { path: '/pricing', label: '定价配置' },
    { path: '/entitlements', label: '会员权益配置' },
    { path: '/refunds', label: '退款 / 申诉审核' },
    { path: '/approvals', label: '敏感操作审批' },
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
    { path: '/third-party', label: '第三方 API 资源', icon: Cpu },
    { path: '/llm-config', label: '模型配置', icon: Cpu },
    { path: '/llm-features', label: 'LLM 调用清单', icon: Cpu },
    { path: '/sensitive-words', label: '敏感词库' },
    { path: '/regions', label: '地区管理' },
    { path: '/system-settings', label: '系统参数' },
    { path: '/audit-logs', label: '操作审计' },
    { path: '/task-runs', label: '定时任务健康' },
    { path: '/admin-accounts', label: '账号与权限' },
  ] },
]

// 默认展开全部分组（含二级子类）：保证所有页面可见、不被折叠或裁切
const defaultOpeneds = navGroups.flatMap(g =>
  [g.key, ...(g.subs ? g.subs.map((_, i) => `${g.key}-${i}`) : [])])

// ── 模块权限(RBAC):按 /admin/me 的 modules 过滤菜单 ─────────────────────────
// 分组 key → 后端模块键(app/core/module_map.MODULES);modules=null 全权显示全部
const GROUP_MODULE: Record<string, string> = {
  'g-content': 'content', 'g-vocab': 'vocab', 'g-speak': 'speak',
  'g-teacher': 'teacher_inst', 'g-ops': 'ops', 'g-sales': 'sales',
  'g-finance': 'finance', 'g-support': 'support', 'g-system': 'system',
}
const myModules = ref<string[] | null>(null)   // null=全权(默认按全权渲染,拿到 me 后收紧)
const isSuper = computed(() => myModules.value === null)
const visibleGroups = computed(() => {
  let groups = navGroups
  if (myModules.value !== null) {
    groups = groups.filter(g => myModules.value!.includes(GROUP_MODULE[g.key] || ''))
  }
  // 「账号与权限」仅超管可见
  if (!isSuper.value) {
    groups = groups.map(g => g.key !== 'g-system' ? g : {
      ...g, items: (g.items || []).filter(it => it.path !== '/admin-accounts'),
    })
  }
  return groups
})
onMounted(async () => {
  try {
    const { adminMe } = await import('../api/admin')
    myModules.value = (await adminMe()).modules
  } catch { /* 拿不到 me 不拦(接口侧仍有强制) */ }
})

function onLogout() {
  auth.logout()
  router.push('/login')
}

// ── 浏览器式多标签页(tagsView)──────────────────────────────────────────────
// path → 标题(取菜单 label;数据大盘单列)
const HOME = '/overview'
const pathTitle: Record<string, string> = { [HOME]: '数据大盘' }
for (const g of navGroups) {
  for (const it of g.items || []) pathTitle[it.path] = it.label
  for (const s of g.subs || []) for (const it of s.items) pathTitle[it.path] = it.label
}
const titleOf = (p: string) => pathTitle[p] || p

const tabs = ref<{ path: string; title: string }[]>([])
function addTab(p: string) {
  if (!p || p === '/login') return
  if (!tabs.value.some(t => t.path === p)) tabs.value.push({ path: p, title: titleOf(p) })
}
watch(() => route.path, p => addTab(p), { immediate: true })

function goTab(p: string) { if (p !== route.path) router.push(p) }
function closeTab(p: string) {
  const i = tabs.value.findIndex(t => t.path === p)
  if (i < 0) return
  tabs.value.splice(i, 1)
  if (p === route.path) router.push((tabs.value[i] || tabs.value[i - 1])?.path || HOME)
}
function ensureCurrent() {
  if (!tabs.value.some(t => t.path === route.path)) router.push(tabs.value[0]?.path || HOME)
}

// 内容刷新:切 router-view 的 v-if 重挂载当前页
const viewAlive = ref(true)
async function reloadView() { viewAlive.value = false; await nextTick(); viewAlive.value = true }

// 右键菜单
const ctx = ref({ visible: false, x: 0, y: 0, path: '' })
function openCtx(e: MouseEvent, p: string) { e.preventDefault(); ctx.value = { visible: true, x: e.clientX, y: e.clientY, path: p } }
function closeCtx() { ctx.value.visible = false }
async function ctxDo(act: 'refresh' | 'close' | 'left' | 'right' | 'others' | 'all') {
  const p = ctx.value.path
  const i = tabs.value.findIndex(t => t.path === p)
  closeCtx()
  if (act === 'refresh') { if (p !== route.path) await router.push(p); await reloadView(); return }
  if (act === 'close') { closeTab(p); return }
  if (act === 'others') tabs.value = tabs.value.filter(t => t.path === p)
  else if (act === 'left') tabs.value = tabs.value.filter((_, idx) => idx >= i)
  else if (act === 'right') tabs.value = tabs.value.filter((_, idx) => idx <= i)
  else if (act === 'all') tabs.value = []
  ensureCurrent()
}
onMounted(() => window.addEventListener('click', closeCtx))
onBeforeUnmount(() => window.removeEventListener('click', closeCtx))
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
        <el-sub-menu v-for="g in visibleGroups" :key="g.key" :index="g.key">
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
      <!-- 浏览器式多标签页 -->
      <div class="tabs-bar">
        <div
          v-for="t in tabs" :key="t.path"
          class="tab" :class="{ active: t.path === route.path }"
          @click="goTab(t.path)" @contextmenu="openCtx($event, t.path)"
        >
          <span class="tab-title">{{ t.title }}</span>
          <el-icon class="tab-close" @click.stop="closeTab(t.path)"><Close /></el-icon>
        </div>
      </div>

      <el-main>
        <router-view v-if="viewAlive" />
      </el-main>
    </el-container>

    <!-- 标签右键菜单 -->
    <ul v-if="ctx.visible" class="tab-ctx" :style="{ left: ctx.x + 'px', top: ctx.y + 'px' }" @click.stop>
      <li @click="ctxDo('refresh')"><el-icon><RefreshRight /></el-icon>刷新</li>
      <li @click="ctxDo('close')"><el-icon><Close /></el-icon>关闭</li>
      <li class="div" />
      <li @click="ctxDo('left')">关闭左侧</li>
      <li @click="ctxDo('right')">关闭右侧</li>
      <li @click="ctxDo('others')">关闭其他</li>
      <li @click="ctxDo('all')">全部关闭</li>
    </ul>
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
/* 多标签页 */
.tabs-bar { display: flex; align-items: center; gap: 4px; padding: 6px 10px;
  background: #f5f7fa; border-bottom: 1px solid #e6e8eb; overflow-x: auto; flex-shrink: 0; }
.tabs-bar::-webkit-scrollbar { height: 4px; }
.tabs-bar::-webkit-scrollbar-thumb { background: #c8ccd2; border-radius: 2px; }
.tab { display: flex; align-items: center; gap: 6px; padding: 4px 10px; font-size: 13px;
  background: #fff; border: 1px solid #e0e3e8; border-radius: 4px; cursor: pointer;
  color: #606266; white-space: nowrap; user-select: none; }
.tab:hover { color: #409eff; }
.tab.active { color: #fff; background: #409eff; border-color: #409eff; }
.tab-title { line-height: 18px; }
.tab-close { font-size: 12px; border-radius: 50%; }
.tab-close:hover { background: rgba(0,0,0,0.12); }
.tab.active .tab-close:hover { background: rgba(255,255,255,0.3); }
.tab-ctx { position: fixed; z-index: 3000; min-width: 130px; margin: 0; padding: 4px 0;
  list-style: none; background: #fff; border: 1px solid #e4e7ed; border-radius: 6px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.12); font-size: 13px; }
.tab-ctx li { display: flex; align-items: center; gap: 6px; padding: 7px 14px; cursor: pointer; color: #303133; }
.tab-ctx li:hover { background: #f0f7ff; color: #409eff; }
.tab-ctx li.div { height: 1px; padding: 0; margin: 4px 0; background: #f0f2f5; cursor: default; }
.tab-ctx li.div:hover { background: #f0f2f5; }
</style>
