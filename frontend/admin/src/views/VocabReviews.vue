<script setup lang="ts">
import AppDialog from '../components/AppDialog.vue'
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listVocabReviews, approveVocabReview, rejectVocabReview, type VocabReviewItem } from '../api/admin'

const status = ref('pending')
const rows = ref<VocabReviewItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 50
const loading = ref(false)

const statusOptions = [
  { label: '待审', value: 'pending' },
  { label: '已入库', value: 'approved' },
  { label: '已驳回', value: 'rejected' },
]

async function load() {
  loading.value = true
  try {
    const data = await listVocabReviews({ status: status.value, skip: (page.value - 1) * pageSize, limit: pageSize })
    rows.value = data.items
    total.value = data.total
  } finally { loading.value = false }
}
function reload() { page.value = 1; load() }

// 审核入库
const approveVisible = ref(false)
const approving = ref<VocabReviewItem | null>(null)
const form = ref({ phonetic: '', pos: '', meaning: '' })
function openApprove(row: VocabReviewItem) {
  approving.value = row
  form.value = { phonetic: '', pos: '', meaning: '' }
  approveVisible.value = true
}
async function submitApprove() {
  if (!approving.value) return
  if (!form.value.meaning.trim()) { ElMessage.warning('请填释义'); return }
  const definitions = [{ pos: form.value.pos.trim(), meaning: form.value.meaning.trim() }]
  await approveVocabReview(approving.value.id, { phonetic: form.value.phonetic.trim() || undefined, definitions })
  ElMessage.success('已加入词库')
  approveVisible.value = false
  load()
}
async function reject(row: VocabReviewItem) {
  await ElMessageBox.confirm(`驳回缺词「${row.word}」?`, '驳回', { type: 'warning' })
  await rejectVocabReview(row.id)
  ElMessage.success('已驳回')
  load()
}

onMounted(load)
</script>

<template>
  <div class="page">
    <div class="toolbar">
      <h2>词库缺词审核</h2>
      <el-radio-group v-model="status" @change="reload">
        <el-radio-button v-for="o in statusOptions" :key="o.value" :label="o.value">{{ o.label }}</el-radio-button>
      </el-radio-group>
      <span class="hint">作业/课程里出现、但词库没有的词。审核通过即加入词库(学生端「单词精讲」才有详解)。</span>
    </div>

    <el-table v-loading="loading" :data="rows" border style="width: 100%">
      <el-table-column prop="word" label="词" min-width="160" />
      <el-table-column prop="occur_count" label="出现次数" width="100" sortable />
      <el-table-column prop="source" label="来源" width="100" />
      <el-table-column prop="created_at" label="首次出现" width="200">
        <template #default="{ row }">{{ row.created_at ? new Date(row.created_at).toLocaleString() : '—' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <template v-if="row.status === 'pending'">
            <el-button size="small" type="primary" @click="openApprove(row)">入库</el-button>
            <el-button size="small" @click="reject(row)">驳回</el-button>
          </template>
          <el-tag v-else :type="row.status === 'approved' ? 'success' : 'info'">
            {{ row.status === 'approved' ? '已入库' : '已驳回' }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      class="pager" layout="total, prev, pager, next, jumper"
      :total="total" :page-size="pageSize" v-model:current-page="page" @current-change="load" />

    <AppDialog v-model="approveVisible" title="加入词库" width="480px">
      <el-form v-if="approving" label-width="72px">
        <el-form-item label="词"><b>{{ approving.word }}</b></el-form-item>
        <el-form-item label="音标"><el-input v-model="form.phonetic" placeholder="如 əˈbsent(可空)" /></el-form-item>
        <el-form-item label="词性"><el-input v-model="form.pos" placeholder="如 adj./n./v.(可空)" /></el-form-item>
        <el-form-item label="释义"><el-input v-model="form.meaning" type="textarea" :rows="2" placeholder="中文释义(必填)" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="approveVisible = false">取消</el-button>
        <el-button type="primary" @click="submitApprove">入库</el-button>
      </template>
    </AppDialog>
  </div>
</template>

<style scoped>
.page { padding: 16px; }
.toolbar { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; flex-wrap: wrap; }
.toolbar h2 { margin: 0; }
.hint { color: #909399; font-size: 13px; }
.pager { margin-top: 16px; justify-content: flex-end; }
</style>
