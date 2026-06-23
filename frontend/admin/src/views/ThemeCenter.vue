<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { listThemes, setActiveTheme, setBranding, type ThemePreset } from '../api/admin'
import { branding, loadBranding } from '../branding'
import { PriceTag, Brush, CircleCheck } from '@element-plus/icons-vue'

const themes = ref<ThemePreset[]>([])
const activeKey = ref('')
const loading = ref(true)
const saving = ref('')

// 项目名称
const appNameInput = ref('')
const savingName = ref(false)
async function saveAppName() {
  if (!appNameInput.value.trim()) { ElMessage.warning('项目名称不能为空'); return }
  savingName.value = true
  try {
    await setBranding({ app_name: appNameInput.value.trim(), slogan: branding.slogan })
    await loadBranding()
    ElMessage.success('项目名称已更新，各端下次启动生效')
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  } finally { savingName.value = false }
}

async function load() {
  loading.value = true
  try {
    const r = await listThemes()
    themes.value = r.themes
    activeKey.value = r.active_key
  } catch (e: any) {
    ElMessage.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function choose(t: ThemePreset) {
  if (saving.value) return
  saving.value = t.key
  try {
    await setActiveTheme(t.key)
    activeKey.value = t.key
    ElMessage.success(`已将「${t.name}」设为上线主题，小程序下次启动生效`)
  } catch (e: any) {
    ElMessage.error(e?.message || '设置失败')
  } finally {
    saving.value = ''
  }
}

onMounted(async () => {
  await load()
  appNameInput.value = branding.app_name
})
</script>

<template>
  <div class="theme-center">
    <div class="brand-box">
      <h2><el-icon style="vertical-align:-2px;margin-right:4px"><PriceTag /></el-icon>项目名称</h2>
      <p class="sub">全系统唯一项目名，各前端（小程序/后台）启动统一读取。改后下次启动生效。</p>
      <div class="brand-row">
        <el-input v-model="appNameInput" placeholder="如 engGramer" style="max-width:320px" />
        <el-button type="primary" :loading="savingName" @click="saveAppName">保存</el-button>
        <span class="brand-cur">当前：{{ branding.app_name }}</span>
      </div>
    </div>

    <div class="head">
      <h2><el-icon style="vertical-align:-2px;margin-right:4px"><Brush /></el-icon>主题中心</h2>
      <p class="sub">挑选小程序的上线视觉风格。选中后写入配置，小程序下次启动自动应用。</p>
    </div>

    <div v-loading="loading" class="gallery">
      <div
        v-for="t in themes"
        :key="t.key"
        class="theme-card"
        :class="{ active: t.key === activeKey }"
      >
        <div v-if="t.key === activeKey" class="badge-active">上线中</div>

        <!-- 手机样机预览（用主题真实颜色渲染） -->
        <div class="mock" :style="{ background: t.tokens.c_bg_page }">
          <div class="mock-title">engGramer</div>
          <!-- hero 渐变卡 -->
          <div class="mock-hero" :style="{ background: t.tokens.g_hero, boxShadow: t.tokens.shadow_primary.replace(/rpx/g,'px') }">
            <span class="mock-hero-ic">📖</span>
            <div class="mock-hero-tx"><b>开始学习</b><small>选择教材开始</small></div>
          </div>
          <!-- 卡片 + 进度 -->
          <div class="mock-block">
            <div class="mock-row">
              <span style="font-weight:700;color:#1d2b33">今日学习计划</span>
              <span :style="{ color: t.tokens.c_primary, fontWeight:700 }">0/4 完成</span>
            </div>
            <div class="mock-bar"><i :style="{ width:'45%', background: t.tokens.c_primary }" /></div>
            <div class="mock-chips">
              <span class="chip" :style="{ background: t.tokens.c_primary_soft, color: t.tokens.c_primary_deep }">薄弱点</span>
              <span class="chip" :style="{ background: t.tokens.c_bg_soft, color:'#6f7d86' }">练习</span>
            </div>
          </div>
          <!-- 色板 -->
          <div class="swatches">
            <i :style="{ background: t.tokens.c_primary }" />
            <i :style="{ background: t.tokens.c_primary_deep }" />
            <i :style="{ background: t.tokens.c_gold }" />
            <i :style="{ background: t.tokens.c_accent }" />
          </div>
        </div>

        <div class="meta">
          <div class="name">{{ t.name }}</div>
          <div class="desc">{{ t.desc }}</div>
        </div>
        <el-button
          :type="t.key === activeKey ? 'success' : 'primary'"
          :plain="t.key !== activeKey"
          :loading="saving === t.key"
          :disabled="t.key === activeKey"
          @click="choose(t)"
        >
          <el-icon v-if="t.key === activeKey" style="vertical-align:-2px;margin-right:4px"><CircleCheck /></el-icon>{{ t.key === activeKey ? '当前上线' : '设为上线' }}
        </el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.theme-center { padding: 8px 4px; }
.head h2 { margin: 0 0 4px; }
.sub { color: #909399; font-size: 14px; margin: 0 0 20px; }
.brand-box { background: #fff; border: 1px solid #ebeef5; border-radius: 8px; padding: 16px 20px; margin-bottom: 24px; }
.brand-box h2 { margin: 0 0 4px; font-size: 18px; }
.brand-row { display: flex; align-items: center; gap: 12px; }
.brand-cur { color: #909399; font-size: 13px; }
.gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px; }
.theme-card {
  position: relative; background: #fff; border: 2px solid #ebeef5; border-radius: 16px;
  padding: 16px; display: flex; flex-direction: column; gap: 12px; transition: all .2s;
}
.theme-card.active { border-color: #67c23a; box-shadow: 0 8px 24px rgba(103,194,58,.15); }
.badge-active { position: absolute; top: 12px; right: 12px; background: #67c23a; color: #fff; font-size: 12px; padding: 2px 10px; border-radius: 999px; z-index: 2; }
.mock { border-radius: 14px; padding: 16px; display: flex; flex-direction: column; gap: 12px; }
.mock-title { text-align: center; font-weight: 800; color: #1d2b33; }
.mock-hero { border-radius: 14px; padding: 14px 16px; display: flex; align-items: center; gap: 12px; color: #fff; }
.mock-hero-ic { font-size: 26px; }
.mock-hero-tx { display: flex; flex-direction: column; }
.mock-hero-tx b { font-size: 16px; }
.mock-hero-tx small { opacity: .85; font-size: 12px; }
.mock-block { background: #fff; border-radius: 12px; padding: 12px; box-shadow: 0 4px 16px rgba(20,70,90,.06); display: flex; flex-direction: column; gap: 8px; }
.mock-row { display: flex; justify-content: space-between; font-size: 13px; }
.mock-bar { height: 8px; background: #eef2f4; border-radius: 999px; overflow: hidden; }
.mock-bar i { display: block; height: 100%; border-radius: 999px; }
.mock-chips { display: flex; gap: 8px; }
.chip { font-size: 12px; padding: 2px 12px; border-radius: 999px; }
.swatches { display: flex; gap: 8px; }
.swatches i { width: 28px; height: 28px; border-radius: 8px; box-shadow: inset 0 0 0 1px rgba(0,0,0,.06); }
.meta .name { font-weight: 700; font-size: 16px; color: #303133; }
.meta .desc { font-size: 13px; color: #909399; margin-top: 2px; }
</style>
