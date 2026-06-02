# 微信小程序前端 MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 uni-app Vue3 + TypeScript + Pinia 实现 engGramer 微信小程序 MVP，覆盖错题上传、AI 分析、学情报告、会员购买全流程。

**Architecture:** 单 uni-app 项目（`frontend/miniprogram/`），Vue3 Composition API + `<script setup>` 风格，Pinia store 管理 auth/user 状态，自定义 `request.ts` 封装 API 调用（自动注入 JWT、统一错误处理），COS 图片先用 `wx.getFileSystemManager().readFile()` 读 ArrayBuffer 再 `wx.request({ method: 'PUT' })` 直传。

**Tech Stack:** uni-app 3.x · Vue 3 · TypeScript · Pinia · pnpm · Vite（内置）· @dcloudio/uni-cli

---

## File Structure

```
frontend/miniprogram/
├── src/
│   ├── api/
│   │   ├── auth.ts              # wx-login
│   │   ├── upload.ts            # presign
│   │   ├── wrongQuestions.ts    # CRUD + analyze
│   │   ├── diagnosis.ts         # report
│   │   ├── memberships.ts       # me
│   │   └── orders.ts            # create + pay
│   ├── composables/
│   │   └── useUpload.ts         # chooseImage → presign → COS PUT → createWQ
│   ├── pages/
│   │   ├── index/index.vue      # 首页（TabBar）
│   │   ├── upload/index.vue     # 上传错题
│   │   ├── wrong-questions/
│   │   │   ├── list.vue         # 错题列表
│   │   │   └── detail.vue       # 错题详情 + AI 分析
│   │   ├── diagnosis/index.vue  # 学情报告
│   │   └── profile/index.vue    # 个人中心 + 会员
│   ├── stores/
│   │   └── auth.ts              # Pinia：token + user + wx-login action
│   ├── types/
│   │   └── api.ts               # TS 接口，与后端 schema 一一对应
│   ├── utils/
│   │   └── request.ts           # uni.request 封装，自动注入 Bearer token
│   ├── App.vue
│   ├── main.ts
│   └── pages.json               # 路由 + TabBar 配置
├── index.html
├── vite.config.ts
├── tsconfig.json
└── package.json
```

---

### Task 0: 脚手架 — 创建 uni-app 项目、依赖安装、类型定义、request 封装

**Files:**
- Create: `frontend/miniprogram/` (entire project via CLI)
- Create: `frontend/miniprogram/src/pages.json`
- Create: `frontend/miniprogram/src/types/api.ts`
- Create: `frontend/miniprogram/src/utils/request.ts`

- [ ] **Step 1: 创建 uni-app 项目**

在项目根目录（engGramer/）运行：

```bash
mkdir -p frontend
cd frontend
npx degit dcloudio/uni-preset-vue#vite-ts miniprogram
cd miniprogram
pnpm install
```

如果 degit 速度慢，备用方案：

```bash
pnpm create uni-app miniprogram --template vue3-ts
cd miniprogram
pnpm install
```

- [ ] **Step 2: 安装 Pinia**

```bash
pnpm add pinia
```

- [ ] **Step 3: 配置 `src/pages.json`**

覆盖（或新建）`src/pages.json`，写入完整路由 + TabBar 配置：

```json
{
  "pages": [
    {
      "path": "pages/index/index",
      "style": { "navigationBarTitleText": "engGramer" }
    },
    {
      "path": "pages/upload/index",
      "style": { "navigationBarTitleText": "上传错题" }
    },
    {
      "path": "pages/wrong-questions/list",
      "style": { "navigationBarTitleText": "我的错题" }
    },
    {
      "path": "pages/wrong-questions/detail",
      "style": { "navigationBarTitleText": "错题详情" }
    },
    {
      "path": "pages/diagnosis/index",
      "style": { "navigationBarTitleText": "学情报告" }
    },
    {
      "path": "pages/profile/index",
      "style": { "navigationBarTitleText": "我的" }
    }
  ],
  "tabBar": {
    "color": "#999",
    "selectedColor": "#1677ff",
    "list": [
      {
        "pagePath": "pages/index/index",
        "text": "首页",
        "iconPath": "static/tab-home.png",
        "selectedIconPath": "static/tab-home-active.png"
      },
      {
        "pagePath": "pages/wrong-questions/list",
        "text": "错题",
        "iconPath": "static/tab-wrong.png",
        "selectedIconPath": "static/tab-wrong-active.png"
      },
      {
        "pagePath": "pages/diagnosis/index",
        "text": "报告",
        "iconPath": "static/tab-report.png",
        "selectedIconPath": "static/tab-report-active.png"
      },
      {
        "pagePath": "pages/profile/index",
        "text": "我的",
        "iconPath": "static/tab-profile.png",
        "selectedIconPath": "static/tab-profile-active.png"
      }
    ]
  },
  "globalStyle": {
    "navigationBarTextStyle": "black",
    "navigationBarTitleText": "engGramer",
    "navigationBarBackgroundColor": "#ffffff",
    "backgroundColor": "#f5f5f5"
  }
}
```

- [ ] **Step 4: 生成 TabBar 图标占位文件**

TabBar 必须有图标文件否则编译报错。用 Python 生成8个最小 PNG：

```bash
python3 -c "
import base64
data = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==')
import os; os.makedirs('src/static', exist_ok=True)
for name in ['tab-home','tab-home-active','tab-wrong','tab-wrong-active','tab-report','tab-report-active','tab-profile','tab-profile-active']:
    open(f'src/static/{name}.png','wb').write(data)
print('icons created')
"
```

预期输出：`icons created`

- [ ] **Step 5: 创建 `src/types/api.ts`**

