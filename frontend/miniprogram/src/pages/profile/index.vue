<!-- src/pages/profile/index.vue -->
<template>
  <view class="profile-page">

    <!-- 待注销横幅 -->
    <view v-if="cancelInfo" class="cancel-banner" @tap="goCancelPage">
      <text class="cb-text">⏳ 账号将于 {{ cancelInfo.days }} 天后注销</text>
      <text class="cb-action">撤销 ›</text>
    </view>

    <!-- 用户信息 -->
    <view class="card user-card">
      <view v-if="auth.user" class="user-row">
        <image
          v-if="auth.user.avatar_url"
          class="avatar"
          :src="auth.user.avatar_url"
          mode="aspectFill"
        />
        <view v-else class="avatar-placeholder">👤</view>
        <text class="nickname">{{ auth.user.nickname || '英语学习者' }}</text>
      </view>
      <view v-else>
        <button class="btn-login" @tap="auth.login()">微信登录</button>
      </view>
    </view>

    <!-- V2 M23 教材偏好 -->
    <view class="card" v-if="auth.isLoggedIn()">
      <view class="card-title">教材偏好</view>
      <view class="pref-row">
        <text class="pref-label">教材版本</text>
        <text class="pref-val">{{ (auth.user as any)?.preferred_textbook_version || '未设置' }}</text>
      </view>
      <view class="pref-row">
        <text class="pref-label">年级</text>
        <text class="pref-val">{{ (auth.user as any)?.preferred_grade || '未设置' }}</text>
      </view>
      <view class="pref-row">
        <text class="pref-label">学期</text>
        <text class="pref-val">{{ (auth.user as any)?.preferred_semester || '未设置' }}</text>
      </view>
      <view class="pref-row">
        <text class="pref-label">所在城市</text>
        <text class="pref-val">{{ cityDisplayName || '未设置' }}</text>
      </view>
      <button class="btn-menu" style="margin-top:16rpx" @tap="openPrefEdit">修改偏好</button>

      <!-- 编辑弹窗 -->
      <view v-if="showPrefEdit" class="modal" @tap.self="showPrefEdit = false">
        <view class="modal-card">
          <view class="card-title">修改偏好</view>

          <text class="pref-label" style="margin-bottom:8rpx;display:block">教材版本</text>
          <picker :range="TEXTBOOK_VERSIONS" :value="prefForm.textbookIdx" @change="(e: any) => prefForm.textbookIdx = +e.detail.value">
            <view class="picker-row">{{ TEXTBOOK_VERSIONS[prefForm.textbookIdx] }} ›</view>
          </picker>

          <text class="pref-label" style="margin-top:20rpx;margin-bottom:8rpx;display:block">年级</text>
          <picker :range="GRADES" :value="prefForm.gradeIdx" @change="(e: any) => prefForm.gradeIdx = +e.detail.value">
            <view class="picker-row">{{ GRADES[prefForm.gradeIdx] }} ›</view>
          </picker>

          <text class="pref-label" style="margin-top:20rpx;margin-bottom:8rpx;display:block">学期</text>
          <picker :range="SEMESTERS" :value="prefForm.semIdx" @change="(e: any) => prefForm.semIdx = +e.detail.value">
            <view class="picker-row">{{ SEMESTERS[prefForm.semIdx] }} ›</view>
          </picker>

          <text class="pref-label" style="margin-top:20rpx;margin-bottom:8rpx;display:block">省份</text>
          <picker :range="PROVINCE_NAMES" :value="prefForm.provIdx" @change="onProvChange">
            <view class="picker-row">{{ PROVINCE_NAMES[prefForm.provIdx] }} ›</view>
          </picker>

          <text class="pref-label" style="margin-top:20rpx;margin-bottom:8rpx;display:block">城市</text>
          <picker :range="currentCityNames" :value="prefForm.cityIdx" @change="(e: any) => prefForm.cityIdx = +e.detail.value">
            <view class="picker-row">{{ currentCityNames[prefForm.cityIdx] || '—' }} ›</view>
          </picker>

          <button class="btn-primary" style="margin-top:24rpx" :disabled="prefSaving" @tap="onSavePref">
            {{ prefSaving ? '保存中…' : '保存' }}
          </button>
          <button class="btn-secondary" style="margin-top:12rpx" @tap="showPrefEdit = false">取消</button>
        </view>
      </view>
    </view>

    <!-- V2 学期会员（D-079 / M1）-->
    <view class="card">
      <view class="card-title">学期会员</view>
      <text class="menu-desc">按学期购买课程内容（基础 ¥39 / Pro ¥79 / ProMax ¥159 / 学期）。</text>
      <button class="btn-menu" @tap="goBuySemester">按学期购买课程（基础¥39 / Pro¥79 / ProMax¥159）</button>
      <view v-if="mySemesters.length" class="sem-list">
        <view
          v-for="s in mySemesters"
          :key="s.id"
          class="sem-item"
          @tap="goUnits(s)"
        >
          <view class="sem-info">
            <text class="sem-name">{{ s.textbook_version }} {{ s.grade }} {{ s.semester }}</text>
            <text class="sem-tier" :class="`tier-${s.tier}`">{{ tierLabel(s.tier) }}</text>
          </view>
          <view class="sem-right">
            <text class="sem-expires">至 {{ s.expires_at.slice(0, 10) }}</text>
            <text class="chevron">›</text>
          </view>
        </view>
      </view>
      <view v-else>
        <text class="empty-tip">尚未购买任何学期</text>
        <button class="btn-secondary" style="margin-top:16rpx" @tap="goPreviewUnits">免费试读第 1 单元</button>
      </view>
    </view>

    <!-- 机构激活码（D-122）-->
    <view class="card">
      <view class="card-title">机构激活码</view>
      <text class="menu-desc">机构学生：输入机构发放的激活码，激活会员。</text>
      <button class="btn-menu" @tap="() => uni.navigateTo({ url: '/pages/membership/activate' })">输入激活码</button>
    </view>

    <!-- 整卷上传（D-089 / M4）-->
    <view class="card" @tap="goUserPapers">
      <view class="card-title">整卷拆题</view>
      <text class="menu-desc">拍下整张试卷（1~9 张图片），AI 自动识别并拆成单题，错题自动入库。</text>
      <button class="btn-menu" @tap.stop="goUserPapers">拍试卷 / 我的整卷</button>
    </view>

    <!-- 教师中心 -->
    <view class="card" style="margin-top:16rpx;">
      <view class="card-title">教师中心</view>
      <text class="menu-desc">教师功能：生成邀请码、查看学生错题、添加批注；学生功能：绑定老师</text>
      <button class="btn-menu" @tap="goTeacher">进入教师中心</button>
    </view>

    <!-- 家人中心 -->
    <view class="card" @tap="goRelative">
      <view class="card-title">家人中心</view>
      <text class="menu-desc">家长侧：绑定孩子、查看孩子学情、代付会员</text>
      <button class="btn-menu" @tap.stop="goRelative">进入家人中心</button>
    </view>

    <!-- 邀请家人绑定 -->
    <view class="card">
      <view class="card-title">邀请家人绑定</view>
      <text class="menu-desc">家长用微信扫码自动打开小程序绑定；或短信发邀请码。</text>
      <view class="invite-actions">
        <button class="btn-primary half" :disabled="loadingRelQr" @tap="onGenRelQr">
          {{ loadingRelQr ? '生成中…' : '微信扫码' }}
        </button>
        <button class="btn-secondary half" @tap="showRelSms = true">短信邀请</button>
      </view>

      <view v-if="relQr" class="modal" @tap.self="relQr = null">
        <view class="modal-card">
          <image class="qr-img" :src="'data:image/png;base64,' + relQr.qrcode_base64" mode="aspectFit" />
          <text class="qr-tip">家长用微信扫一扫，自动打开并绑定。</text>
          <view class="qr-fallback">
            <text>或手动输入：</text>
            <text class="qr-code">{{ relQr.code }}</text>
            <button size="mini" class="btn-copy" @tap="copyRelCode">复制</button>
          </view>
          <button class="btn-secondary" @tap="relQr = null">关闭</button>
        </view>
      </view>

      <view v-if="showRelSms" class="modal" @tap.self="showRelSms = false">
        <view class="modal-card">
          <view class="card-title">短信邀请家人</view>
          <input v-model="relSmsPhone" class="input" placeholder="家人手机号" maxlength="11" />
          <button class="btn-primary" :disabled="relSmsSending || relSmsPhone.length !== 11" @tap="onSendRelSms">
            {{ relSmsSending ? '发送中…' : '发送' }}
          </button>
          <button class="btn-secondary" @tap="showRelSms = false">取消</button>
        </view>
      </view>
    </view>

    <!-- 已绑定的家人 -->
    <view class="card" v-if="myRelatives.length > 0 || relativesLoaded">
      <view class="card-title">已绑定的家人</view>
      <text class="menu-desc" style="margin-bottom:16rpx;display:block;">以下家人可查看你的学情报告</text>
      <view v-if="myRelatives.length === 0" class="rel-empty">暂无已绑定的家人</view>
      <view v-for="r in myRelatives" :key="r.student_id" class="rel-row">
        <view class="rel-info">
          <text class="rel-name">{{ r.nickname || '家人' }}</text>
          <text class="rel-rel">{{ r.relationship }}</text>
        </view>
        <button
          size="mini"
          class="btn-unbind"
          :disabled="unbindingId === r.student_id"
          @tap.stop="onUnbind(r.student_id)"
        >{{ unbindingId === r.student_id ? '解绑中…' : '解绑' }}</button>
      </view>
    </view>

    <!-- 账号设置 -->
    <view class="card" @tap="goSettings">
      <view class="card-title">账号设置</view>
      <text class="menu-desc">注销账号、用户协议、隐私政策</text>
      <button class="btn-menu" @tap.stop="goSettings">进入账号设置</button>
    </view>

  </view>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { generateRelativeInviteCode, relativeInviteQrcode, relativeInviteSms, getMyRelatives, unbindRelative } from '@/api/relative'
