<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listCurriculumUnits, generateUnitContent } from '../api/admin'
import type { AdminCurriculumUnit } from '../types'

const rows = ref<AdminCurriculumUnit[]>([])
const loading = ref(false)
const generating = ref<Record<string, boolean>>({})

// 筛选
const filterTextbook = ref('')
const filterGrade = ref('')
const filterSemester = ref('')

const textbookOptions = computed(() => [...new Set(rows.value.map(r => r.textbook_version))])
const gradeOptions = computed(() => [...new Set(rows.value.map(r => r.grade))])
const semesterOptions = computed(() => [...new Set(rows.value.map(r => r.semester))])

const filteredRows = computed(() => rows.value.filter(r => {
  if (filterTextbook.value && r.textbook_version !== filterTextbook.value) return false
  if (filterGrade.value && r.grade !== filterGrade.value) return false
  if (filterSemester.value && r.semester !== filterSemester.value) return false
  return true
}))

async function load() {
  loading.value = true
  try {
    rows.value = await listCurriculumUnits()
  } catch (e: any) {
    ElMessage.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function onGenerate(row: AdminCurriculumUnit) {
  await ElMessageBox.confirm(
    `确认为「${row.textbook_version} ${row.grade} ${row.semester}学期 Unit ${row.unit_no}」生成 AI 课程内容？\n` +
    `生成内容状态为草稿，需在"内容审核"页发布后学生才可见。`,
    '生成确认',
    { type: 'warning', confirmButtonText: '生成', cancelButtonText: '取消' },
  )
  generating.value[row.unit_id] = true
  try {
    const result = await generateUnitContent(row.unit_id)
    ElMessage.success(
      `生成完成！KP 数: ${result.kp_count}，内容条数: ${result.content_count}`
    )
    // 更新该行统计
    const idx = rows.value.findIndex(r => r.unit_id === row.unit_id)
    if (idx !== -1) {
      rows.value[idx] = {
        ...rows.value[idx],
        kp_count: result.kp_count,
        content_count: result.content_count,
        content_rate: result.content_rate,
      }
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '生成失败')
  } finally {
    generating.value[row.unit_id] = false
  }
}

function rateColor(rate: number): string {
  if (rate >= 1) return '#67C23A'
  if (rate > 0) return '#E6A23C'
  return '#F56C6C'
}

onMounted(load)
</script>

<template>
  <div>
    <!-- 筛选工具栏 -->
    <div class="toolbar" style="margin-bottom: 16px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap;">
      <el-select v-model="filterTextbook" placeholder="教材版本" clearable style="width: 140px">
        <el-option v-for="t in textbookOptions" :key="t" :label="t" :value="t" />
      </el-select>
      <el-select v-model="filterGrade" placeholder="年级" clearable style="width: 140px">
        <el-option v-for="g in gradeOptions" :key="g" :label="g" :value="g" />
      </el-select>
      <el-select v-model="filterSemester" placeholder="学期" clearable style="width: 100px">
        <el-option v-for="s in semesterOptions" :key="s" :label="s + '学期'" :value="s" />
      </el-select>
      <el-button @click="load" :loading="loading">🔄 刷新</el-button>
      <span style="color: #909399; font-size: 13px;">
        共 {{ filteredRows.length }} 个单元 ·
        已完成 {{ filteredRows.filter(r => r.content_rate >= 1).length }} 个
      </span>
    </div>

    <!-- 单元列表 -->
    <el-table
      v-loading="loading"
      :data="filteredRows"
      border
      style="width: 100%"
    >
      <el-table-column prop="textbook_version" label="教材" width="90" />
      <el-table-column prop="grade" label="年级" width="110" />
      <el-table-column prop="semester" label="学期" width="70">
        <template #default="{ row }">{{ row.semester }}学期</template>
      </el-table-column>
      <el-table-column prop="unit_no" label="Unit" width="60" align="center" />
      <el-table-column prop="unit_title" label="单元标题" min-width="160" show-overflow-tooltip />
      <el-table-column prop="kp_count" label="KP数" width="70" align="center" />
      <el-table-column label="内容完成度" width="180">
        <template #default="{ row }">
          <div style="display: flex; align-items: center; gap: 8px;">
            <el-progress
              :percentage="Math.round(row.content_rate * 100)"
              :color="rateColor(row.content_rate)"
              :stroke-width="8"
              style="flex: 1"
            />
            <span style="font-size: 12px; white-space: nowrap; color: #606266;">
              {{ row.content_count }}/{{ row.kp_count * 6 }}
            </span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button
            size="small"
            type="primary"
            :loading="generating[row.unit_id]"
            @click="onGenerate(row)"
          >
            🤖 生成内容
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>