```typescript
// src/types/api.ts
// 与后端 schemas 一一对应，字段名保持 snake_case

export interface BaseResponse<T> {
  code: number
  message: string
  data: T
}

// ── Auth ─────────────────────────────────────────────────────────────────────

export interface LoginData {
  access_token: string
  token_type: string
  user: {
    id: string
    openid: string
    nickname: string | null
    avatar_url: string | null
  }
}

// ── Upload ───────────────────────────────────────────────────────────────────

export interface PresignData {
  presign_url: string
  file_url: string
  key: string
  expires_in: number
}

// ── WrongQuestion ────────────────────────────────────────────────────────────

export interface WrongQuestionCreate {
  source_image_url: string
  question_text?: string
  student_answer?: string
  correct_answer?: string
  question_type?: string
  difficulty?: number
  tags?: string[]
}

export interface WrongQuestionOut {
  id: string
  student_id: string
  source_image_url: string
  question_text: string | null
  student_answer: string | null
  correct_answer: string | null
  question_type: string | null
  difficulty: number | null
  tags: string[] | null
  is_mastered: boolean
  mastered_at: string | null
  created_at: string
  updated_at: string
}

export interface WrongQuestionListOut {
  items: WrongQuestionOut[]
  total: number
}

export interface AiAnalysisOut {
  id: string
  wrong_question_id: string
  llm_provider: string
  error_types: string[]
  knowledge_points: string[]
  diagnosis: string
  suggestions: string
  confidence_score: number | null
  tokens_used: number
  created_at: string
}

// ── Diagnosis ────────────────────────────────────────────────────────────────

export interface ErrorTypeCount {
  error_type: string
  count: number
}

export interface KnowledgePointCount {
  knowledge_point: string
  count: number
}

export interface DailyActivity {
  date: string
  count: number
}

export interface DiagnosisReport {
  total_questions: number
  total_analyzed: number
  mastered_count: number
  mastery_rate: number
  top_error_types: ErrorTypeCount[]
  top_weak_knowledge_points: KnowledgePointCount[]
  question_type_distribution: Record<string, number>
  difficulty_distribution: Record<string, number>
  recent_daily_activity: DailyActivity[]
  top_suggestions: string[]
}

// ── Membership ───────────────────────────────────────────────────────────────

export interface CurrentMembershipOut {
  tier: string          // free | basic | pro | promax
  started_at: string | null
  expires_at: string | null
  is_active: boolean
}

// ── Orders ───────────────────────────────────────────────────────────────────

export interface OrderCreate {
  tier: string          // basic | pro | promax
  duration_months: number  // 1 | 3 | 12
  order_type: string    // new | renew | upgrade
}

export interface OrderOut {
  id: string
  order_no: string
  tier: string
  duration_months: number
  amount_fen: number    // 分
  status: string        // pending | paid | refunded | partial_refunded
  wx_transaction_id: string | null
  paid_at: string | null
  created_at: string
}

export interface PayParamsOut {
  timeStamp: string
  nonceStr: string
  package: string       // prepay_id=wx...
  signType: string      // RSA
  paySign: string
}
```

- [ ] **Step 6: 创建 `src/utils/request.ts`**

读 token 直接用 `uni.getStorageSync`（不 import store）避免循环依赖：

```typescript
// src/utils/request.ts

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string) || 'http://localhost:8000'

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  data?: Record<string, unknown>
  header?: Record<string, string>
}

export function request<T>(url: string, options: RequestOptions = {}): Promise<T> {
  return new Promise((resolve, reject) => {
    const token = uni.getStorageSync('access_token') as string | undefined
    const header: Record<string, string> = {
      'Content-Type': 'application/json',
      ...options.header,
    }
    if (token) {
      header['Authorization'] = `Bearer ${token}`
    }

    uni.request({
      url: `${BASE_URL}${url}`,
      method: options.method || 'GET',
      data: options.data,
      header,
      success(res) {
        const body = res.data as { code: number; message: string; data: T }
        if (res.statusCode === 401) {
          uni.removeStorageSync('access_token')
          uni.reLaunch({ url: '/pages/index/index' })
          reject(new Error('未登录或登录已过期'))
          return
        }
        if (res.statusCode < 200 || res.statusCode >= 300) {
          reject(new Error(body?.message || `HTTP ${res.statusCode}`))
          return
        }
        if (body.code !== 200) {
          reject(new Error(body.message || '请求失败'))
          return
        }
        resolve(body.data)
      },
      fail(err) {
        reject(new Error(err.errMsg || '网络请求失败'))
      },
    })
  })
}
```

- [ ] **Step 7: 验证编译**

```bash
pnpm dev:mp-weixin
```

预期：输出 `dist/dev/mp-weixin/`，无 TS 类型错误（pages 目录此时可能只有模板页面，编译能通过即可）。

- [ ] **Step 8: Commit**

```bash
git add frontend/miniprogram/
git commit -m "feat(frontend): scaffold uni-app Vue3 TypeScript miniprogram with TabBar routing, types, and request utils"
```

---

### Task 1: API 层 + Auth Store（wx-login → JWT → storage）

**Files:**
- Create: `frontend/miniprogram/src/api/auth.ts`
- Create: `frontend/miniprogram/src/api/upload.ts`
- Create: `frontend/miniprogram/src/api/wrongQuestions.ts`
- Create: `frontend/miniprogram/src/api/diagnosis.ts`
- Create: `frontend/miniprogram/src/api/memberships.ts`
- Create: `frontend/miniprogram/src/api/orders.ts`
- Create: `frontend/miniprogram/src/stores/auth.ts`
- Modify: `frontend/miniprogram/src/main.ts`

- [ ] **Step 1: 创建 `src/api/auth.ts`**

```typescript
// src/api/auth.ts
import { request } from '@/utils/request'
import type { LoginData } from '@/types/api'

export function wxLogin(code: string): Promise<LoginData> {
  return request<LoginData>('/api/v1/auth/wx-login', {
    method: 'POST',
    data: { code },
  })
}
```

- [ ] **Step 2: 创建 `src/api/upload.ts`**

```typescript
// src/api/upload.ts
import { request } from '@/utils/request'
import type { PresignData } from '@/types/api'

export function getPresignUrl(contentType: string): Promise<PresignData> {
  return request<PresignData>('/api/v1/upload/presign', {
    method: 'POST',
    data: { content_type: contentType },
  })
}
```

- [ ] **Step 3: 创建 `src/api/wrongQuestions.ts`**

```typescript
// src/api/wrongQuestions.ts
import { request } from '@/utils/request'
import type {
  AiAnalysisOut,
  WrongQuestionCreate,
  WrongQuestionListOut,
  WrongQuestionOut,
} from '@/types/api'

export function createWrongQuestion(data: WrongQuestionCreate): Promise<WrongQuestionOut> {
  return request<WrongQuestionOut>('/api/v1/wrong-questions/', {
    method: 'POST',
    data: data as unknown as Record<string, unknown>,
  })
}

export function listWrongQuestions(skip = 0, limit = 20): Promise<WrongQuestionListOut> {
  return request<WrongQuestionListOut>(
    `/api/v1/wrong-questions/?skip=${skip}&limit=${limit}`,
  )
}

export function getWrongQuestion(id: string): Promise<WrongQuestionOut> {
  return request<WrongQuestionOut>(`/api/v1/wrong-questions/${id}`)
}

export function markMastered(id: string, isMastered: boolean): Promise<WrongQuestionOut> {
  return request<WrongQuestionOut>(`/api/v1/wrong-questions/${id}/mastered`, {
    method: 'PATCH',
    data: { is_mastered: isMastered },
  })
}

export function analyzeWrongQuestion(id: string): Promise<AiAnalysisOut> {
  return request<AiAnalysisOut>(`/api/v1/wrong-questions/${id}/analyze`, {
    method: 'POST',
  })
}

export function listAnalyses(id: string): Promise<AiAnalysisOut[]> {
  return request<AiAnalysisOut[]>(`/api/v1/wrong-questions/${id}/analyses`)
}
```