import { listMySemesters } from '@/api/semesters'
import { updateProfile } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'
import { PROVINCES, PROVINCE_NAMES, getCitiesForProvince, getCityName, getProvinceName } from '@/data/cities'
import type { PurchasedSemesterOut, QRCodeOut, BoundStudent } from '@/types/api'

const TEXTBOOK_VERSIONS = ['译林版', '人教版', '外研版', '北师大版', '冀教版']
const GRADES = ['小学3年级', '小学4年级', '小学5年级', '小学6年级', '初中7年级', '初中8年级', '初中9年级', '高中1年级', '高中2年级', '高中3年级']
const SEMESTERS = ['上', '下']

const auth = useAuthStore()
const myInvite = ref<{ code: string; expires_at: string } | null>(null)

// M23/M27 教材偏好 + 城市
const showPrefEdit = ref(false)
const prefSaving = ref(false)
const prefForm = reactive({
  textbookIdx: 0,
  gradeIdx: 0,
  semIdx: 0,
  provIdx: 0,
  cityIdx: 0,
})

const currentCityNames = computed(() => {
  const prov = PROVINCES[prefForm.provIdx]
  return getCitiesForProvince(prov?.name ?? '').map(c => c.name)
})

const cityDisplayName = computed(() => {
  const code = (auth.user as any)?.city_code
  if (!code) return ''
  const city = getCityName(code)
  const prov = getProvinceName(code)
  return city === prov ? city : (prov ? `${prov} ${city}` : city)
})

