<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getTtsStats, getPrewarmSemesters, startPrewarm, getPrewarmStatus,
  type TtsCosUsage, type TtsPrewarmStatus, type TtsPrewarmSemester,
} from '../api/admin'

const cos = ref<TtsCosUsage | null>(null)
const prewarm = ref<TtsPrewarmStatus | null>(null)
const semesters = ref<TtsPrewarmSemester[]>([])

const form = reactive({ idx: 0, scope: 'vocab', limit: 50 })
const starting = ref(false)
let timer: any = null

async function loadStats() {
  const s = await getTtsStats()
  cos.value = s.cos
  prewarm.value = s.prewarm
  // 任务进行中则持续轮询
  if (s.prewarm.running && !timer) startPolling()
}

async function loadSemesters() {
  semesters.value = await getPrewarmSemesters()
}

function startPolling() {
  if (timer) return
  timer = setInterval(async () => {
    const st = await getPrewarmStatus()
    prewarm.value = st
    if (!st.running) {
      stopPolling()
      await loadStats()
      ElMessage.success(`预热完成：成功 ${st.ok} / ${st.total}，失败 ${st.failed}`)
    }
  }, 2000)
}
function stopPolling() {
  if (timer) { clearInterval(timer); timer = null }
}

async function onStart() {
  const sem = semesters.value[form.idx]
  if (!sem) { ElMessage.warning('请选择学期'); return }
  starting.value = true
  try {
    const r = await startPrewarm({
      textbook_version: sem.textbook_version, grade: sem.grade, semester: sem.semester,
      scope: form.scope, limit: form.limit,
    })
    if (!r.started) { ElMessage.warning(r.reason || '未能启动'); return }
    ElMessage.success(`已开始预热：${r.label}（共 ${r.total} 条）`)
    startPolling()
  } finally {
    starting.value = false
  }
}

const pct = () => {
  const p = prewarm.value
  return p && p.total ? Math.round((p.done / p.total) * 100) : 0
}

onMounted(() => { loadStats(); loadSemesters() })
onUnmounted(stopPolling)
</script>

<template>
  <div style="display:flex;flex-direction:column;gap:16px;max-width:680px">
    <el-card>
      <template #header>TTS 用量看板</template>
      <div style="display:flex;gap:32px" v-if="cos">
        <el-statistic title="已生成音频数（COS tts/）" :value="cos.object_count" />
        <el-statistic title="存储用量 (MB)" :value="cos.total_mb" :precision="2" />
      </div>
      <p style="color:#909399;font-size:13px;margin:12px 0 0">
        每个 COS 对象 = 一次已合成（已付费）音频，幂等复用不重复计费。
        <el-button link type="primary" @click="loadStats">刷新</el-button>
      </p>
      <el-alert v-if="cos && !cos.available" type="warning" :closable="false" show-icon
        title="COS 未配置（dev 占位），无法统计用量与预热" style="margin-top:8px" />
    </el-card>

    <el-card>
      <template #header>按学期预热（首播零延迟 · 控成本）</template>
      <p style="color:#909399;font-size:13px;margin:0 0 16px">
        提前把某学期的词表（单词+英文描述）/听力素材合成并上传 COS，学生首次播放即秒开。
        串行单任务执行，已存在的音频自动跳过、不重复合成。
      </p>
      <el-form label-width="90px">
        <el-form-item label="学期">
          <el-select v-model="form.idx" style="width:340px" placeholder="选择学期">
            <el-option v-for="(s, i) in semesters" :key="i" :value="i"
              :label="`${s.textbook_version} / ${s.grade} / ${s.semester}（${s.word_count} 词）`" />
          </el-select>
        </el-form-item>
        <el-form-item label="范围">
          <el-radio-group v-model="form.scope">
            <el-radio value="vocab">词表</el-radio>
            <el-radio value="listening">听力素材</el-radio>
            <el-radio value="all">全部</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="词数上限">
          <el-input-number v-model="form.limit" :min="1" :max="500" :step="10" />
          <span style="color:#909399;font-size:12px;margin-left:8px">每词含「单词+英文描述」约 2 条音频</span>
        </el-form-item>
        <el-button type="primary" :loading="starting"
          :disabled="prewarm?.running" @click="onStart">
          {{ prewarm?.running ? '预热进行中…' : '开始预热' }}
        </el-button>
      </el-form>

      <div v-if="prewarm && (prewarm.running || prewarm.total)" style="margin-top:20px">
        <div style="font-size:13px;color:#606266;margin-bottom:6px">
          {{ prewarm.label }} · {{ prewarm.done }}/{{ prewarm.total }}
          （成功 {{ prewarm.ok }}，失败 {{ prewarm.failed }}）
        </div>
        <el-progress :percentage="pct()" :status="prewarm.running ? '' : 'success'" />
      </div>
    </el-card>
  </div>
</template>