- [ ] **Step 4: 创建 `src/api/diagnosis.ts`**

```typescript
// src/api/diagnosis.ts
import { request } from '@/utils/request'
import type { DiagnosisReport } from '@/types/api'

export function getDiagnosisReport(): Promise<DiagnosisReport> {
  return request<DiagnosisReport>('/api/v1/diagnosis/report')
}
```

- [ ] **Step 5: 创建 `src/api/memberships.ts`**

```typescript
// src/api/memberships.ts
import { request } from '@/utils/request'
import type { CurrentMembershipOut } from '@/types/api'

export function getMyMembership(): Promise<CurrentMembershipOut> {
  return request<CurrentMembershipOut>('/api/v1/memberships/me')
}
```

- [ ] **Step 6: 创建 `src/api/orders.ts`**

```typescript
// src/api/orders.ts
import { request } from '@/utils/request'
import type { OrderCreate, OrderOut, PayParamsOut } from '@/types/api'

export function createOrder(data: OrderCreate): Promise<OrderOut> {
  return request<OrderOut>('/api/v1/orders/', {
    method: 'POST',
    data: data as unknown as Record<string, unknown>,
  })
}

export function getOrder(id: string): Promise<OrderOut> {
  return request<OrderOut>(`/api/v1/orders/${id}`)
}

export function payOrder(id: string): Promise<PayParamsOut> {
  return request<PayParamsOut>(`/api/v1/orders/${id}/pay`, { method: 'POST' })
}
```

- [ ] **Step 7: 创建 `src/stores/auth.ts`**

```typescript
// src/stores/auth.ts
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { wxLogin } from '@/api/auth'
import type { LoginData } from '@/types/api'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string>(uni.getStorageSync('access_token') || '')
  const user = ref<LoginData['user'] | null>(null)

  function isLoggedIn(): boolean {
    return !!token.value
  }

  async function login(): Promise<void> {
    // Step 1: 获取微信 code
    const code = await new Promise<string>((resolve, reject) => {
      uni.login({
        provider: 'weixin',
        success: (res) => resolve(res.code),
        fail: (err) => reject(new Error(err.errMsg || '微信登录失败')),
      })
    })
    // Step 2: 换取 JWT
    const data = await wxLogin(code)
    token.value = data.access_token
    user.value = data.user
    uni.setStorageSync('access_token', data.access_token)
  }

  function logout(): void {
    token.value = ''
    user.value = null
    uni.removeStorageSync('access_token')
  }

  return { token, user, isLoggedIn, login, logout }
})
```

- [ ] **Step 8: 修改 `src/main.ts` — 注册 Pinia**

```typescript
// src/main.ts
import { createSSRApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'

export function createApp() {
  const app = createSSRApp(App)
  app.use(createPinia())
  return { app }
}
```

- [ ] **Step 9: 验证编译**

```bash
pnpm dev:mp-weixin
```

预期：无 TS 类型错误，dist 输出正常。

- [ ] **Step 10: Commit**

```bash
git add src/api/ src/stores/ src/main.ts
git commit -m "feat(frontend): add API layer (auth/upload/wq/diagnosis/membership/order) and Pinia auth store"
```

---

### Task 2: 错题上传页（chooseImage → COS PUT → createWrongQuestion）

**Files:**
- Create: `frontend/miniprogram/src/composables/useUpload.ts`
- Create: `frontend/miniprogram/src/pages/upload/index.vue`

COS 直传关键：`uni.chooseImage` 获取临时路径 → `wx.getFileSystemManager().readFile` 读 ArrayBuffer → `wx.request({ method: 'PUT', data: arrayBuffer, header: {'Content-Type': contentType} })` 直传预签名 URL。不能用 `uni.uploadFile`（它是 multipart/form-data，COS presigned PUT 不接受）。

- [ ] **Step 1: 创建 `src/composables/useUpload.ts`**

```typescript
// src/composables/useUpload.ts
import { ref } from 'vue'
import { getPresignUrl } from '@/api/upload'
import { createWrongQuestion } from '@/api/wrongQuestions'
import type { WrongQuestionOut } from '@/types/api'

type MimeType = 'image/jpeg' | 'image/png' | 'image/webp'

type UploadProgress =
  | 'idle'
  | 'choosing'
  | 'presigning'
  | 'uploading'
  | 'creating'
  | 'done'
  | 'error'

interface UploadOptions {
  questionType?: string
  difficulty?: number
}

export function useUpload() {
  const uploading = ref(false)
  const progress = ref<UploadProgress>('idle')
  const errorMsg = ref('')

  async function uploadAndCreate(
    options: UploadOptions = {},
  ): Promise<WrongQuestionOut | null> {
    uploading.value = true
    progress.value = 'choosing'
    errorMsg.value = ''

    try {
      // Step 1: 选图
      const tempFilePath = await new Promise<string>((resolve, reject) => {
        uni.chooseImage({
          count: 1,
          sizeType: ['compressed'],
          sourceType: ['album', 'camera'],
          success: (res) => resolve(res.tempFilePaths[0]),
          fail: (err) => reject(new Error(err.errMsg || '选图失败')),
        })
      })

      // Step 2: 检测图片类型
      const lower = tempFilePath.toLowerCase()
      const contentType: MimeType = lower.endsWith('.png')
        ? 'image/png'
        : lower.endsWith('.webp')
          ? 'image/webp'
          : 'image/jpeg'

      // Step 3: 获取预签名 URL
      progress.value = 'presigning'
      const presign = await getPresignUrl(contentType)

      // Step 4: 读取图片为 ArrayBuffer，直传 COS presigned PUT URL
      progress.value = 'uploading'
      const arrayBuffer = await new Promise<ArrayBuffer>((resolve, reject) => {
        wx.getFileSystemManager().readFile({
          filePath: tempFilePath,
          success: (res) => resolve(res.data as ArrayBuffer),
          fail: (err) => reject(new Error(err.errMsg || '读取文件失败')),
        })
      })

      await new Promise<void>((resolve, reject) => {
        wx.request({
          url: presign.presign_url,
          method: 'PUT',
          data: arrayBuffer,
          header: { 'Content-Type': contentType },
          responseType: 'arraybuffer',
          success: (res) => {
            if (res.statusCode === 200 || res.statusCode === 204) {
              resolve()
            } else {
              reject(new Error(`COS 上传失败：HTTP ${res.statusCode}`))
            }
          },
          fail: (err) => reject(new Error(err.errMsg || 'COS 上传失败')),
        })
      })

      // Step 5: 创建错题记录
      progress.value = 'creating'
      const wq = await createWrongQuestion({
        source_image_url: presign.file_url,
        question_type: options.questionType,
        difficulty: options.difficulty,
      })

      progress.value = 'done'
      return wq
    } catch (e) {
      progress.value = 'error'
      errorMsg.value = (e as Error).message || '上传失败'
      return null
    } finally {
      uploading.value = false
    }
  }

  return { uploading, progress, errorMsg, uploadAndCreate }
}
```