function onProvChange(e: any) {
  prefForm.provIdx = +e.detail.value
  prefForm.cityIdx = 0
}

function openPrefEdit() {
  const u: any = auth.user
  prefForm.textbookIdx = Math.max(0, TEXTBOOK_VERSIONS.indexOf(u?.preferred_textbook_version || ''))
  prefForm.gradeIdx = Math.max(0, GRADES.indexOf(u?.preferred_grade || ''))
  prefForm.semIdx = Math.max(0, SEMESTERS.indexOf(u?.preferred_semester || ''))
  // init city picker
  const code = u?.city_code
  if (code) {
    const provCode = code.slice(0, 2)
    const pIdx = PROVINCES.findIndex(p => p.code === provCode)
    if (pIdx >= 0) {
      prefForm.provIdx = pIdx
      const cities = getCitiesForProvince(PROVINCES[pIdx].name)
      const cIdx = cities.findIndex(c => c.code === code)
      prefForm.cityIdx = Math.max(0, cIdx)
    }
  }
  showPrefEdit.value = true
}

async function onSavePref() {
  prefSaving.value = true
  try {
    const cities = getCitiesForProvince(PROVINCES[prefForm.provIdx]?.name ?? '')
    const cityCode = cities[prefForm.cityIdx]?.code ?? null
    await updateProfile({
      preferred_textbook_version: TEXTBOOK_VERSIONS[prefForm.textbookIdx],
      preferred_grade: GRADES[prefForm.gradeIdx],
      preferred_semester: SEMESTERS[prefForm.semIdx],
      city_code: cityCode,
    })
    const u: any = auth.user
    if (u) {
      u.preferred_textbook_version = TEXTBOOK_VERSIONS[prefForm.textbookIdx]
      u.preferred_grade = GRADES[prefForm.gradeIdx]
      u.preferred_semester = SEMESTERS[prefForm.semIdx]
      u.city_code = cityCode
    }
    showPrefEdit.value = false
    uni.showToast({ title: '已保存', icon: 'success' })
  } catch (e: any) {
    uni.showToast({ title: e?.message || '保存失败', icon: 'none' })
  } finally { prefSaving.value = false }
}

