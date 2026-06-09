<script setup lang="ts">
import { onMounted, ref, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listExamPapers, createExamPaper, generateSimQuestionsFromPaper } from '../api/admin'
import type { AdminExamPaperItem } from '../types'

const rows = ref<AdminExamPaperItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)
const generating = ref<string | null>(null)

// 新建表单
const dialogVisible = ref(false)
const submitting = ref(false)
const form = reactive({
  title: '',
  textbook_version: '',
  grade: '',
  semester: '',
  region: '',
  paper_url: '',
})

const gradeOptions = ['小学3年级', '小学4年级', '小学5年级', '小学6年级', '初中1年级', '初中2年级', '初中3年级']
const semesterOptions = ['上', '下']
const versionOptions = ['译林版', '人教版', '外研版', '北师大版']

async function load() {
  loading.value = true
  try {
    const data = await listExamPapers({
      skip: (page.value - 1) * pageSize,
      limit: pageSize,
    })
    rows.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

async function onSubmit() {
  if (!form.title || !form.textbook_version || !form.grade || !form.semester) {
    ElMessage.warning('请填写必填字段')
    return
  }
  submitting.value = true
  try {
    await createExamPaper({
      title: form.title,
      textbook_version: form.textbook_version,
      grade: form.grade,
      semester: form.semester,
      region: form.region || undefined,
      paper_url: form.paper_url || undefined,
    })
    ElMessage.success('试卷已录入')
    dialogVisible.value = false
    Object.assign(form, { title: '', textbook_version: '', grade: '', semester: '', region: '', paper_url: '' })
    await load()
  } finally {
    submitting.value = false
  }
}

async function onGenerate(row: AdminExamPaperItem) {
  await ElMessageBox.confirm(
    `确认为「${row.title}」生成仿真题？`,
    '生成仿真题',
    { type: 'info', confirmButtonText: '确认生成', cancelButtonText: '取消' },
  )
  generating.value = row.id
  try {
    const result = await generateSimQuestionsFromPaper(row.id)
    ElMessage.success(`生成完成，新增仿真题 ${result.sim_questions_created} 道`)
    await load()
  } finally {
    generating.value = null
  }
}

function onPageChange(p: number) {
  page.value = p
  load()
}

onMounted(load)
</script>

<template>
  <div>
    <div class="toolbar">
      <span class="title">📄 真题试卷管理</span>
      <el-button type="primary" @click="dialogVisible = true">+ 录入试卷</el-button>
      <el-button @click="load">刷新</el-button>
    </div>

    <el-alert
      type="warning"
      :closable="false"
      style="margin-bottom: 16px"
      title="版权说明：真题试卷仅供平台内部管理，不对外展示原题。请通过「生成仿真题」功能将原题转化为改写版本后再发布。"
    />

    <el-table v-loading="loading" :data="rows" border style="width: 100%">
      <el-table-column prop="title" label="试卷名称" min-width="200" show-overflow-tooltip />
      <el-table-column prop="textbook_version" label="教材版本" width="100" />
      <el-table-column prop="grade" label="年级" width="110" />
      <el-table-column prop="semester" label="学期" width="60" />
      <el-table-column prop="region" label="地区" width="100" />
      <el-table-column prop="status" label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.status === 'published' ? 'success' : 'info'" size="small">
            {{ row.status === 'draft' ? '草稿' : row.status === 'published' ? '已发布' : row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="sim_count" label="仿真题数" width="90" align="center" />
      <el-table-column label="原题链接" width="80" align="center">
        <template #default="{ row }">
          <a v-if="row.paper_url" :href="row.paper_url" target="_blank">查看</a>
          <span v-else class="text-gray">—</span>
        </template>
      </el-table-column>
      <el-table-column label="录入时间" width="160">
        <template #default="{ row }">{{ row.created_at.slice(0, 16).replace('T', ' ') }}</template>
      </el-table-column>
      <el-table-column label="操作" width="130" fixed="right">
        <template #default="{ row }">
          <el-button
            size="small"
            type="primary"
            :loading="generating === row.id"
            @click="onGenerate(row)"
          >
            生成仿真题
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-if="total > pageSize"
      style="margin-top: 16px; justify-content: flex-end; display: flex"
      :current-page="page"
      :page-size="pageSize"
      :total="total"
      layout="total, prev, pager, next"
      @current-change="onPageChange"
    />

    <!-- 录入试卷弹窗 -->
    <el-dialog v-model="dialogVisible" title="录入真题试卷" width="480px" :close-on-click-modal="false">
      <el-form label-width="90px">
        <el-form-item label="试卷名称" required>
          <el-input v-model="form.title" placeholder="例：2024年上海小学5年级英语期末考卷" />
        </el-form-item>
        <el-form-item label="教材版本" required>
          <el-select v-model="form.textbook_version" placeholder="选择教材版本" style="width: 100%">
            <el-option v-for="v in versionOptions" :key="v" :label="v" :value="v" />
          </el-select>
        </el-form-item>
        <el-form-item label="年级" required>
          <el-select v-model="form.grade" placeholder="选择年级" style="width: 100%">
            <el-option v-for="g in gradeOptions" :key="g" :label="g" :value="g" />
          </el-select>
        </el-form-item>
        <el-form-item label="学期" required>
          <el-select v-model="form.semester" placeholder="选择学期" style="width: 100%">
            <el-option v-for="s in semesterOptions" :key="s" :label="s" :value="s" />
          </el-select>
        </el-form-item>
        <el-form-item label="地区">
          <el-input v-model="form.region" placeholder="例：上海（可选）" />
        </el-form-item>
        <el-form-item label="原题 URL">
          <el-input v-model="form.paper_url" placeholder="OSS 链接（可选，仅内部可见）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="onSubmit">确认录入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.title {
  font-size: 18px;
  font-weight: 600;
  flex: 1;
}
.text-gray {
  color: #aaa;
}
</style>