- [ ] **Step 2: 创建 `src/pages/upload/index.vue`**

```vue
<!-- src/pages/upload/index.vue -->
<template>
  <view class="upload-page">
    <view class="card">
      <view class="card-title">上传错题图片</view>

      <!-- 题型选择 -->
      <view class="form-item">
        <text class="label">题型</text>
        <picker :range="questionTypes" @change="onTypeChange">
          <view class="picker-val">{{ selectedType || '请选择（可选）' }}</view>
        </picker>
      </view>

      <!-- 难度选择 -->
      <view class="form-item">
        <text class="label">难度</text>
        <picker :range="difficulties" @change="onDiffChange">
          <view class="picker-val">
            {{ selectedDiff ? selectedDiff + ' 星' : '请选择（可选）' }}
          </view>
        </picker>
      </view>

      <!-- 上传按钮 -->
      <button class="btn-upload" :disabled="uploading" @tap="onUpload">
        {{ uploadBtnText }}
      </button>

      <!-- 错误提示 -->
      <view v-if="errorMsg" class="error-msg">{{ errorMsg }}</view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useUpload } from '@/composables/useUpload'

const questionTypes = ['单选', '完型', '阅读', '作文', '其他']
const difficulties = ['1', '2', '3', '4', '5']

const selectedType = ref('')
const selectedDiff = ref<number | undefined>(undefined)

const { uploading, progress, errorMsg, uploadAndCreate } = useUpload()

function onTypeChange(e: { detail: { value: number } }) {
  selectedType.value = questionTypes[e.detail.value]
}

function onDiffChange(e: { detail: { value: number } }) {
  selectedDiff.value = e.detail.value + 1
}

const uploadBtnText = computed(() => {
  const map: Record<string, string> = {
    idle: '选图上传',
    choosing: '选择图片中…',
    presigning: '准备上传…',
    uploading: '上传图片中…',
    creating: '保存错题中…',
    done: '上传成功！',
    error: '重试上传',
  }
  return map[progress.value] || '选图上传'
})

async function onUpload() {
  const wq = await uploadAndCreate({
    questionType: selectedType.value || undefined,
    difficulty: selectedDiff.value,
  })
  if (wq) {
    uni.showToast({ title: '上传成功', icon: 'success' })
    setTimeout(() => {
      uni.navigateTo({ url: `/pages/wrong-questions/detail?id=${wq.id}` })
    }, 800)
  } else {
    uni.showToast({ title: errorMsg.value || '上传失败', icon: 'error' })
  }
}
</script>

<style scoped>
.upload-page { padding: 24rpx; }
.card { background: #fff; border-radius: 16rpx; padding: 32rpx; }
.card-title { font-size: 32rpx; font-weight: bold; margin-bottom: 32rpx; color: #222; }
.form-item {
  display: flex;
  align-items: center;
  padding: 20rpx 0;
  border-bottom: 1rpx solid #f0f0f0;
}
.label { width: 120rpx; color: #666; font-size: 28rpx; }
.picker-val { flex: 1; color: #333; font-size: 28rpx; padding-left: 16rpx; }
.btn-upload {
  margin-top: 48rpx;
  background: #1677ff;
  color: #fff;
  border-radius: 12rpx;
  font-size: 32rpx;
  height: 96rpx;
  line-height: 96rpx;
}
.btn-upload[disabled] { opacity: 0.5; }
.error-msg { margin-top: 20rpx; color: #ff4d4f; font-size: 26rpx; text-align: center; }
</style>
```

- [ ] **Step 3: 验证编译**

```bash
pnpm dev:mp-weixin
```

预期：无 TS 错误，`dist/dev/mp-weixin/pages/upload/index.js` 生成。

- [ ] **Step 4: Commit**

```bash
git add src/composables/ src/pages/upload/
git commit -m "feat(frontend): add upload page with COS presigned PUT flow"
```

---

### Task 3: 错题列表 + 错题详情 + AI 分析

**Files:**
- Create: `frontend/miniprogram/src/pages/wrong-questions/list.vue`
- Create: `frontend/miniprogram/src/pages/wrong-questions/detail.vue`

- [ ] **Step 1: 创建 `src/pages/wrong-questions/list.vue`**

```vue
<!-- src/pages/wrong-questions/list.vue -->
<template>
  <view class="list-page">
    <!-- 加载态 -->
    <view v-if="loading && items.length === 0" class="center-tip">加载中…</view>

    <!-- 空状态 -->
    <view v-else-if="!loading && items.length === 0" class="center-tip">
      <text>还没有错题，去上传一题吧 📷</text>
      <button
        class="btn-sm"
        @tap="() => uni.navigateTo({ url: '/pages/upload/index' })"
      >
        上传错题
      </button>
    </view>

    <!-- 列表 -->
    <view v-else>
      <view
        v-for="wq in items"
        :key="wq.id"
        class="wq-card"
        @tap="goDetail(wq.id)"
      >
        <image
          class="wq-img"
          :src="wq.source_image_url"
          mode="aspectFill"
          lazy-load
        />
        <view class="wq-info">
          <view class="wq-meta">
            <text v-if="wq.question_type" class="tag">{{ wq.question_type }}</text>
            <text v-if="wq.difficulty" class="tag">{{ '★'.repeat(wq.difficulty) }}</text>
            <text v-if="wq.is_mastered" class="tag tag-green">已掌握</text>
          </view>
          <text class="wq-date">{{ wq.created_at.slice(0, 10) }}</text>
        </view>
      </view>

      <!-- 加载更多 -->
      <view v-if="hasMore" class="load-more" @tap="loadMore">
        {{ loading ? '加载中…' : '加载更多' }}
      </view>
      <view v-else-if="items.length > 0" class="load-more gray">已加载全部</view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listWrongQuestions } from '@/api/wrongQuestions'
import { useAuthStore } from '@/stores/auth'
import type { WrongQuestionOut } from '@/types/api'

const auth = useAuthStore()
const items = ref<WrongQuestionOut[]>([])
const total = ref(0)
const loading = ref(false)
const skip = ref(0)
const LIMIT = 20
const hasMore = ref(true)

onMounted(async () => {
  if (!auth.isLoggedIn()) {
    await auth.login()
  }
  await loadItems()
})

async function loadItems() {
  if (loading.value) return
  loading.value = true
  try {
    const res = await listWrongQuestions(skip.value, LIMIT)
    items.value.push(...res.items)
    total.value = res.total
    hasMore.value = items.value.length < res.total
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'error' })
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  if (loading.value || !hasMore.value) return
  skip.value += LIMIT
  await loadItems()
}

function goDetail(id: string) {
  uni.navigateTo({ url: `/pages/wrong-questions/detail?id=${id}` })
}
</script>

<style scoped>
.list-page { padding: 24rpx; background: #f5f5f5; min-height: 100vh; }
.center-tip { text-align: center; padding: 120rpx 0; color: #999; font-size: 28rpx; }
.btn-sm {
  margin-top: 32rpx;
  background: #1677ff;
  color: #fff;
  font-size: 28rpx;
  border-radius: 10rpx;
}
.wq-card {
  display: flex;
  background: #fff;
  border-radius: 16rpx;
  margin-bottom: 20rpx;
  overflow: hidden;
}
.wq-img { width: 180rpx; height: 140rpx; flex-shrink: 0; }
.wq-info {
  flex: 1;
  padding: 20rpx;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}
.wq-meta { display: flex; flex-wrap: wrap; gap: 8rpx; }
.tag {
  background: #e6f0ff;
  color: #1677ff;
  font-size: 22rpx;
  padding: 4rpx 12rpx;
  border-radius: 6rpx;
}
.tag-green { background: #f0fff4; color: #52c41a; }
.wq-date { color: #999; font-size: 24rpx; }
.load-more { text-align: center; padding: 32rpx; color: #1677ff; font-size: 28rpx; }
.gray { color: #ccc; }
</style>
```