const mySemesters = ref<PurchasedSemesterOut[]>([])
const myRelatives = ref<BoundStudent[]>([])
const relativesLoaded = ref(false)
const unbindingId = ref<string | null>(null)

const cancelInfo = computed(() => {
  const u: any = auth.user
  if (!u?.deactivation_scheduled_at) return null
  return { days: u.days_until_cancellation ?? 0 }
})

onMounted(async () => {
  if (auth.isLoggedIn()) {
    try { mySemesters.value = await listMySemesters() || [] } catch { /* 忽略 */ }
    try {
      myRelatives.value = await getMyRelatives() || []
    } catch { /* 忽略 */ } finally { relativesLoaded.value = true }
  }
})

function tierLabel(tier: string): string {
  return ({ basic: '基础版', pro: '专业版', promax: '旗舰版', free: '免费版' } as any)[tier] || tier
}

function goTeacher() {
  uni.navigateTo({ url: '/pages/teacher/students' })
}

function goRelative() {
  uni.navigateTo({ url: '/pages/relative/center' })
}

function goUserPapers() {
  uni.navigateTo({ url: '/pages/user-papers/list' })
}

function _requestBindSubscribe() {
  const tmplId = import.meta.env.VITE_WX_SUBSCRIBE_TEMPLATE_BIND as string | undefined
  if (!tmplId || tmplId.startsWith('placeholder')) return
  uni.requestSubscribeMessage({
    tmplIds: [tmplId],
    success() { },
    fail() { },
  })
}

async function genInviteCode() {
  // 先请求订阅权限，再生成邀请码（用户授权后家人绑定成功时会收到微信通知）
  _requestBindSubscribe()
  try {
    const r = await generateRelativeInviteCode()
    myInvite.value = r || null
    uni.showToast({ title: '已生成', icon: 'success' })
  } catch (e: any) {
    uni.showToast({ title: e?.message || '生成失败', icon: 'none' })
  }
}

function copyCode() {
  if (!myInvite.value) return
  uni.setClipboardData({
    data: myInvite.value.code,
    success: () => uni.showToast({ title: '已复制', icon: 'success' }),
  })
}

