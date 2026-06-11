<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getTtsSpeed, updateTtsSpeed, getTtsVoices, updateTtsVoices } from '../api/admin'

const form = reactive({ primary: 0.8, junior: 1.0, senior: 1.1 })
const loading = ref(false)
const saving = ref(false)

// 音色：2男2女
const voices = reactive({ male1: '', male2: '', female1: '', female2: '' })
const vLoading = ref(false)
const vSaving = ref(false)

async function load() {
  loading.value = true
  try {
    const s = await getTtsSpeed()
    form.primary = s.primary
    form.junior = s.junior
    form.senior = s.senior
  } finally {
    loading.value = false
  }
}

async function loadVoices() {
  vLoading.value = true
  try {
    const v = await getTtsVoices()
    voices.male1 = v.male[0] || ''
    voices.male2 = v.male[1] || ''
    voices.female1 = v.female[0] || ''
    voices.female2 = v.female[1] || ''
  } finally {
    vLoading.value = false
  }
}

async function onSave() {
  saving.value = true
  try {
    await updateTtsSpeed({ primary: form.primary, junior: form.junior, senior: form.senior })
    ElMessage.success('语速已保存，约 1 分钟内全端生效')
  } finally {
    saving.value = false
  }
}

async function onSaveVoices() {
  const male = [voices.male1, voices.male2].map(s => s.trim()).filter(Boolean)
  const female = [voices.female1, voices.female2].map(s => s.trim()).filter(Boolean)
  if (!male.length || !female.length) {
    ElMessage.warning('男、女音色各至少填 1 个')
    return
  }
  vSaving.value = true
  try {
    await updateTtsVoices({ male, female })
    ElMessage.success('音色已保存，约 1 分钟内全端生效')
  } finally {
    vSaving.value = false
  }
}

onMounted(() => { load(); loadVoices() })
</script>

<template>
  <div style="display:flex;flex-direction:column;gap:16px;max-width:560px">
    <el-card>
      <template #header>听力语速（speed_ratio · 0.5~2.0）</template>
      <p style="color:#909399;font-size:13px;margin:0 0 16px">
        听力音频按学生学段使用对应语速；词力通单词统一使用「初中」档。值越小越慢。
      </p>
      <el-form label-width="120px">
        <el-form-item label="小学（慢）">
          <el-input-number v-model="form.primary" :min="0.5" :max="2" :step="0.05" :precision="2" />
        </el-form-item>
        <el-form-item label="初中（标准）">
          <el-input-number v-model="form.junior" :min="0.5" :max="2" :step="0.05" :precision="2" />
        </el-form-item>
        <el-form-item label="高中（略快）">
          <el-input-number v-model="form.senior" :min="0.5" :max="2" :step="0.05" :precision="2" />
        </el-form-item>
        <el-button type="primary" :loading="saving" @click="onSave">保存语速</el-button>
      </el-form>
    </el-card>

    <el-card>
      <template #header>音色池（2 男 2 女 · 火山 bigtts voice_type）</template>
      <p style="color:#909399;font-size:13px;margin:0 0 16px">
        听力对话按说话人性别自动选音色（多角色同性别在池内轮换）；单词按词哈希稳定取一个音色。
        填火山控制台已授权的 voice_type，如 <code>en_male_tim_uranus_bigtts</code>。
      </p>
      <el-form label-width="120px">
        <el-form-item label="男声 1">
          <el-input v-model="voices.male1" placeholder="en_male_tim_uranus_bigtts" />
        </el-form-item>
        <el-form-item label="男声 2">
          <el-input v-model="voices.male2" placeholder="zh_male_wennuanahu_uranus_bigtts" />
        </el-form-item>
        <el-form-item label="女声 1">
          <el-input v-model="voices.female1" placeholder="en_female_dacey_uranus_bigtts" />
        </el-form-item>
        <el-form-item label="女声 2">
          <el-input v-model="voices.female2" placeholder="en_female_stokie_uranus_bigtts" />
        </el-form-item>
        <el-button type="primary" :loading="vSaving" @click="onSaveVoices">保存音色</el-button>
      </el-form>
    </el-card>
  </div>
</template>