- [ ] **Step 2: 创建 `src/pages/wrong-questions/detail.vue`**

注意：uni-app 小程序获取页面参数用 `getCurrentPages()` 而非 Vue Router 的 `useRoute()`。

```vue
<!-- src/pages/wrong-questions/detail.vue -->
<template>
  <view class="detail-page">
    <view v-if="!wq" class="center-tip">加载中…</view>
    <view v-else>
      <!-- 题目图片 -->
      <image
        class="wq-img"
        :src="wq.source_image_url"
        mode="widthFix"
        @tap="previewImg"
      />

      <!-- 元信息卡 -->
      <view class="card">
        <view class="row">
          <text class="label">题型</text>
          <text>{{ wq.question_type || '未填写' }}</text>
        </view>
        <view class="row">
          <text class="label">难度</text>
          <text>{{ wq.difficulty ? '★'.repeat(wq.difficulty) : '未填写' }}</text>
        </view>
        <view class="row">
          <text class="label">已掌握</text>
          <switch :checked="wq.is_mastered" @change="onToggleMastered" />
        </view>
      </view>

      <!-- AI 分析 -->
      <view class="card">
        <view class="card-title">AI 诊断分析</view>
        <button class="btn-analyze" :disabled="analyzing" @tap="onAnalyze">
          {{ analyzing ? '分析中（约3-8秒）…' : '触发 AI 分析' }}
        </button>

        <view v-if="latestAnalysis" class="analysis-result">
          <view class="section-title">错误类型</view>
          <view class="tags">
            <text
              v-for="t in latestAnalysis.error_types"
              :key="t"
              class="tag-red"
            >{{ t }}</text>
          </view>

          <view class="section-title">薄弱知识点</view>
          <view class="tags">
            <text
              v-for="k in latestAnalysis.knowledge_points"
              :key="k"
              class="tag-orange"
            >{{ k }}</text>
          </view>

          <view class="section-title">诊断</view>
          <text class="analysis-text">{{ latestAnalysis.diagnosis }}</text>

          <view class="section-title">建议</view>
          <text class="analysis-text">{{ latestAnalysis.suggestions }}</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  analyzeWrongQuestion,
  getWrongQuestion,
  listAnalyses,
  markMastered,
} from '@/api/wrongQuestions'
import type { AiAnalysisOut, WrongQuestionOut } from '@/types/api'

// uni-app 小程序获取路由参数方式
const pages = getCurrentPages()
const currentPage = pages[pages.length - 1] as UniApp.Page & { options: Record<string, string> }
const wqId = currentPage.options.id

const wq = ref<WrongQuestionOut | null>(null)
const latestAnalysis = ref<AiAnalysisOut | null>(null)
const analyzing = ref(false)

onMounted(async () => {
  try {
    wq.value = await getWrongQuestion(wqId)
    const analyses = await listAnalyses(wqId)
    if (analyses.length > 0) latestAnalysis.value = analyses[0]
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'error' })
  }
})

async function onToggleMastered(e: { detail: { value: boolean } }) {
  if (!wq.value) return
  try {
    wq.value = await markMastered(wqId, e.detail.value)
  } catch (err) {
    uni.showToast({ title: (err as Error).message, icon: 'error' })
  }
}

async function onAnalyze() {
  analyzing.value = true
  try {
    latestAnalysis.value = await analyzeWrongQuestion(wqId)
    uni.showToast({ title: 'AI 分析完成', icon: 'success' })
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'error' })
  } finally {
    analyzing.value = false
  }
}

function previewImg() {
  if (wq.value) {
    uni.previewImage({ urls: [wq.value.source_image_url] })
  }
}
</script>

<style scoped>
.detail-page { padding: 24rpx; background: #f5f5f5; min-height: 100vh; }
.center-tip { text-align: center; padding: 100rpx; color: #999; }
.wq-img { width: 100%; border-radius: 16rpx; margin-bottom: 20rpx; }
.card { background: #fff; border-radius: 16rpx; padding: 28rpx; margin-bottom: 20rpx; }
.card-title { font-size: 30rpx; font-weight: bold; margin-bottom: 20rpx; color: #222; }
.row {
  display: flex;
  align-items: center;
  padding: 16rpx 0;
  border-bottom: 1rpx solid #f5f5f5;
}
.label { width: 140rpx; color: #666; font-size: 28rpx; }
.btn-analyze {
  background: #1677ff;
  color: #fff;
  border-radius: 10rpx;
  font-size: 28rpx;
  height: 80rpx;
  line-height: 80rpx;
}
.btn-analyze[disabled] { opacity: 0.5; }
.analysis-result { margin-top: 24rpx; }
.section-title { font-size: 26rpx; color: #888; margin: 20rpx 0 8rpx; }
.tags { display: flex; flex-wrap: wrap; gap: 10rpx; }
.tag-red {
  background: #fff0f0;
  color: #ff4d4f;
  font-size: 24rpx;
  padding: 4rpx 14rpx;
  border-radius: 6rpx;
}
.tag-orange {
  background: #fff7e6;
  color: #fa8c16;
  font-size: 24rpx;
  padding: 4rpx 14rpx;
  border-radius: 6rpx;
}
.analysis-text { font-size: 28rpx; color: #333; line-height: 1.7; }
</style>
```