function goSettings() {
  uni.navigateTo({ url: '/pages/account/settings' })
}

function goCancelPage() {
  uni.navigateTo({ url: '/pages/account/cancel' })
}

const relQr = ref<QRCodeOut | null>(null)
const loadingRelQr = ref(false)
const showRelSms = ref(false)
const relSmsPhone = ref('')
const relSmsSending = ref(false)

async function onGenRelQr() {
  loadingRelQr.value = true
  try {
    relQr.value = await relativeInviteQrcode() as any
  } catch (e: any) {
    uni.showToast({ title: e?.message || '失败', icon: 'none' })
  } finally { loadingRelQr.value = false }
}

async function onSendRelSms() {
  relSmsSending.value = true
  try {
    await relativeInviteSms(relSmsPhone.value)
    uni.showToast({ title: '短信已发送', icon: 'success' })
    showRelSms.value = false
    relSmsPhone.value = ''
  } catch (e: any) {
    uni.showToast({ title: e?.message || '发送失败', icon: 'none' })
  } finally { relSmsSending.value = false }
}

async function onUnbind(relativeId: string) {
  uni.showModal({
    title: '确认解绑',
    content: '解绑后该家人将无法查看你的学情报告，确认吗？',
    confirmText: '解绑',
    confirmColor: '#e74c3c',
    success: async (res) => {
      if (!res.confirm) return
      unbindingId.value = relativeId
      try {
        await unbindRelative(relativeId)
        myRelatives.value = myRelatives.value.filter(r => r.student_id !== relativeId)
        uni.showToast({ title: '已解绑', icon: 'success' })
      } catch (e: any) {
        uni.showToast({ title: e?.message || '解绑失败', icon: 'none' })
      } finally { unbindingId.value = null }
    },
  })
}

function copyRelCode() {
  if (!relQr.value) return
  uni.setClipboardData({
    data: relQr.value.code,
    success: () => uni.showToast({ title: '已复制', icon: 'success' }),
  })
}

function goUnits(s: { textbook_version: string; grade: string; semester: string }) {
  const url = `/pages/curriculum/units?textbook=${encodeURIComponent(s.textbook_version)}&grade=${encodeURIComponent(s.grade)}&semester=${encodeURIComponent(s.semester)}`
  uni.navigateTo({ url })
}
function goPreviewUnits() {
  // 引导未购用户先看免费的第 1 单元（用用户的 preferred_* 偏好；缺省走小学5上）
  const t = (auth.user as any)?.preferred_textbook_version || '译林版'
  const g = (auth.user as any)?.preferred_grade || '小学5年级'
  const sem = (auth.user as any)?.preferred_semester || '上'
  const url = `/pages/curriculum/units?textbook=${encodeURIComponent(t)}&grade=${encodeURIComponent(g)}&semester=${encodeURIComponent(sem)}`
  uni.navigateTo({ url })
}

function goBuySemester() {
  const t = (auth.user as any)?.preferred_textbook_version || '译林版'
  const g = (auth.user as any)?.preferred_grade || '小学5年级'
  const sem = (auth.user as any)?.preferred_semester || '上'
  const url = `/pages/membership/semester-purchase?textbook=${encodeURIComponent(t)}&grade=${encodeURIComponent(g)}&semester=${encodeURIComponent(sem)}`
  uni.navigateTo({ url })
}
</script>

