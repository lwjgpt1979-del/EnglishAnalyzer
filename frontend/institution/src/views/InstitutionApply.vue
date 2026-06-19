<script setup lang="ts">
import { computed, reactive, ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getApplyCaptcha, applySendCode, applyInstitution, listRegions, type RegionNode } from '../api/institution'

const router = useRouter()

const form = reactive({
  name: '',
  contact_phone: '',
  code: '',
  province_code: '',
  city_code: '',
  address: '',
})

// ── 图形验证码（防短信盗刷）──
const captchaId = ref('')
const captchaSvg = ref('')
const captchaInput = ref('')

async function refreshCaptcha() {
  try {
    const c = await getApplyCaptcha()
    captchaId.value = c.captcha_id
    captchaSvg.value = c.image_svg
    captchaInput.value = ''
  } catch {
    // 静默：用户点图可重试
  }
}
// ── 地区(后端 region 表唯一源，懒加载省→市)──
const provinces = ref<RegionNode[]>([])
const cityOptions = ref<RegionNode[]>([])

onMounted(async () => {
  refreshCaptcha()
  try { provinces.value = await listRegions() } catch { /* 静默，可重试 */ }
})

async function onProvinceChange() {
  form.city_code = ''
  cityOptions.value = []
  if (!form.province_code) return
  try { cityOptions.value = await listRegions(form.province_code) } catch { /* 忽略 */ }
}

// ── 验证码倒计时 ──
const countdown = ref(0)
const sending = ref(false)
let timer: number | undefined

function startCountdown() {
  countdown.value = 60
  timer = window.setInterval(() => {
    countdown.value -= 1
    if (countdown.value <= 0 && timer) { clearInterval(timer); timer = undefined }
  }, 1000)
}
onUnmounted(() => { if (timer) clearInterval(timer) })

const phoneOk = computed(() => /^1[3-9]\d{9}$/.test(form.contact_phone))

async function onSendCode() {
  if (!phoneOk.value) { ElMessage.warning('请输入正确的 11 位手机号'); return }
  if (!captchaInput.value.trim()) { ElMessage.warning('请先填写图形验证码'); return }
  sending.value = true
  try {
    await applySendCode(form.contact_phone, captchaId.value, captchaInput.value.trim())
    ElMessage.success('验证码已发送，请注意查收')
    startCountdown()
    refreshCaptcha()
  } catch (e) {
    ElMessage.error((e as Error).message || '发送失败')
    refreshCaptcha()  // 图形码一次性，失败后换新
  } finally {
    sending.value = false
  }
}

// ── 提交 ──
const submitting = ref(false)
const submitted = ref(false)

async function onSubmit() {
  if (form.name.trim().length < 2) { ElMessage.warning('请填写机构名称'); return }
  if (!phoneOk.value) { ElMessage.warning('请输入正确的手机号'); return }
  if (!form.code.trim()) { ElMessage.warning('请输入验证码'); return }
  if (!form.province_code || !form.city_code) { ElMessage.warning('请选择所在省市'); return }
  if (form.address.trim().length < 4) { ElMessage.warning('请填写详细地址'); return }
  submitting.value = true
  try {
    await applyInstitution({
      name: form.name.trim(),
      contact_phone: form.contact_phone,
      province_code: form.province_code,
      city_code: form.city_code,
      address: form.address.trim(),
      code: form.code.trim(),
    })
    submitted.value = true
  } catch (e) {
    ElMessage.error((e as Error).message || '提交失败')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="apply-wrap">
    <el-card class="apply-card">
      <!-- 提交成功 -->
      <div v-if="submitted" class="success">
        <el-result icon="success" title="申请已提交"
          sub-title="我们会在 1-2 个工作日内审核，审核通过后将电话联系您开通机构管理账号。">
          <template #extra>
            <el-button type="primary" @click="router.push('/login')">返回登录</el-button>
          </template>
        </el-result>
      </div>

      <!-- 申请表单 -->
      <template v-else>
        <h2 class="t">机构入驻申请</h2>
        <p class="sub">填写机构信息提交申请，平台审核通过后为您开通管理后台账号。</p>

        <el-form label-position="top">
          <el-form-item label="机构名称" required>
            <el-input v-model="form.name" placeholder="请输入机构全称" maxlength="40" />
          </el-form-item>

          <el-form-item label="联系手机号" required>
            <el-input v-model="form.contact_phone" placeholder="11 位手机号" maxlength="11" />
          </el-form-item>

          <el-form-item label="图形验证码" required>
            <div class="captcha-row">
              <el-input v-model="captchaInput" placeholder="输入右侧字符" maxlength="6" />
              <!-- eslint-disable-next-line vue/no-v-html -->
              <div class="captcha-img" title="看不清？点击换一张" @click="refreshCaptcha" v-html="captchaSvg" />
            </div>
          </el-form-item>

          <el-form-item label="短信验证码" required>
            <div class="phone-row">
              <el-input v-model="form.code" placeholder="请输入 6 位验证码" maxlength="6" />
              <el-button :disabled="countdown > 0 || sending" :loading="sending" @click="onSendCode">
                {{ countdown > 0 ? `${countdown}s 后重发` : '获取验证码' }}
              </el-button>
            </div>
          </el-form-item>

          <el-form-item label="所在地区" required>
            <div class="region-row">
              <el-select v-model="form.province_code" placeholder="省份" filterable
                style="flex:1" @change="onProvinceChange">
                <el-option v-for="p in provinces" :key="p.code" :label="p.name" :value="p.code" />
              </el-select>
              <el-select v-model="form.city_code" placeholder="城市" filterable
                style="flex:1" :disabled="!form.province_code">
                <el-option v-for="c in cityOptions" :key="c.code" :label="c.name" :value="c.code" />
              </el-select>
            </div>
          </el-form-item>

          <el-form-item label="详细地址" required>
            <el-input v-model="form.address" type="textarea" :rows="2"
              placeholder="街道、门牌号等" maxlength="100" />
          </el-form-item>

          <el-button type="primary" :loading="submitting" style="width:100%" @click="onSubmit">
            提交申请
          </el-button>
          <div class="back"><el-link type="info" @click="router.push('/login')">已有账号？返回登录</el-link></div>
        </el-form>
      </template>
    </el-card>
  </div>
</template>

<style scoped>
.apply-wrap { min-height: 100vh; display: flex; align-items: center; justify-content: center; background: #f0f2f5; padding: 24px 0; }
.apply-card { width: 440px; max-width: 92vw; }
.t { text-align: center; margin: 0 0 6px; }
.sub { text-align: center; color: #909399; font-size: 13px; margin: 0 0 20px; line-height: 1.6; }
.phone-row { display: flex; gap: 10px; width: 100%; }
.phone-row .el-input { flex: 1; }
.captcha-row { display: flex; gap: 10px; width: 100%; align-items: center; }
.captcha-row .el-input { flex: 1; }
.captcha-img { width: 120px; height: 44px; flex-shrink: 0; cursor: pointer; border-radius: 6px; overflow: hidden; line-height: 0; }
.captcha-img :deep(svg) { display: block; width: 120px; height: 44px; }
.region-row { display: flex; gap: 10px; width: 100%; }
.back { text-align: center; margin-top: 14px; }
.success { padding: 8px 0; }
</style>