- [ ] **Step 3: 验证编译**

```bash
pnpm dev:mp-weixin
```

预期：`pages/wrong-questions/list.js` 和 `detail.js` 均生成，无 TS 错误。

- [ ] **Step 4: Commit**

```bash
git add src/pages/wrong-questions/
git commit -m "feat(frontend): add wrong question list and detail pages with AI analysis trigger"
```

---

### Task 4: 学情报告页（DiagnosisReport 可视化）

**Files:**
- Create: `frontend/miniprogram/src/pages/diagnosis/index.vue`

MVP 阶段不引入 ECharts（800KB+），用纯 CSS 进度条 + 活跃度方格展示。

- [ ] **Step 1: 创建 `src/pages/diagnosis/index.vue`**

```vue
<!-- src/pages/diagnosis/index.vue -->
<template>
  <view class="diag-page">
    <view v-if="loading" class="center-tip">生成报告中…</view>
    <view v-else-if="!report" class="center-tip">暂无数据</view>
    <view v-else>

      <!-- 总览卡片 -->
      <view class="card overview">
        <view class="stat-row">
          <view class="stat-item">
            <text class="stat-num">{{ report.total_questions }}</text>
            <text class="stat-label">累计错题</text>
          </view>
          <view class="stat-item">
            <text class="stat-num">{{ report.total_analyzed }}</text>
            <text class="stat-label">已分析</text>
          </view>
          <view class="stat-item">
            <text class="stat-num">{{ (report.mastery_rate * 100).toFixed(0) }}%</text>
            <text class="stat-label">掌握率</text>
          </view>
        </view>
      </view>

      <!-- 高频错误类型（CSS 进度条） -->
      <view class="card" v-if="report.top_error_types.length > 0">
        <view class="card-title">高频错误类型 TOP 5</view>
        <view
          v-for="item in report.top_error_types.slice(0, 5)"
          :key="item.error_type"
          class="bar-item"
        >
          <text class="bar-label">{{ item.error_type }}</text>
          <view class="bar-track">
            <view
              class="bar-fill"
              :style="{ width: barWidth(item.count, maxErrorCount) + '%' }"
            />
          </view>
          <text class="bar-count">{{ item.count }}</text>
        </view>
      </view>

      <!-- 薄弱知识点 -->
      <view class="card" v-if="report.top_weak_knowledge_points.length > 0">
        <view class="card-title">薄弱知识点</view>
        <view class="tags">
          <text
            v-for="kp in report.top_weak_knowledge_points.slice(0, 8)"
            :key="kp.knowledge_point"
            class="tag-kp"
          >
            {{ kp.knowledge_point }}（{{ kp.count }}）
          </text>
        </view>
      </view>

      <!-- 近30天活跃度方格 -->
      <view class="card">
        <view class="card-title">近30天提交</view>
        <view class="activity-grid">
          <view
            v-for="day in report.recent_daily_activity"
            :key="day.date"
            class="activity-cell"
            :class="activityClass(day.count)"
          />
        </view>
        <text class="activity-hint">颜色越深表示提交越多</text>
      </view>

      <!-- AI 学习建议 -->
      <view class="card" v-if="report.top_suggestions.length > 0">
        <view class="card-title">AI 学习建议</view>
        <view
          v-for="(s, i) in report.top_suggestions"
          :key="i"
          class="suggestion-item"
        >
          <text class="suggestion-num">{{ i + 1 }}</text>
          <text class="suggestion-text">{{ s }}</text>
        </view>
      </view>

    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getDiagnosisReport } from '@/api/diagnosis'
import { useAuthStore } from '@/stores/auth'
import type { DiagnosisReport } from '@/types/api'

const auth = useAuthStore()
const report = ref<DiagnosisReport | null>(null)
const loading = ref(false)

const maxErrorCount = computed(() => {
  if (!report.value || report.value.top_error_types.length === 0) return 1
  return Math.max(...report.value.top_error_types.map((e) => e.count))
})

onMounted(async () => {
  if (!auth.isLoggedIn()) await auth.login()
  loading.value = true
  try {
    report.value = await getDiagnosisReport()
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'error' })
  } finally {
    loading.value = false
  }
})

function barWidth(count: number, max: number): number {
  return max === 0 ? 0 : Math.round((count / max) * 100)
}

function activityClass(count: number): string {
  if (count === 0) return 'activity-0'
  if (count === 1) return 'activity-1'
  if (count <= 3) return 'activity-2'
  return 'activity-3'
}
</script>

<style scoped>
.diag-page { padding: 24rpx; background: #f5f5f5; min-height: 100vh; }
.center-tip { text-align: center; padding: 120rpx; color: #999; }
.card { background: #fff; border-radius: 16rpx; padding: 28rpx; margin-bottom: 20rpx; }
.card-title { font-size: 30rpx; font-weight: bold; margin-bottom: 20rpx; color: #222; }

/* 总览 */
.stat-row { display: flex; justify-content: space-around; }
.stat-item { text-align: center; }
.stat-num { font-size: 56rpx; font-weight: bold; color: #1677ff; display: block; }
.stat-label { font-size: 24rpx; color: #999; }

/* 进度条 */
.bar-item { display: flex; align-items: center; margin-bottom: 16rpx; }
.bar-label { width: 160rpx; font-size: 26rpx; color: #333; flex-shrink: 0; }
.bar-track { flex: 1; background: #f0f0f0; height: 16rpx; border-radius: 8rpx; margin: 0 16rpx; }
.bar-fill { height: 100%; background: #1677ff; border-radius: 8rpx; }
.bar-count { font-size: 24rpx; color: #666; width: 48rpx; text-align: right; }

/* 知识点标签 */
.tags { display: flex; flex-wrap: wrap; gap: 12rpx; }
.tag-kp {
  background: #f5f0ff;
  color: #722ed1;
  font-size: 24rpx;
  padding: 6rpx 16rpx;
  border-radius: 8rpx;
}

/* 活跃度方格 */
.activity-grid { display: flex; flex-wrap: wrap; gap: 6rpx; margin-bottom: 12rpx; }
.activity-cell { width: 28rpx; height: 28rpx; border-radius: 4rpx; }
.activity-0 { background: #eee; }
.activity-1 { background: #bce7ff; }
.activity-2 { background: #69c0ff; }
.activity-3 { background: #1677ff; }
.activity-hint { font-size: 22rpx; color: #bbb; }

/* 建议 */
.suggestion-item { display: flex; align-items: flex-start; margin-bottom: 20rpx; }
.suggestion-num {
  width: 44rpx;
  height: 44rpx;
  background: #1677ff;
  color: #fff;
  border-radius: 50%;
  font-size: 24rpx;
  line-height: 44rpx;
  text-align: center;
  flex-shrink: 0;
  margin-right: 16rpx;
}
.suggestion-text { flex: 1; font-size: 28rpx; color: #333; line-height: 1.7; }
</style>
```