<style scoped>
.profile-page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin-bottom: 20rpx; box-shadow: 0 4rpx 24rpx rgba(0, 0, 0, 0.04); }
.card-title { font-size: var(--fs-h2); font-weight: 700; margin-bottom: 20rpx; color: var(--c-ink); }
.user-row { display: flex; align-items: center; }
.avatar { width: 100rpx; height: 100rpx; border-radius: 50%; margin-right: 24rpx; }
.avatar-placeholder {
  width: 100rpx;
  height: 100rpx;
  background: var(--c-bg-soft);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 48rpx;
  margin-right: 24rpx;
}
.nickname { font-size: 32rpx; font-weight: 700; color: var(--c-ink); }
.btn-login { background: var(--c-primary); color: var(--c-ink); border-radius: var(--r-btn); font-weight: 700; }
.member-tier {
  display: inline-block;
  padding: 8rpx 24rpx;
  border-radius: var(--r-pill);
  font-size: 28rpx;
  font-weight: 700;
  margin-bottom: 12rpx;
}
.tier-free { background: var(--c-bg-soft); color: var(--c-text-hint); }
.tier-basic { background: var(--c-primary-soft); color: #8a7212; }
.tier-pro { background: #fcecd2; color: var(--c-orange); }
.tier-promax { background: var(--c-danger-bg); color: var(--c-danger); }
.expires-tip { font-size: 24rpx; color: var(--c-text-hint); display: block; margin-bottom: 20rpx; }
.tier-list { display: flex; gap: 16rpx; margin: 24rpx 0; }
.tier-card {
  flex: 1;
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-md);
  padding: 20rpx;
  text-align: center;
}
.tier-card.selected { border-color: var(--c-gold); background: var(--c-primary-faint); }
.tier-name { font-size: 26rpx; color: var(--c-text-body); display: block; margin-bottom: 8rpx; }
.tier-price { font-size: 24rpx; color: var(--c-ink); font-weight: 600; }
.duration-row { display: flex; gap: 16rpx; margin-bottom: 24rpx; }
.duration-btn {
  flex: 1;
  text-align: center;
  padding: 16rpx;
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-md);
  font-size: 26rpx;
  position: relative;
}
.duration-btn.selected { border-color: var(--c-gold); color: var(--c-ink); background: var(--c-primary-faint); font-weight: 600; }
.discount-tag {
  position: absolute;
  top: -14rpx;
  right: -8rpx;
  background: var(--c-orange);
  color: #fff;
  font-size: 18rpx;
  padding: 2rpx 8rpx;
  border-radius: var(--r-sm);
}
.btn-pay {
  background: var(--c-primary);
  color: var(--c-ink);
  border-radius: var(--r-btn);
  font-size: 32rpx;
  font-weight: 700;
  height: 96rpx;
  line-height: 96rpx;
}
.btn-pay[disabled] { background: var(--c-primary-soft); color: #b9a94e; }
.center-tip { color: var(--c-text-hint); font-size: 28rpx; }
.menu-desc { font-size: 24rpx; color: var(--c-text-second); margin-bottom: 12rpx; display: block; }
.btn-menu { background: var(--c-primary-faint); color: var(--c-ink); border: 2rpx solid var(--c-gold); border-radius: var(--r-md); padding: 16rpx; font-size: 28rpx; font-weight: 600; text-align: center; }
.cancel-banner { background: var(--c-orange); color: #fff; border-radius: var(--r-md); padding: 16rpx 24rpx; margin-bottom: 16rpx; display: flex; align-items: center; }
.cb-text { flex: 1; font-size: 26rpx; font-weight: 700; }
.cb-action { font-size: 26rpx; }
.sem-list { display: flex; flex-direction: column; gap: 12rpx; }
.sem-item { background: var(--c-bg-soft); border-radius: var(--r-md); padding: 16rpx 20rpx; display: flex; justify-content: space-between; align-items: center; }
.sem-info { display: flex; flex-direction: column; gap: 4rpx; }
.sem-name { font-size: 28rpx; color: var(--c-ink); font-weight: 600; }
.sem-tier { display: inline-block; font-size: 22rpx; padding: 2rpx 12rpx; border-radius: var(--r-pill); margin-top: 4rpx; width: fit-content; font-weight: 600; }
.sem-tier.tier-basic { background: var(--c-primary-soft); color: #8a7212; }
.sem-tier.tier-pro { background: #fcecd2; color: var(--c-orange); }
.sem-tier.tier-promax { background: var(--c-danger-bg); color: var(--c-danger); }
.sem-expires { font-size: 24rpx; color: var(--c-text-hint); }
.empty-tip { font-size: 26rpx; color: var(--c-text-hint); }
.invite-row { margin-top: 12rpx; background: var(--c-bg-soft); border-radius: var(--r-md); padding: 16rpx; display: flex; align-items: center; gap: 12rpx; }
.inv-code { flex: 1; font-size: 40rpx; font-weight: 800; color: var(--c-ink); letter-spacing: 6rpx; }
.inv-exp { font-size: 22rpx; color: var(--c-text-hint); }
.btn-copy { background: var(--c-primary); color: var(--c-ink); font-size: 24rpx; font-weight: 600; border-radius: var(--r-sm); padding: 8rpx 16rpx; }
.btn-primary { background: var(--c-primary); color: var(--c-ink); border-radius: var(--r-btn); padding: 20rpx; font-size: 28rpx; font-weight: 700; text-align: center; margin-top: 8rpx; }
.btn-primary[disabled] { background: var(--c-primary-soft); color: #b9a94e; }
.btn-secondary { background: var(--c-primary-faint); color: var(--c-ink); border: 2rpx solid var(--c-gold); border-radius: var(--r-md); padding: 20rpx; font-size: 28rpx; font-weight: 600; text-align: center; }
.invite-actions { display: flex; gap: 12rpx; }
.half { flex: 1; margin-top: 0; }
.modal { position: fixed; left: 0; right: 0; top: 0; bottom: 0; background: rgba(0,0,0,.5); display: flex; align-items: center; justify-content: center; z-index: 999; }
.modal-card { background: var(--c-bg-card); border-radius: var(--r-xl); padding: var(--sp-5); width: 80%; max-width: 600rpx; box-shadow: 0 8rpx 32rpx rgba(0,0,0,.2); }
.qr-img { width: 100%; height: 480rpx; }
.qr-tip { display: block; text-align: center; font-size: 26rpx; color: var(--c-text-second); margin: 16rpx 0; line-height: 1.5; }
.qr-fallback { display: flex; align-items: center; gap: 12rpx; margin: 16rpx 0; padding: 12rpx; background: var(--c-bg-soft); border-radius: var(--r-md); }
.qr-code { flex: 1; font-size: 36rpx; font-weight: 800; letter-spacing: 4rpx; color: var(--c-ink); }
.dev-hint { display: block; font-size: 22rpx; color: var(--c-text-hint); margin-bottom: 16rpx; }
.sem-right { display: flex; flex-direction: column; align-items: flex-end; gap: 4rpx; }
.chevron { color: var(--c-text-hint); font-size: 28rpx; }
/* 已绑定的家人 */
.rel-empty { font-size: 26rpx; color: var(--c-text-hint); text-align: center; padding: 20rpx 0; }
.rel-row { display: flex; align-items: center; justify-content: space-between; padding: 14rpx 0; border-bottom: 1rpx solid var(--c-border); }
.rel-row:last-child { border-bottom: none; }
.rel-info { display: flex; flex-direction: column; gap: 4rpx; }
.rel-name { font-size: 28rpx; font-weight: 700; color: var(--c-ink); }
.rel-rel { font-size: 24rpx; color: var(--c-text-hint); }
.btn-unbind { background: #fdecea; color: #e74c3c; border: 2rpx solid #f5c6c6; border-radius: var(--r-sm); font-size: 24rpx; padding: 8rpx 20rpx; }
.btn-unbind[disabled] { opacity: 0.5; }
/* M23 pref */
.pref-row { display: flex; justify-content: space-between; align-items: center; padding: 14rpx 0; border-bottom: 1rpx solid var(--c-border); }
.pref-row:last-of-type { border-bottom: none; }
.pref-label { font-size: 26rpx; color: var(--c-text-second); }
.pref-val { font-size: 28rpx; color: var(--c-ink); font-weight: 600; }
.picker-row { background: var(--c-bg-soft); border-radius: var(--r-md); padding: 16rpx 20rpx; font-size: 28rpx; color: var(--c-ink); }
</style>