- [ ] **Step 2: 验证编译**

```bash
pnpm dev:mp-weixin
```

预期：`pages/diagnosis/index.js` 生成，无 TS 错误。

- [ ] **Step 3: Commit**

```bash
git add src/pages/diagnosis/
git commit -m "feat(frontend): add diagnosis report page with bar charts and activity grid"
```

---

### Task 5: 个人中心 + 会员状态 + 微信支付

**Files:**
- Create: `frontend/miniprogram/src/pages/profile/index.vue`

- [ ] **Step 1: 创建 `src/pages/profile/index.vue`**

```vue
<!-- src/pages/profile/index.vue -->
<template>
  <view class="profile-page">

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

    <!-- 会员状态 + 升级 -->
    <view class="card">
      <view class="card-title">会员状态</view>

      <view v-if="loadingMembership" class="center-tip">加载中…</view>
      <view v-else-if="membership">
        <view class="member-tier" :class="`tier-${membership.tier}`">
          {{ tierLabel(membership.tier) }}
        </view>
        <text v-if="membership.expires_at" class="expires-tip">
          到期：{{ membership.expires_at.slice(0, 10) }}
        </text>
      </view>

      <!-- 档位选择 -->
      <view class="tier-list">
        <view
          v-for="plan in memberPlans"
          :key="plan.tier"
          class="tier-card"
          :class="{ selected: selectedPlan === plan.tier }"
          @tap="selectedPlan = plan.tier"
        >
          <text class="tier-name">{{ plan.label }}</text>
          <text class="tier-price">¥{{ plan.price }}/月</text>
        </view>
      </view>

      <!-- 时长选择 -->
      <view class="duration-row">
        <view
          v-for="d in [1, 3, 12]"
          :key="d"
          class="duration-btn"
          :class="{ selected: selectedDuration === d }"
          @tap="selectedDuration = d"
        >
          <text>{{ d }}个月</text>
          <text v-if="d === 12" class="discount-tag">8折</text>
        </view>
      </view>

      <button
        class="btn-pay"
        :disabled="paying || !auth.isLoggedIn()"
        @tap="onPay"
      >
        {{ paying ? '支付中…' : `立即升级 ¥${currentPrice}` }}
      </button>
    </view>

  </view>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getMyMembership } from '@/api/memberships'
import { createOrder, payOrder } from '@/api/orders'
import { useAuthStore } from '@/stores/auth'
import type { CurrentMembershipOut } from '@/types/api'

const auth = useAuthStore()
const membership = ref<CurrentMembershipOut | null>(null)
const loadingMembership = ref(false)
const paying = ref(false)
const selectedPlan = ref('basic')
const selectedDuration = ref(1)

const memberPlans = [
  { tier: 'basic', label: '基础版', price: 9 },
  { tier: 'pro', label: '专业版', price: 19 },
  { tier: 'promax', label: '旗舰版', price: 39 },
]

// 12个月享8折
const currentPrice = computed(() => {
  const plan = memberPlans.find((p) => p.tier === selectedPlan.value)
  if (!plan) return 0
  const base = plan.price * selectedDuration.value
  return selectedDuration.value === 12 ? Math.round(base * 0.8) : base
})

onMounted(async () => {
  if (!auth.isLoggedIn()) return
  loadingMembership.value = true
  try {
    membership.value = await getMyMembership()
  } finally {
    loadingMembership.value = false
  }
})

function tierLabel(tier: string): string {
  const map: Record<string, string> = {
    free: '免费版',
    basic: '基础版',
    pro: '专业版',
    promax: '旗舰版',
  }
  return map[tier] || tier
}

async function onPay() {
  if (!auth.isLoggedIn()) {
    await auth.login()
    return
  }
  paying.value = true
  try {
    const orderType = membership.value?.tier === 'free' ? 'new' : 'renew'
    const order = await createOrder({
      tier: selectedPlan.value,
      duration_months: selectedDuration.value,
      order_type: orderType,
    })
    const params = await payOrder(order.id)

    await new Promise<void>((resolve, reject) => {
      wx.requestPayment({
        timeStamp: params.timeStamp,
        nonceStr: params.nonceStr,
        package: params.package,
        signType: params.signType as 'RSA' | 'MD5',
        paySign: params.paySign,
        success: () => resolve(),
        fail: (err) => reject(new Error(err.errMsg || '支付取消')),
      })
    })

    uni.showToast({ title: '支付成功！', icon: 'success' })
    membership.value = await getMyMembership()
  } catch (e) {
    const msg = (e as Error).message
    // 用户主动取消不提示错误
    if (msg && !msg.includes('cancel')) {
      uni.showToast({ title: msg || '支付失败', icon: 'error' })
    }
  } finally {
    paying.value = false
  }
}
</script>

<style scoped>
.profile-page { padding: 24rpx; background: #f5f5f5; min-height: 100vh; }
.card { background: #fff; border-radius: 16rpx; padding: 28rpx; margin-bottom: 20rpx; }
.card-title { font-size: 30rpx; font-weight: bold; margin-bottom: 20rpx; color: #222; }
.user-row { display: flex; align-items: center; }
.avatar { width: 100rpx; height: 100rpx; border-radius: 50%; margin-right: 24rpx; }
.avatar-placeholder {
  width: 100rpx;
  height: 100rpx;
  background: #eee;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 48rpx;
  margin-right: 24rpx;
}
.nickname { font-size: 32rpx; font-weight: bold; color: #222; }
.btn-login { background: #1677ff; color: #fff; border-radius: 10rpx; }
.member-tier {
  display: inline-block;
  padding: 8rpx 24rpx;
  border-radius: 8rpx;
  font-size: 28rpx;
  font-weight: bold;
  margin-bottom: 12rpx;
}
.tier-free { background: #f5f5f5; color: #999; }
.tier-basic { background: #e6f0ff; color: #1677ff; }
.tier-pro { background: #fff7e6; color: #fa8c16; }
.tier-promax { background: #fff0f0; color: #f5222d; }
.expires-tip { font-size: 24rpx; color: #999; display: block; margin-bottom: 20rpx; }
.tier-list { display: flex; gap: 16rpx; margin: 24rpx 0; }
.tier-card {
  flex: 1;
  border: 2rpx solid #e0e0e0;
  border-radius: 12rpx;
  padding: 20rpx;
  text-align: center;
}
.tier-card.selected { border-color: #1677ff; background: #f0f7ff; }
.tier-name { font-size: 26rpx; color: #333; display: block; margin-bottom: 8rpx; }
.tier-price { font-size: 24rpx; color: #1677ff; }
.duration-row { display: flex; gap: 16rpx; margin-bottom: 24rpx; }
.duration-btn {
  flex: 1;
  text-align: center;
  padding: 16rpx;
  border: 2rpx solid #e0e0e0;
  border-radius: 10rpx;
  font-size: 26rpx;
  position: relative;
}
.duration-btn.selected { border-color: #1677ff; color: #1677ff; background: #f0f7ff; }
.discount-tag {
  position: absolute;
  top: -14rpx;
  right: -8rpx;
  background: #ff4d4f;
  color: #fff;
  font-size: 18rpx;
  padding: 2rpx 8rpx;
  border-radius: 6rpx;
}
.btn-pay {
  background: #1677ff;
  color: #fff;
  border-radius: 12rpx;
  font-size: 32rpx;
  height: 96rpx;
  line-height: 96rpx;
}
.btn-pay[disabled] { opacity: 0.5; }
.center-tip { color: #999; font-size: 28rpx; }
</style>
```

- [ ] **Step 2: 验证编译**

```bash
pnpm dev:mp-weixin
```

预期：`pages/profile/index.js` 生成，无 TS 错误。

- [ ] **Step 3: Commit**

```bash
git add src/pages/profile/
git commit -m "feat(frontend): add profile page with membership status display and WeChat Pay flow"
```

---

### Task 6: 首页 + App.vue + 集成验证 + push + D-065

**Files:**
- Create: `frontend/miniprogram/src/pages/index/index.vue`
- Modify: `frontend/miniprogram/src/App.vue`
- Modify: `docs/决策归档.md` (prepend D-065)

- [ ] **Step 1: 创建 `src/pages/index/index.vue`**

```vue
<!-- src/pages/index/index.vue -->
<template>
  <view class="home-page">
    <view class="hero">
      <text class="hero-title">engGramer</text>
      <text class="hero-sub">英语 AI 错题诊断</text>
    </view>

    <view class="quick-grid">
      <view
        class="quick-card"
        @tap="() => uni.navigateTo({ url: '/pages/upload/index' })"
      >
        <text class="quick-icon">📷</text>
        <text class="quick-label">上传错题</text>
      </view>
      <view
        class="quick-card"
        @tap="() => uni.switchTab({ url: '/pages/wrong-questions/list' })"
      >
        <text class="quick-icon">📚</text>
        <text class="quick-label">我的错题</text>
      </view>
      <view
        class="quick-card"
        @tap="() => uni.switchTab({ url: '/pages/diagnosis/index' })"
      >
        <text class="quick-icon">📊</text>
        <text class="quick-label">学情报告</text>
      </view>
      <view
        class="quick-card"
        @tap="() => uni.switchTab({ url: '/pages/profile/index' })"
      >
        <text class="quick-icon">👤</text>
        <text class="quick-label">个人中心</text>
      </view>
    </view>

    <view v-if="!auth.isLoggedIn()" class="login-banner">
      <text class="login-tip">登录后解锁 AI 分析功能</text>
      <button class="btn-login" @tap="auth.login()">微信一键登录</button>
    </view>
  </view>
</template>

<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
</script>

<style scoped>
.home-page { padding: 40rpx 24rpx; background: #f5f5f5; min-height: 100vh; }
.hero { text-align: center; padding: 60rpx 0 48rpx; }
.hero-title { font-size: 60rpx; font-weight: bold; color: #1677ff; display: block; }
.hero-sub { font-size: 30rpx; color: #888; display: block; margin-top: 12rpx; }
.quick-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20rpx; margin-bottom: 32rpx; }
.quick-card {
  background: #fff;
  border-radius: 20rpx;
  padding: 40rpx 0;
  text-align: center;
}
.quick-icon { font-size: 56rpx; display: block; margin-bottom: 16rpx; }
.quick-label { font-size: 28rpx; color: #333; }
.login-banner {
  background: #fff;
  border-radius: 20rpx;
  padding: 36rpx 32rpx;
  text-align: center;
}
.login-tip { font-size: 28rpx; color: #666; display: block; margin-bottom: 24rpx; }
.btn-login { background: #1677ff; color: #fff; border-radius: 12rpx; font-size: 30rpx; }
</style>
```

- [ ] **Step 2: 修改 `src/App.vue`**

```vue
<!-- src/App.vue -->
<script setup lang="ts">
import { onLaunch } from '@dcloudio/uni-app'

onLaunch(() => {
  // storage 里有 token 时 Pinia store 构造时已自动恢复，无需额外操作。
  // 不在 onLaunch 强制弹出登录，避免影响首次打开体验。
  console.log('[App] launched')
})
</script>

<template>
  <layout />
</template>
```

- [ ] **Step 3: 完整编译验证**

```bash
pnpm dev:mp-weixin
```

预期：
- 全部6个页面生成（index, upload, wrong-questions/list, wrong-questions/detail, diagnosis, profile）
- 无 TS 类型错误
- 无缺失文件警告

如有 `wx` 全局变量 TS 报错，在 `tsconfig.json` 中添加：
```json
{
  "compilerOptions": {
    "types": ["@dcloudio/types"]
  }
}
```

然后 `pnpm add -D @dcloudio/types`，再次编译。

- [ ] **Step 4: 追加决策归档 D-065**

在 `docs/决策归档.md` 文件顶部（现有所有 D-06x 条目之前）追加：

```markdown
## D-065 · 微信小程序前端技术选型

**日期：** 2026-05-26
**状态：** 已定案

**决策：** 使用 uni-app Vue3 + TypeScript + Pinia + Vite 开发微信小程序 MVP，项目位于 `frontend/miniprogram/`。

**理由：**
- uni-app 是国内最成熟的多端小程序框架，Vue3 + TypeScript 与团队技能匹配
- Pinia 比 Vuex 更轻量，适合小程序状态管理
- COS 图片直传采用 `wx.getFileSystemManager().readFile` + `wx.request({ method: 'PUT' })` 绕开小程序不支持 multipart/form-data 的限制（`uni.uploadFile` 是 POST multipart，不适用于 COS presigned PUT URL）
- MVP 阶段不引入 ECharts（体积 800KB+），用纯 CSS 进度条和活跃度方格替代，后续迭代再接入
- `request.ts` 直接用 `uni.getStorageSync` 读 token 避免循环依赖，token 统一存在 `access_token` key

---
```

- [ ] **Step 5: Commit + push**

```bash
cd /path/to/engGramer
git add frontend/ docs/决策归档.md
git commit -m "feat(frontend): complete miniprogram MVP — home, App.vue, D-065 archived"
git push
```

预期：push 成功，GitHub 上可见 `frontend/miniprogram/` 目录。
